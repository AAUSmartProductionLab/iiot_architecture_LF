"""
A simple modbus tcp server to test modbus functionality with
"""

from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusServerContext,
    ModbusSequentialDataBlock
)

# Create data store
store = ModbusDeviceContext(
    di=ModbusSequentialDataBlock(1, [0]*100),  # Discrete Inputs
    co=ModbusSequentialDataBlock(1, [0]*100),  # Coils
    hr=ModbusSequentialDataBlock(1, [0]*100),  # Holding Registers
    ir=ModbusSequentialDataBlock(1, [0]*100),  # Input Registers
)

context = ModbusServerContext(devices=store, single=True)

# Start server
try:
    print("Starting Modbus Server...")
    StartTcpServer(
        context,
        address=("127.0.0.1", 5020)
    )
except KeyboardInterrupt:
    print("Shutting down server...")