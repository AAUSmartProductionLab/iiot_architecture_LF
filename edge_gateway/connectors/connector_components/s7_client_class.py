"""A thin Siemens S7 client (snap7) with a generic read(dp).

Datapoints carry their address under dp['address']:
    {area: 'DB'|'MK'|'PE'|'PA', db_number, start, size}
and dp['datatype'] (real/int/dint/…) drives decoding. Mirrors the sync
connect()/read(dp)/disconnect() interface of the other connector clients.
"""

import snap7

from ..schemas import decode

try:  # snap7 3.x exposes areas as an enum on snap7.type
    from snap7.type import Area as _Area

    _AREA_MAP = {"DB": _Area.DB, "MK": _Area.MK, "PE": _Area.PE, "PA": _Area.PA}
except Exception:  # pragma: no cover - older snap7 fallback
    _AREA_MAP = {}


class S7Client:
    def __init__(self, host, rack=0, slot=1):
        self.host = host
        self.rack = int(rack)
        self.slot = int(slot)
        self.client = snap7.client.Client()
        self.connected = False

    def connect(self):
        self.client.connect(self.host, self.rack, self.slot)
        self.connected = self.client.get_connected()
        print(f"Connected to S7 {self.host} rack {self.rack} slot {self.slot}")

    def read(self, dp):
        a = dp.get("address", {}) or {}
        area = str(a.get("area", "DB")).upper()
        db = int(a.get("db_number", 1))
        start = int(a.get("start", 0))
        size = int(a.get("size", 4))
        datatype = dp.get("datatype")

        if area == "DB":
            raw = bytes(self.client.db_read(db, start, size))
        elif area in _AREA_MAP:
            # Non-DB areas (merker/inputs/outputs): db number is unused (0).
            raw = bytes(self.client.read_area(_AREA_MAP[area], 0, start, size))
        else:
            raise ValueError(f"unsupported S7 area: {area}")

        # Prefer the shared decoder; fall back to snap7 helpers for legacy names.
        from ..schemas import resolve_datatype

        if resolve_datatype(datatype) is not None:
            return decode(raw, datatype)
        dt = (datatype or "real").lower()
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
