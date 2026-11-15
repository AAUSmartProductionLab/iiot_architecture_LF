"""
An asynchronous Modbus TCP client connector (pymodbus 3.x).
"""

import asyncio
import inspect
import logging

from pymodbus.client import AsyncModbusTcpClient

from .decoding import modbus_decode, modbus_register_count
from .models import ModbusReadRequest, ModbusTCPClientConfig

logger = logging.getLogger(__name__)


def _unit_kwarg() -> str:
    """Name of the unit-id keyword in this pymodbus version.

    pymodbus renamed `slave=` to `device_id=` in 3.10 (and dropped `slave` later),
    so resolve it once from the installed library instead of hard-coding either.
    """
    params = inspect.signature(AsyncModbusTcpClient.read_holding_registers).parameters
    return "device_id" if "device_id" in params else "slave"


_UNIT = _unit_kwarg()


class AsyncModbusClient:
    """A Modbus TCP client. Datapoints carry their address under dp['address']:
    {register (0-based), register_type, word_order}; dp['datatype'] fixes how many
    registers are read and how they are decoded."""

    def __init__(self, config: ModbusTCPClientConfig):
        self.host = config.host
        self.port = config.port
        self.timeout = config.timeout
        self.unit_id = config.unit_id
        self.connected = False

        # NOTE: the pymodbus client is *not* created here. pymodbus 3.x grabs the
        # running event loop at construction time, so building it in __init__
        # fails with "no running event loop" when this class is instantiated
        # before asyncio.run() starts (e.g. inside the synchronous
        # Connector.__init__). It is created lazily in connect() instead.
        self.client = None

    # -------------------------
    # Connect / disconnect
    # -------------------------

    async def connect(self):
        if self.client is None:
            self.client = AsyncModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)
        if await self.client.connect():
            self.connected = True
            logger.info(f"Connected to Modbus Server at {self.host}:{self.port}")
        else:
            self.connected = False
            # Raise so the Connector reports CONNECT_FAILED and retries, instead of
            # logging CONNECTED for a device it never reached.
            raise ConnectionError(f"could not connect to Modbus server {self.host}:{self.port}")

    async def disconnect(self):
        if self.client is None:
            self.connected = False
            return
        try:
            self.client.close()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error while closing Modbus client: {e}")
        finally:
            self.connected = False
            logger.info("Disconnected from modbus server.")

    # -------------------------
    # Read
    # -------------------------

    async def _read(self, request: ModbusReadRequest) -> list:
        """Raw read: a list of 16-bit registers, or of bits for coil/discrete."""
        if not self.connected:
            raise RuntimeError("Not connected to Modbus server")
        readers = {
            "coil": (self.client.read_coils, "bits"),
            "discrete": (self.client.read_discrete_inputs, "bits"),
            "holding": (self.client.read_holding_registers, "registers"),
            "input": (self.client.read_input_registers, "registers"),
        }
        if request.type not in readers:
            raise ValueError(f"Invalid register type: {request.type}")
        fn, attr = readers[request.type]
        result = await fn(address=request.reg_address, count=request.count, **{_UNIT: self.unit_id})
        if result is None or result.isError():
            raise RuntimeError(f"Modbus error: {result}")
        return list(getattr(result, attr))[: request.count]

    async def safe_read(self, request: ModbusReadRequest) -> list:
        """_read with reconnect-and-retry on failure."""
        for i in range(request.retries):
            try:
                return await self._read(request)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Read attempt {i + 1} failed: {e}")
                if i == request.retries - 1:
                    raise
                await self.disconnect()
                await asyncio.sleep(0.2)
                try:
                    await self.connect()
                except ConnectionError:
                    pass  # the next attempt raises "Not connected"

    async def read_datapoint(self, dp: dict):
        """Read and decode one datapoint."""
        addr = dp.get("address", {}) or {}
        datatype = dp.get("datatype", "float32")
        request = ModbusReadRequest(
            type=addr.get("register_type", "holding"),
            reg_address=int(addr.get("register", 0)),
            count=modbus_register_count(datatype),
        )
        raw = await self.safe_read(request)
        return modbus_decode(raw, datatype, addr.get("word_order", "big"))

    # -------------------------
    # Subscribe (poll loop)
    # -------------------------

    async def subscribe(self, datapoints, on_value, interval=2.0):
        """Read every datapoint once per `interval` seconds and hand each decoded
        value to on_value(dp, value). A connection that can't be re-established
        is raised so the Connector reconnects with backoff."""
        while True:
            for dp in datapoints:
                try:
                    on_value(dp, await self.read_datapoint(dp))
                except Exception as e:  # noqa: BLE001
                    if not self.connected:
                        raise ConnectionError(f"Modbus connection lost: {e}") from e
                    logger.error(f"Modbus read failed for {dp.get('name')}: {e}")
            await asyncio.sleep(interval)
