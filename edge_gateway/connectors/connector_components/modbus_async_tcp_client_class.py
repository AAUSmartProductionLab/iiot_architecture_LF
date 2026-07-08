"""
A Class to implement a synchronous MODBUS TCP client connector.
"""

from pymodbus.client import AsyncModbusTcpClient
from .models import ModbusTCPClientConfig, ModbusReadRequest
import logging
import asyncio 

logger = logging.getLogger(__name__)

class AsyncModbusClient:
    """A Modbus Client."""
    def __init__(self, config: ModbusTCPClientConfig):
        # Attributes
        self.host = config.host
        self.port = config.port
        self.timeout = config.timeout
        
        self.connected = False

        # Initialise Client
        self.client = AsyncModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)

    # -------------------------
    # Connect / disconnect
    # -------------------------

    async def connect(self):
        if await self.client.connect():
            self.connected = True
            logger.info(f"Connected to Modbus Server at {self.host}:{self.port}")
        else:
            self.connected = False
            logger.error("Failed to connect.")

    async def disconnect(self):
        if self.client is None:
            logger.warning("Attempted to disconnect, but client is None.")
            self.connected = False
            return
        try:
            self.client.close()
        except Exception as e:
            logger.error(f"Error while closing Modbus client: {e}")
        finally:
            self.connected = False
            logger.info("Disconnected from modbus server.")

    # -------------------------
    # Read Coils
    # -------------------------

    async def _read_coils(self, reg_address, count):
        result = await self.client.read_coils(address=reg_address, count=count)
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")
        
        return result.bits

    # -------------------------
    # Read discrete inputs
    # -------------------------

    async def _read_discrete_inputs(self, reg_address, count):
        result = await self.client.read_discrete_inputs(address=reg_address, count=count)
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")

        return result.bits

    # -------------------------
    # Read holding registers
    # -------------------------

    async def _read_holding_registers(self, reg_address, count):
        result = await self.client.read_holding_registers(address=reg_address, count=count)
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")
        
        return result.registers
    
    # -------------------------
    # Read input registers
    # -------------------------

    async def _read_input_registers(self, reg_address, count):
        result = await self.client.read_input_registers(address=reg_address, count=count)
        
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")
        
        return result.registers
    
    # -------------------------
    # Unified read method
    # -------------------------

    async def _read(self, request: ModbusReadRequest):
        """
        Carry out a read function based on a ModbusReadRequest instance.
        
        Returns a dictionary: data = {  "register1" : value1,
                                        "register2" : value2, ...} 
        """
        # Check connection
        if not self.connected:
            raise RuntimeError("Not connected to Modbus server")

        # Read values from request arguments to local variables
        reg_type = request.type
        reg_address = request.reg_address
        count = request.count
        
        if reg_type == "coil":
            # Read Output Coils.
            data = await self._read_coils(reg_address=reg_address, count=count)
        elif reg_type == "discrete":
            # Read Input Coils
            data = await self._read_discrete_inputs(reg_address=reg_address, count=count)
        elif reg_type == "holding":
            # Read Holding Registers
            data = await self._read_holding_registers(reg_address=reg_address, count=count)
        elif reg_type == "input":
            # Read Input Registers
            data = await self._read_input_registers(reg_address=reg_address, count=count)
        else:
            # Raise an error
            raise ValueError(f"Invalid register type: {reg_type}")
        
        return {
            str(reg_address + i): value
            for i, value in enumerate(data)
        }

    # -------------------------
    # Safe read wrapper method
    # -------------------------
   
    async def safe_read(self, request: ModbusReadRequest):
        for i in range(request.retries):
            try:
                return await self._read(request)
            except Exception as e:
                logger.warning(f"Read attempt {i+1} failed: {e}")
                if i == request.retries - 1:
                    raise
                await self.disconnect()
                await asyncio.sleep(0.2)
                await self.connect()

    # -------------------------
    # Subscribe (poll loop)
    # -------------------------

    async def subscribe(self, datapoints, on_value, interval=2.0):
        """Poll each datapoint every `interval`s and hand its value to on_value.

        An initial read fires immediately on subscription. dp's register address
        and type are read from dp['address']['register'] and
        dp['address']['register_type']."""
        # ── initial read ──────────────────────────────────────────────
        for dp in datapoints:
            try:
                result = await self._read_from_dp(dp)
                value = next(iter(result.values())) if result else None
                on_value(dp, value)
            except Exception as e:
                logger.error(f"Modbus initial read failed for {dp.get('name')}: {e}")

        # ── polling loop ──────────────────────────────────────────────
        while True:
            for dp in datapoints:
                try:
                    result = await self._read_from_dp(dp)
                    value = next(iter(result.values())) if result else None
                    on_value(dp, value)
                except Exception as e:
                    logger.error(f"Modbus read failed for {dp.get('name')}: {e}")
            await asyncio.sleep(interval)

    async def _read_from_dp(self, dp: dict):
        """Build a ModbusReadRequest from a datapoint dict and read via safe_read."""
        addr = dp.get("address", {}) or {}
        request = ModbusReadRequest(
            type=addr.get("register_type", "holding"),
            reg_address=int(addr.get("register", 1)),
            count=int(addr.get("quantity", 1)),
        )
        return await self.safe_read(request)