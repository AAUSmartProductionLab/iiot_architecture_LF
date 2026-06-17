"""A thin Siemens S7 client (snap7) with a generic read_datapoint()."""

import snap7
import snap7.util as su
from snap7.client import Client


class S7Client:
    """An S7 client. Datapoints carry their address under dp['address']:
    {area: 'DB', db_number, start, size}; datatype from dp['datatype']."""

    def __init__(self, host, rack=0, slot=1):
        self.host = host
        self.rack = int(rack)
        self.slot = int(slot)
        self.client = Client()
        self.connected = False

    def connect(self):
        self.client.connect(self.host, self.rack, self.slot)
        self.connected = self.client.get_connected()
        print(f"Connected to S7 {self.host} rack {self.rack} slot {self.slot}")

    def read_datapoint(self, dp):
        a = dp.get("address", {}) or {}
        db = int(a.get("db_number", 1))
        start = int(a.get("start", 0))
        size = int(a.get("size", 4))
        raw = self.client.db_read(db, start, size)
        dt = (dp.get("datatype") or "real").lower()
        if dt in ("real", "float", "float32", "float64"):
            return round(su.get_real(raw, 0), 3)
        if dt in ("int", "int16", "short"):
            return su.get_int(raw, 0)
        if dt in ("dint", "int32"):
            return su.get_dint(raw, 0)
        return list(raw)

    def disconnect(self):
        try:
            self.client.disconnect()
        except Exception:
            pass
        self.connected = False
