"""
A Class to implement a synchronous MODBUS TCP client connector.
"""

from pymodbus.client import AsyncModbusTcpClient

class AsyncModbusClient:
    """A Modbus Client."""
    def __init__(self, args):
        # Attributes
        self.host = args.get("host", "127.0.0.1")
        self.port = args.get("port", 502)
        self.timeout = args.get("timeout", 5)
        
        self.connected = False

        # Initialise Client
        self.client = AsyncModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)

    # -------------------------
    # Connect / disconnect
    # -------------------------

    async def connect(self):
        if await self.client.connect():
            self.connected = True
            print(f"Connected to Modbus Server at {self.host}:{self.port}")
        else:
            self.connected = False
            print("Failed to connect.")

    async def disconnect(self):
        await self.client.close()
        self.connected = False
        print("Disconnected from modbus server.")

    # -------------------------
    # Read Coils
    # -------------------------

    async def _read_coils(self, reg_address, count):
        if not self.connected:
            raise RuntimeError("Not connected to Modbus server")

        result = await self.client.read_coils(address=reg_address, count=count)
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")
        
        return result.bits

    # -------------------------
    # Read discrete inputs
    # -------------------------

    async def _read_discrete_inputs(self, reg_address, count):
        if not self.connected:
            raise RuntimeError("Not connected to Modbus server")

        result = await self.client.read_discrete_inputs(address=reg_address, count=count)
        
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")

        return result.bits

    # -------------------------
    # Read holding registers
    # -------------------------

    async def _read_holding_registers(self, reg_address, count):
        if not self.connected:
            raise RuntimeError("Not connected to Modbus server")

        result = await self.client.read_holding_registers(address=reg_address, count=count)
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")
        
        return result.registers
    
    # -------------------------
    # Read input registers
    # -------------------------

    async def _read_input_registers(self, reg_address, count):
        if not self.connected:
            raise RuntimeError("Not connected to Modbus server")

        result = await self.client.read_input_registers(address=reg_address, count=count)
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")
        
        return result.registers
    
    # -------------------------
    # Unified read method
    # -------------------------

    async def read(self, args):
        """
        Carry out a read function based on a dictionary of arguments.
        Expects an object: args = { "type" : str, # 'coil', 'discrete', 'holding', 'input'
                                    "reg_address" : int, # register address, default 1
                                    "count" : int, # default 1 }
        Returns a dictionary: data = {  "register1" : value1,
                                        "register2" : value2, ...} 
        """
        
        reg_type = args["type"]
        if not reg_type:
            raise ValueError("Missing 'type' in arguments")
        
        address = args.get("reg_address", 1)
        
        count = args.get("count", 1)
        
        if reg_type == "coil":
            """Read Output Coils."""
            data = await self._read_coils(reg_address=address, count=count)
        elif reg_type == "discrete":
            """Read Input Coils"""
            data = await self._read_discrete_inputs(reg_address=address, count=count)
        elif reg_type == "holding":
            """Read Holding Registers"""
            data = await self._read_holding_registers(reg_address=address, count=count)
        elif reg_type == "input":
            """Read Input Registers"""
            data = await self._read_input_registers(reg_address=address, count=count)
        else:
            """Give en fejl."""
            raise ValueError(f"Invalid register type: {reg_type}")
        
        return {
            str(address + i): value
            for i, value in enumerate(data)
        }
