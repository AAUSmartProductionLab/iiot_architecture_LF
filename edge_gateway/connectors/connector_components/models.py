"""
Pydantic data models for the OT adapters.

Each client takes a typed *Config and each read/write takes a typed *Request, so
bad parameters fail fast with a clear ValidationError instead of surfacing as an
obscure protocol error deeper in.
"""

from typing import Any, Literal

from pydantic import BaseModel

# ---------------------------
# Modbus TCP Data Models
# ---------------------------


class ModbusTCPClientConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 502
    timeout: int = 4


class ModbusReadRequest(BaseModel):
    type: Literal["coil", "discrete", "holding", "input"]
    reg_address: int = 1
    count: int = 1
    retries: int = 2


# ---------------------------
# OPC UA Data Models
# ---------------------------


class OPCUAClientConfig(BaseModel):
    url: str
    timeout: int = 4


class OPCUAReadRequest(BaseModel):
    node_id: str
    retries: int = 2


class OPCUAWriteRequest(BaseModel):
    node_id: str
    value: Any
    retries: int = 2


# ---------------------------
# Snap7 Data Models
# ---------------------------


class S7ClientConfig(BaseModel):
    host: str
    rack: int = 0
    slot: int = 1


class S7ReadRequest(BaseModel):
    db_number: int
    start: int
    size: int
    datatype: Literal[
        "real", "lreal", "float", "float32", "float64", "int", "dint", "bytes"
    ] = "real"
    retries: int = 2
