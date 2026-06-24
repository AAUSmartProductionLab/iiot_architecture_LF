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
