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

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


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

    register_: int = Field(alias="register")
    register_type: Literal["holding", "input"] = "holding"
    quantity: int = 1


class ModbusDataPoint(DataPoint):
    address: ModbusAddress


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
    db_number: int = 1
    start: int = 0
    size: int = 4


class S7DataPoint(DataPoint):
    address: S7Address


# --- connector variants (discriminated by `protocol`) ------------------------
class _BaseConnector(BaseModel):
    device_key: str
    mqtt: MqttConfig = Field(default_factory=MqttConfig)
    interval: float = 2.0


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
