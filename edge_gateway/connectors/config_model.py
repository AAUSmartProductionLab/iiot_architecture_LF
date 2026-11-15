"""Pydantic data model for a connector — the deserialized CONNECTOR_CONFIG.

Each protocol declares its own typed `connection` params and per-datapoint
`address` params, so "what parameters do we get for this protocol?" is answered
(and enforced: required fields, allowed options) by these models. The adapter is
handed one connector as JSON — via the CONNECTOR_CONFIG env var the gateway-agent
sets, or a config.json file for local runs. The `protocol` field is the
discriminator: it selects the variant, which fixes the shape of `connection` and
each datapoint's `address`. An unsupported protocol fails validation up front.

Add a protocol = add a *Connection / *Address / *Connector trio and extend the
ConnectorConfig union below.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .connector_components.decoding import modbus_register_count, s7_read_size


# --- shared ------------------------------------------------------------------
class MqttConfig(BaseModel):
    broker_host: str = "localhost"
    broker_port: int = 1883


class DataPoint(BaseModel):
    """Common datapoint metadata; `address` is typed per protocol in subclasses."""

    name: str
    datatype: str = "float32"
    unit: str = ""
    local_topic: str = ""


# --- Modbus TCP --------------------------------------------------------------
class ModbusConnection(BaseModel):
    host: str
    port: int = 502
    unit_id: int = 1


class ModbusAddress(BaseModel):
    # `register` is a method on pydantic's BaseModel, so the attribute is named
    # register_ and aliased back to the wire/JSON name "register".
    model_config = ConfigDict(populate_by_name=True)

    # 0-based protocol address (what goes on the wire). Modicon notation maps as
    # 40001 -> holding 0, 30001 -> input 0, 00001 -> coil 0, 10001 -> discrete 0.
    register_: int = Field(alias="register", ge=0, le=65535)
    register_type: Literal["holding", "input", "coil", "discrete"] = "holding"
    # Multi-register values: "big" = most-significant word first (spec default),
    # "little" = word-swapped (common on meters/drives).
    word_order: Literal["big", "little"] = "big"
    # Deprecated: the register count is derived from the datatype. Accepted (and
    # ignored) so connectors provisioned before this change still validate.
    quantity: int | None = None


class ModbusDataPoint(DataPoint):
    datatype: str = "float32"
    address: ModbusAddress

    @model_validator(mode="after")
    def _check_datatype(self):
        bit_register = self.address.register_type in ("coil", "discrete")
        if bit_register and self.datatype != "bool":
            raise ValueError(f"{self.address.register_type} registers hold bits: use datatype 'bool'")
        if not bit_register:
            modbus_register_count(self.datatype)  # raises on an unsupported datatype
            if self.datatype == "bool":
                raise ValueError("datatype 'bool' needs register_type 'coil' or 'discrete'")
        return self


# --- OPC UA ------------------------------------------------------------------
class OpcUaConnection(BaseModel):
    endpoint_url: str


class OpcUaAddress(BaseModel):
    node_id: str


class OpcUaDataPoint(DataPoint):
    address: OpcUaAddress


# --- Siemens S7 (snap7) ------------------------------------------------------
class S7Connection(BaseModel):
    host: str
    rack: int = 0
    slot: int = 1


class S7Address(BaseModel):
    area: Literal["DB", "MK", "PE", "PA"] = "DB"
    db_number: int = 1  # only used for area DB
    start: int = Field(default=0, ge=0)  # byte offset
    bit: int = Field(default=0, ge=0, le=7)  # only used for datatype bool
    # Only used for datatype bytes; every other datatype has a fixed size.
    size: int = Field(default=0, ge=0)


class S7DataPoint(DataPoint):
    datatype: str = "real"
    address: S7Address

    @model_validator(mode="after")
    def _check_datatype(self):
        s7_read_size(self.datatype, self.address.size)  # raises on bad datatype / missing size
        return self


# --- connector variants (discriminated by `protocol`) ------------------------
class _BaseConnector(BaseModel):
    device_key: str
    mqtt: MqttConfig = Field(default_factory=MqttConfig)
    interval: float = Field(default=2.0, ge=0.05)  # seconds between polls


class ModbusConnector(_BaseConnector):
    protocol: Literal["modbus-tcp"]
    connection: ModbusConnection
    datapoints: list[ModbusDataPoint] = Field(default_factory=list)


class OpcUaConnector(_BaseConnector):
    protocol: Literal["opcua"]
    connection: OpcUaConnection
    datapoints: list[OpcUaDataPoint] = Field(default_factory=list)


class S7Connector(_BaseConnector):
    protocol: Literal["s7"]
    connection: S7Connection
    datapoints: list[S7DataPoint] = Field(default_factory=list)


ConnectorConfig = Annotated[
    Union[ModbusConnector, OpcUaConnector, S7Connector],
    Field(discriminator="protocol"),
]

_ADAPTER = TypeAdapter(ConnectorConfig)


def parse_connector(data: dict | str | bytes) -> ConnectorConfig:
    """Deserialize + validate a connector config (dict or JSON text) into its
    protocol-specific model. Raises pydantic.ValidationError on bad input."""
    if isinstance(data, (str, bytes, bytearray)):
        return _ADAPTER.validate_json(data)
    return _ADAPTER.validate_python(data)
