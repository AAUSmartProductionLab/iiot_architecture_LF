"""
Pydantic data models for the OT adapters.

Each client takes a typed *Config and each read/write takes a typed *Request, so
bad parameters fail fast with a clear ValidationError instead of surfacing as an
obscure protocol error deeper in.
"""

import pyads.constants
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

# ---------------------------
# ADS Data Models
# ---------------------------

class ADSClientConfig(BaseModel):
    # Local Parameters
    local_ip: str = "127.0.0.1"
    local_netid: str = "127.0.0.1.1.1"

    # Target Parameters
    target_ip: str = "192.168.1.10"
    target_netid: str = "192.168.1.10.1.1"
    target_port: int = 851
    target_routename: str | None = None
    username: str | None = None
    password: str | None = None

class ADSReadRequest(BaseModel):
    ads_readtype: Literal["by index", "by name", "list by name"]
    index_group: int = 1
    index_offset: int = 0
    datatype: Literal[
        "BOOL",
        "DINT",
        "INT",
        "LREAL",
        "REAL",
        "SHORT",
        "SINT",
        "UDINT",
        "UINT",
        "USHORT",
        "USINT",
        "STRING",
        "WSTRING"
    ]
    dataname: str | None = None
    datanames: list[str] = Field(default_factory=list)
    array_size: int = 1

# ---------------------------
# HTTP/HTTPS Data Models
# ---------------------------

class HTTPClientConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int | None = None
    path: str = ""
    timeout: int = 4
    protocol: Literal["HTTP", "HTTPS"] = "HTTP"
    cert_path: str | None = None
    verify_ssl: bool = True

# ---------------------------
# Modbus TCP Data Models
# ---------------------------

class ModbusTCPClientConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 502
    unit_id: int = 1
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
    endpoint_url: str
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
