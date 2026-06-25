"""A thin Siemens S7 client (snap7) with a generic read()."""

import asyncio
import logging
import snap7.util as su
from snap7.client import Client
from .models import S7ClientConfig, S7ReadRequest

logger = logging.getLogger(__name__)

class S7Client:
    """An S7 client. Datapoints carry their address under dp['address']:
    {area: 'DB', db_number, start, size}; datatype from dp['datatype']."""

    def __init__(self, config: S7ClientConfig):
        self.host = config.host
        self.rack = config.rack
        self.slot = config.slot

        self.client = Client()
        self.connected = False

    #----------------------------
    # Connection / Disconnection
    #----------------------------

    def connect(self):
        self.client.connect(self.host, self.rack, self.slot)
        self.connected = self.client.get_connected()
        logger.info(f"Connected to S7 {self.host} rack {self.rack} slot {self.slot}")

    def disconnect(self):
        try:
            self._ensure_connected()
            self.client.disconnect()
        finally:
            self.connected = False
        
    def _ensure_connected(self):
        if not self.connected:
            raise RuntimeError("Not connected to S7 PLC")

    #----------------------------
    # Read
    #----------------------------

    def read(self, request: S7ReadRequest):
        self._ensure_connected()
        
        raw = self.client.db_read(
            request.db_number,
            request.start,
            request.size
        )

        datatype = request.datatype.lower()

        if datatype in ("real", "lreal", "float", "float32", "float64"):
            value = round(su.get_real(raw, 0), 3)
        if datatype in ("int", "int16", "short"):
            value = su.get_int(raw, 0)
        if datatype in ("dint", "int32"):
            value = su.get_dint(raw, 0)
        
        key = f"DB{request.db_number}.{request.start}"

        return {key: value}

    #----------------------------
    # Subscribe
    #----------------------------

    async def subscribe(self, datapoints, on_value, interval=2.0):
        """Poll each datapoint every `interval`s and hand the value to on_value.
        snap7 is blocking, so reads run in a worker thread to stay async-friendly."""
        while True:
            for dp in datapoints:
                try:
                    addr = dp.get("address", {}) or {}
                    request = S7ReadRequest(
                        db_number=int(addr.get("db_number", 1)),
                        start=int(addr.get("start", 0)),
                        size=int(addr.get("size", 4)),
                        datatype=dp.get("datatype", "real"),
                    )
                    result = await asyncio.to_thread(self.read, request)
                    value = next(iter(result.values())) if result else None
                    on_value(dp, value)
                except Exception as e:
                    logger.error(f"S7 read failed for {dp.get('name')}: {e}")
            await asyncio.sleep(interval)
