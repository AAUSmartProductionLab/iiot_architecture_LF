"""
Data Classes for the OT adapters.
"""

from dataclasses import dataclass
from typing import Literal, Any, Dict

#---------------------------
# Modbus TCP Data Classes
#---------------------------

@dataclass
class ModbusTCPClientConfig:
    host: str = "127.0.0.1"
    port: int = 502
    timeout: int = 4

@dataclass
class ModbusReadRequest:
    reg_address: int = 1
    type: Literal["coil", "discrete", "holding", "input"]
    count: int = 1
    retries: int = 2

#---------------------------
# OPC UA Data Classes
#---------------------------

@dataclass
class OPCUAClientConfig:
    url: str
    timeout: int = 4

@dataclass
class OPCUAReadRequest:
    node_id: str
    retries: int = 2

@dataclass
class OPCUAWriteRequest:
    node_id: str
    value: Any
    retries: int = 2

#---------------------------
# MQTT Data Classes
#---------------------------

#---------------------------
# Snap7 Data Classes
#---------------------------

@dataclass
class S7ClientConfig:
    host: str
    rack: int = 0
    slot: int = 1

@dataclass
class S7ReadRequest:
    db_number: int
    start: int
    size: int
    datatype: Literal["real", "lreral", "float", "float32", "float64", "int", "dint", "bytes"] = "real"
    retries: int = 2