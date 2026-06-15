"""mDNS advertisement (AsyncZeroconf).

Announces `_aasgw._tcp.local.` so the server's ServiceBrowser finds the gateway.
The FastAPI port is a ServiceInfo field; TXT carries string metadata only.
"""

import socket

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

SERVICE_TYPE = "_aasgw._tcp.local."


def _primary_ip() -> str:
    """Best-effort LAN IP (avoids returning 127.0.0.1 on multi-homed hosts)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packets sent; just selects the egress iface
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class Advertiser:
    """Registers/unregisters this gateway as an mDNS service."""

    def __init__(self, gateway_id: str, port: int):
        self.gateway_id = gateway_id
        self.port = port
        self.azc: AsyncZeroconf | None = None
        self.info: ServiceInfo | None = None

    def _service_info(self) -> ServiceInfo:
        ip = _primary_ip()
        return ServiceInfo(
            SERVICE_TYPE,
            f"{self.gateway_id}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=self.port,
            properties={
                "gateway_id": self.gateway_id,
                "manifest_path": "/api/manifest",
                "schema": "1",
            },
            server=f"{self.gateway_id}.local.",
        )

    async def start(self) -> None:
        self.azc = AsyncZeroconf()
        self.info = self._service_info()
        await self.azc.async_register_service(self.info)

    async def stop(self) -> None:
        if self.azc and self.info:
            await self.azc.async_unregister_service(self.info)
        if self.azc:
            await self.azc.async_close()
