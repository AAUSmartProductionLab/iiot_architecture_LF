"""
A Class to implement a synchronous MODBUS TCP client connector.
"""

from pymodbus.client import ModbusTcpClient

class ModbusClient:
    """A Modbus Client."""
    def __init__(self, host, port=502, timeout=5):
        # Attributes
        self.host = host
        self.port = port
        self.timeout = timeout
        self.connected = False
        #Initialise Client
        self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)

    def connect(self):
        if self.client.connect():
            self.connected = True
            print(f"Connected to Modbus Server at {self.host}:{self.port}")
        else:
            self.connected = False
            print("Failed to connect.")

    def read(self, func_code, reg_address, count):
        """Carry out a read function."""
        if func_code == "FC1":
            """Read Output Coils."""
        elif func_code == "FC2":
            """Read Input Coils"""
        elif func_code == "FC3":
            """Read Holding Registers"""
            self.read_holding_registers(reg_address=reg_address, count=count)
        elif func_code == "FC4":
            """Read Input Registers"""
        else:
            """Give en fejl."""
            print("Not a valid read function code.")

    def read_holding_registers(self, reg_address, count):
        if not self.connected:
            print("Not connected to Modbus server.")
            return None

        result = self.client.read_holding_registers(address=reg_address, count=count)
        
        if result is None or result.isError():
            print(f"Modbus error: {result}")
            return None
        
        return result.registers
    
    def disconnect(self):
        self.client.close()
        self.connected = False
        print("Disconnected from modbus server.")
    
