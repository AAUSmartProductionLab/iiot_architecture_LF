"""The connector data model — the single source of truth for what parameters a
connector carries, per protocol.

This mirrors the Web UI's `web/src/protocols.ts` registry on the Python side so
the gateway, the adapter clients and the AAS all agree on the shape of a
connector. A connector descriptor (stored in the manifest, passed to an adapter
container as CONNECTOR_CONFIG) looks like:

    {
      "device_key": "...",
      "protocol": "modbus-tcp" | "opcua" | "s7",
      "connection": { ...protocol connection fields (see CONNECTION)... },
      "datapoints": [ {
          "name": str, "datatype": <canonical datatype>, "unit": str,
          "local_topic": str,
          "address": { ...protocol address fields (see ADDRESS)... }
      } ],
      "mqtt": {"broker_host", "broker_port"}, "interval": float
    }

Two field groups vary by protocol:
  - `connection` — connector-level, how to reach the device (host/port, url, …).
  - `address`    — per-datapoint, where to read the value from (register, node_id, …).

`datatype` is drawn from DATATYPES, which also pins the *size* of each value for
the binary protocols (how many 16-bit Modbus registers / how many S7 bytes it
spans), so a single declared type drives decoding everywhere.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    default: str | int | None = None
    type: str = "text"  # text | number
    options: tuple[str, ...] | None = None
    required: bool = False


# --- canonical datatypes -----------------------------------------------------
# struct: big-endian decode format (Modbus standard word order, S7 native).
# modbus_registers / s7_bytes: how many 16-bit registers / bytes the value spans.
@dataclass(frozen=True)
class DataType:
    name: str
    struct: str
    modbus_registers: int
    s7_bytes: int
    aliases: tuple[str, ...] = ()


DATATYPES: dict[str, DataType] = {
    dt.name: dt
    for dt in [
        DataType("bool", "?", 1, 1, ("boolean", "bit")),
        DataType("int16", ">h", 1, 2, ("int", "short")),
        DataType("uint16", ">H", 1, 2, ("uint", "word")),
        DataType("int32", ">i", 2, 4, ("dint", "long")),
        DataType("uint32", ">I", 2, 4, ("udint", "dword")),
        DataType("float32", ">f", 2, 4, ("float", "real")),
        DataType("float64", ">d", 4, 8, ("double", "lreal")),
    ]
}

_DATATYPE_ALIASES: dict[str, str] = {
    alias: dt.name for dt in DATATYPES.values() for alias in (dt.name, *dt.aliases)
}


def resolve_datatype(name: str | None) -> DataType | None:
    """Map a user-supplied datatype (e.g. 'real', 'float32') to a DataType, or
    None when unknown (callers then fall back to returning the raw value)."""
    canonical = _DATATYPE_ALIASES.get((name or "").lower())
    return DATATYPES.get(canonical) if canonical else None


def decode(raw: bytes, datatype: str | None):
    """Decode a big-endian byte string to a Python scalar per `datatype`.
    Returns the raw bytes (as a list) when the datatype is unknown or too short."""
    dt = resolve_datatype(datatype)
    if dt is None or len(raw) < struct.calcsize(dt.struct):
        return list(raw)
    value = struct.unpack(dt.struct, raw[: struct.calcsize(dt.struct)])[0]
    return round(value, 3) if isinstance(value, float) else value


# --- per-protocol schemas (mirror of web/src/protocols.ts) -------------------
PROTOCOL_SCHEMAS: dict[str, dict] = {
    "modbus-tcp": {
        "label": "Modbus TCP",
        "connection": [
            Field("host", "Host", required=True),
            Field("port", "Port", 502, "number"),
            Field("unit_id", "Unit ID", 1, "number"),
        ],
        "address": [
            Field("register", "Register", 0, "number", required=True),
            Field("register_type", "Register type", "holding", options=("holding", "input")),
            Field("quantity", "Quantity", 1, "number"),
        ],
    },
    "opcua": {
        "label": "OPC UA",
        "connection": [
            Field("endpoint_url", "Endpoint URL", "opc.tcp://host:4840", required=True),
        ],
        "address": [
            Field("node_id", "Node ID", "ns=2;s=", required=True),
        ],
    },
    "s7": {
        "label": "Siemens S7 (snap7)",
        "connection": [
            Field("host", "Host", required=True),
            Field("rack", "Rack", 0, "number"),
            Field("slot", "Slot", 1, "number"),
        ],
        "address": [
            Field("area", "Area", "DB", options=("DB", "MK", "PE", "PA")),
            Field("db_number", "DB number", 1, "number"),
            Field("start", "Start byte", 0, "number"),
            Field("size", "Size (bytes)", 4, "number"),
        ],
    },
}

# Protocol aliases accepted from callers -> canonical schema key.
_PROTOCOL_ALIASES = {
    "modbus": "modbus-tcp",
    "modbus-tcp": "modbus-tcp",
    "modbustcp": "modbus-tcp",
    "opcua": "opcua",
    "opc-ua": "opcua",
    "opc.tcp": "opcua",
    "s7": "s7",
    "snap7": "s7",
}


def resolve_protocol(protocol: str | None) -> str | None:
    return _PROTOCOL_ALIASES.get((protocol or "").lower().strip())


def supported_protocols() -> list[str]:
    return list(PROTOCOL_SCHEMAS)


def validate(descriptor: dict) -> list[str]:
    """Return a list of human-readable problems with a connector descriptor
    (empty list == valid). Checks the protocol is supported and that required
    connection / address fields are present. Unknown extra fields are allowed."""
    errors: list[str] = []
    proto = resolve_protocol(descriptor.get("protocol"))
    if proto is None:
        errors.append(
            f"unsupported protocol {descriptor.get('protocol')!r}; "
            f"supported: {', '.join(supported_protocols())}"
        )
        return errors

    schema = PROTOCOL_SCHEMAS[proto]
    conn = descriptor.get("connection") or {}
    for f in schema["connection"]:
        if f.required and conn.get(f.key) in (None, ""):
            errors.append(f"connection.{f.key} is required for {proto}")

    for i, dp in enumerate(descriptor.get("datapoints") or []):
        if not dp.get("name"):
            errors.append(f"datapoints[{i}].name is required")
        addr = dp.get("address") or {}
        for f in schema["address"]:
            if f.required and addr.get(f.key) in (None, ""):
                errors.append(f"datapoints[{i}].address.{f.key} is required for {proto}")
    return errors
