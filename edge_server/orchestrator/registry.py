"""Ephemeral in-memory liveness registry ("who is online").

Tracks discovery state only (reachability, address, cached last manifest);
semantic data lives in BaSyx. Lost on restart, rebuilt by re-discovery. Accessed
only from the event loop, so a plain dict suffices.
"""

import time


class Registry:
    def __init__(self) -> None:
        self._gw: dict[str, dict] = {}  # gateway_id -> record

    def upsert(self, gateway_id: str, **fields) -> dict:
        rec = self._gw.get(gateway_id, {"gateway_id": gateway_id})
        rec.update(fields)
        rec["last_seen"] = time.time()
        rec["online"] = True
        self._gw[gateway_id] = rec
        return rec

    def touch(self, gateway_id: str) -> None:
        """Refresh liveness for an already-known gateway (used by the health sweep)."""
        rec = self._gw.get(gateway_id)
        if rec:
            rec["last_seen"] = time.time()
            rec["online"] = True

    def mark_offline(self, gateway_id: str) -> None:
        if gateway_id in self._gw:
            self._gw[gateway_id]["online"] = False

    def get(self, gateway_id: str) -> dict | None:
        return self._gw.get(gateway_id)

    def list(self) -> list[dict]:
        return list(self._gw.values())


registry = Registry()
