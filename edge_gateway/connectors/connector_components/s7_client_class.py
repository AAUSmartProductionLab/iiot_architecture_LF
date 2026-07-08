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

    async def connect(self):
        # Run connect in thread to avoid blocking
        await asyncio.to_thread(self.client.connect, self.host, self.rack, self.slot)
        self.connected = await asyncio.to_thread(self.client.get_connected)
        if self.connected:
            logger.info(f"Connected to S7 {self.host} rack {self.rack} slot {self.slot}")
        else:
            raise ConnectionError(f"Failed to connect to S7 {self.host}")

    async def disconnect(self):
        try:
            self._ensure_connected()
            await asyncio.to_thread(self.client.disconnect)
        finally:
            self.connected = False
        
    def _ensure_connected(self):
        if not self.connected:
            raise RuntimeError("Not connected to S7 PLC")

    #----------------------------
    # Read
    #----------------------------

    async def read(self, request: S7ReadRequest):
        self._ensure_connected()
        
        raw = await asyncio.to_thread(
            self.client.db_read,
            request.db_number,
            request.start,
            request.size
        )

        datatype = request.datatype.lower()
        value = None

        if datatype in ("real", "lreal", "float", "float32", "float64"):
            value = round(su.get_real(raw, 0), 3)
        elif datatype in ("int", "int16", "short"):
            value = su.get_int(raw, 0)
        elif datatype in ("dint", "int32"):
            value = su.get_dint(raw, 0)
        else:
            logger.warning(f"Unsupported datatype:{datatype}")
        
        key = f"DB{request.db_number}.{request.start}"

        return {key: value}

    #----------------------------
    # Subscribe
    #----------------------------

    async def subscribe(self, datapoints, on_value, interval=2.0):
        """Poll each datapoint every `interval`s and hand the value to on_value.

        An initial read of all datapoints fires immediately on subscription so
        current values are published without waiting for the first tick.
        snap7 is blocking, so reads run in a worker thread to stay async-friendly."""

        def _build_request(dp: dict) -> S7ReadRequest | None:
            addr = dp.get("address", {}) or {}
            db = addr.get("db_number")
            if db is None:
                logger.error(f"S7 missing db_number for datapoint {dp.get('name')}")
                return None
            return S7ReadRequest(
                db_number=int(db),
                start=int(addr.get("start", 0)),
                size=int(addr.get("size", 4)),
                datatype=dp.get("datatype", "real"),
            )

        # ── initial read: publish current values right away ──────────────
        for dp in datapoints:
            try:
                request = _build_request(dp)
                if request is None:
                    continue
                result = await self.read(request)
                value = next(iter(result.values())) if result else None
                on_value(dp, value)
            except Exception as e:
                logger.error(f"S7 initial read failed for {dp.get('name')}: {e}")

        # ── polling loop ─────────────────────────────────────────────────
        while True:
            for dp in datapoints:
                try:
                    request = _build_request(dp)
                    if request is None:
                        continue
                    result = await self.read(request)
                    value = next(iter(result.values())) if result else None
                    on_value(dp, value)
                except Exception as e:
                    logger.error(f"S7 read failed for {dp.get('name')}: {e}")
            await asyncio.sleep(interval)
