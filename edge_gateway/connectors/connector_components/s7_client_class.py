"""A thin Siemens S7 client (snap7) with a generic read() and a polling subscribe()."""

import asyncio
import logging

from snap7.client import Client
from snap7.type import Area

from .decoding import s7_decode, s7_read_size
from .models import S7ClientConfig, S7ReadRequest

logger = logging.getLogger(__name__)

_AREAS = {"DB": Area.DB, "MK": Area.MK, "PE": Area.PE, "PA": Area.PA}


class S7Client:
    """An S7 client. Datapoints carry their address under dp['address']:
    {area: 'DB'|'MK'|'PE'|'PA', db_number, start, bit, size}; the datatype comes
    from dp['datatype'] and fixes how many bytes are read (size only matters for
    'bytes', bit only for 'bool')."""

    def __init__(self, config: S7ClientConfig):
        self.host = config.host
        self.rack = config.rack
        self.slot = config.slot

        self.client = Client()
        self.connected = False

    # ----------------------------
    # Connection / Disconnection
    # ----------------------------

    async def connect(self):
        # snap7 is blocking: run it in a worker thread.
        await asyncio.to_thread(self.client.connect, self.host, self.rack, self.slot)
        self.connected = await asyncio.to_thread(self.client.get_connected)
        if self.connected:
            logger.info(f"Connected to S7 {self.host} rack {self.rack} slot {self.slot}")
        else:
            raise ConnectionError(f"Failed to connect to S7 {self.host}")

    async def disconnect(self):
        if self.connected:
            try:
                await asyncio.to_thread(self.client.disconnect)
            finally:
                self.connected = False

    def _ensure_connected(self):
        if not self.connected:
            raise RuntimeError("Not connected to S7 PLC")

    # ----------------------------
    # Read
    # ----------------------------

    async def read(self, request: S7ReadRequest):
        self._ensure_connected()
        size = s7_read_size(request.datatype, request.size)
        db_number = request.db_number if request.area == "DB" else 0
        raw = await asyncio.to_thread(
            self.client.read_area, _AREAS[request.area], db_number, request.start, size
        )
        value = s7_decode(raw, request.datatype, request.bit)
        key = f"{request.area}{db_number if request.area == 'DB' else ''}.{request.start}"
        return {key: value}

    # ----------------------------
    # Subscribe (poll loop)
    # ----------------------------

    @staticmethod
    def _request_for(dp: dict) -> S7ReadRequest:
        addr = dp.get("address") or {}
        return S7ReadRequest(
            area=addr.get("area", "DB"),
            db_number=int(addr.get("db_number", 1)),
            start=int(addr.get("start", 0)),
            bit=int(addr.get("bit", 0)),
            size=int(addr.get("size", 0) or 0),
            datatype=dp.get("datatype", "real"),
        )

    async def subscribe(self, datapoints, on_value, interval=2.0):
        """Read every datapoint once per `interval` seconds and hand each value to
        on_value(dp, value). Reporting only on change is the Connector's job.

        A datapoint with an invalid address is logged once and skipped; read
        errors are logged per poll. A lost connection is raised so the Connector
        reconnects instead of logging errors forever."""
        requests = []
        for dp in datapoints:
            try:
                request = self._request_for(dp)
                s7_read_size(request.datatype, request.size)  # validate datatype up front
                requests.append((dp, request))
            except Exception as e:  # noqa: BLE001 - bad config for one datapoint
                logger.error(f"S7 datapoint {dp.get('name')} skipped: {e}")

        while True:
            for dp, request in requests:
                try:
                    result = await self.read(request)
                    on_value(dp, next(iter(result.values())))
                except Exception as e:  # noqa: BLE001
                    if not await asyncio.to_thread(self.client.get_connected):
                        self.connected = False
                        raise ConnectionError(f"S7 connection lost: {e}") from e
                    logger.error(f"S7 read failed for {dp.get('name')}: {e}")
            await asyncio.sleep(interval)
