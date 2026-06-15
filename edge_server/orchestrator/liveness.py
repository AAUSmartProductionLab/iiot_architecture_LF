"""Active liveness monitor.

mDNS finds gateways but is unreliable at detecting loss (TTL expiry is slow), so
liveness is polled: every `interval` seconds GET /api/health on each known
gateway and mark it online/offline. Discovery and liveness are separate concerns.
"""

import asyncio
import logging

import httpx

from .registry import registry

log = logging.getLogger("liveness")


class LivenessMonitor:
    def __init__(self, interval: float = 20.0, timeout: float = 2.0):
        self.interval = interval
        self.timeout = timeout
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while True:
                for rec in registry.list():
                    gateway_id = rec.get("gateway_id")
                    ip, port = rec.get("ip"), rec.get("port")
                    if not gateway_id or not ip or not port:
                        continue
                    url = f"http://{ip}:{port}/api/health"
                    try:
                        r = await client.get(url)
                        if r.status_code == 200:
                            registry.touch(gateway_id)
                        else:
                            registry.mark_offline(gateway_id)
                    except Exception:
                        registry.mark_offline(gateway_id)
                await asyncio.sleep(self.interval)
