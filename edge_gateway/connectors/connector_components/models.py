"""
Pydantic data models for the OT adapters.

Each client takes a typed *Config and each read/write takes a typed *Request, so
bad parameters fail fast with a clear ValidationError instead of surfacing as an
obscure protocol error deeper in.

Keep this module free of protocol-library imports: every adapter imports it, so
an optional dependency here (e.g. pyads for the not-yet-wired ADS client) would
crash the adapter for all protocols when that library isn't installed.
"""

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
    reg_address: int = 0  # 0-based protocol address
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
    area: Literal["DB", "MK", "PE", "PA"] = "DB"
    db_number: int = 1  # only used for area DB
    start: int = Field(ge=0)
    bit: int = Field(default=0, ge=0, le=7)  # only used for datatype bool
    size: int = 0  # only used for datatype bytes; otherwise derived from datatype
    datatype: str = "real"  # validated by decoding.s7_canonical
    retries: int = 2
