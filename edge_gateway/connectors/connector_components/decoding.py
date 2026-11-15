"""Pure raw-bytes -> value decoding for the polled protocols (no I/O).

Kept separate from the clients so it can be unit-tested without a PLC.

* S7: big-endian, sized by the S7 datatype (REAL = 4 bytes, LREAL = 8, ...).
* Modbus: big-endian 16-bit registers; multi-register types are combined
  most-significant word first unless word_order="little" (a common vendor
  variant, e.g. many energy meters).
"""

from __future__ import annotations

import struct

# No protocol libraries at module level: config_model imports this module for
# validation, and the gateway-agent image does not install snap7 & co.

# ---------------------------------------------------------------------------
# S7
# ---------------------------------------------------------------------------

# Accepted S7 datatype names -> canonical name. Aliases keep connectors that were
# provisioned with the older names ("float32", "float", ...) working.
S7_ALIASES = {
    "real": "real", "float": "real", "float32": "real",
    "lreal": "lreal", "float64": "lreal",
    "int": "int", "int16": "int", "short": "int",
    "uint": "uint", "uint16": "uint",
    "dint": "dint", "int32": "dint",
    "udint": "udint", "uint32": "udint",
    "sint": "sint", "int8": "sint",
    "usint": "usint", "uint8": "usint", "byte": "usint",
    "word": "word", "dword": "dword",
    "bool": "bool",
    "bytes": "bytes",
}

# Bytes to read per canonical datatype (None = use the datapoint's `size`).
S7_SIZES = {
    "real": 4, "lreal": 8, "int": 2, "uint": 2, "dint": 4, "udint": 4,
    "sint": 1, "usint": 1, "word": 2, "dword": 4, "bool": 1, "bytes": None,
}


def s7_canonical(datatype: str) -> str:
    key = (datatype or "").strip().lower()
    if key not in S7_ALIASES:
        raise ValueError(f"unsupported S7 datatype {datatype!r}; use one of {sorted(set(S7_ALIASES.values()))}")
    return S7_ALIASES[key]


def s7_read_size(datatype: str, size: int | None = None) -> int:
    """Number of bytes to read for this datatype (`size` only matters for 'bytes')."""
    n = S7_SIZES[s7_canonical(datatype)]
    if n is None:
        if not size or size < 1:
            raise ValueError("S7 datatype 'bytes' needs a size >= 1")
        return int(size)
    return n


def _float32(value: float) -> float:
    """Shortest decimal that round-trips the float32 (12.5 not 12.5000000001)."""
    return float(f"{value:.7g}")


def s7_decode(raw: bytes | bytearray, datatype: str, bit: int = 0):
    """Decode bytes read from an S7 area at the datapoint's start offset."""
    import snap7.util as su  # adapter-only dependency

    dt = s7_canonical(datatype)
    buf = bytearray(raw)
    if dt == "real":
        return _float32(su.get_real(buf, 0))
    if dt == "lreal":
        return su.get_lreal(buf, 0)
    if dt == "int":
        return su.get_int(buf, 0)
    if dt in ("uint", "word"):
        return su.get_uint(buf, 0) if dt == "uint" else su.get_word(buf, 0)
    if dt == "dint":
        return su.get_dint(buf, 0)
    if dt in ("udint", "dword"):
        return su.get_udint(buf, 0) if dt == "udint" else su.get_dword(buf, 0)
    if dt == "sint":
        return su.get_sint(buf, 0)
    if dt == "usint":
        return su.get_usint(buf, 0)
    if dt == "bool":
        if not 0 <= bit <= 7:
            raise ValueError(f"S7 bool bit must be 0-7, got {bit}")
        return bool(su.get_bool(buf, 0, bit))
    if dt == "bytes":
        return buf.hex()
    raise ValueError(f"unhandled S7 datatype {dt}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Modbus
# ---------------------------------------------------------------------------

# datatype -> (registers, struct format for the big-endian byte string)
MODBUS_TYPES = {
    "int16": (1, ">h"),
    "uint16": (1, ">H"),
    "int32": (2, ">i"),
    "uint32": (2, ">I"),
    "float32": (2, ">f"),
    "int64": (4, ">q"),
    "uint64": (4, ">Q"),
    "float64": (4, ">d"),
}
MODBUS_BIT_TYPES = {"bool"}  # coils / discrete inputs


def modbus_register_count(datatype: str) -> int:
    dt = (datatype or "").lower()
    if dt in MODBUS_BIT_TYPES:
        return 1
    if dt not in MODBUS_TYPES:
        raise ValueError(
            f"unsupported Modbus datatype {datatype!r}; use one of "
            f"{sorted(MODBUS_TYPES) + sorted(MODBUS_BIT_TYPES)}"
        )
    return MODBUS_TYPES[dt][0]


def modbus_decode(registers: list[int], datatype: str, word_order: str = "big"):
    """Combine 16-bit registers into a typed value.

    word_order "big" = first register holds the most-significant word (Modbus
    spec / Modicon); "little" = word-swapped, as used by many meters/drives.
    """
    dt = (datatype or "").lower()
    if dt in MODBUS_BIT_TYPES:
        return bool(registers[0])
    count, fmt = MODBUS_TYPES[dt]
    words = list(registers[:count])
    if len(words) != count:
        raise ValueError(f"{datatype} needs {count} registers, got {len(registers)}")
    if word_order == "little":
        words.reverse()
    elif word_order != "big":
        raise ValueError(f"word_order must be 'big' or 'little', got {word_order!r}")
    value = struct.unpack(fmt, struct.pack(f">{count}H", *(w & 0xFFFF for w in words)))[0]
    return _float32(value) if dt == "float32" else value
