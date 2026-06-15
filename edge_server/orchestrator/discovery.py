"""mDNS discovery of edge gateways.

Zeroconf callbacks run on a worker thread, so they only enqueue events via
`loop.call_soon_threadsafe`; an async task resolves the service, fetches the
gateway manifest, updates the registry, and (on change) invokes the
`on_manifest` callback to sync the AAS.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

import httpx
from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

from . import config
from .registry import registry

log = logging.getLogger("discovery")

SERVICE_TYPE = "_aasgw._tcp.local."

# async (manifest: dict, network: dict) -> None
OnManifest = Callable[[dict, dict], Awaitable[None]]


def _decode_props(raw: dict) -> dict:
    out = {}
    for k, v in (raw or {}).items():
        key = k.decode() if isinstance(k, bytes) else str(k)
        if isinstance(v, bytes):
            out[key] = v.decode(errors="replace")
        elif v is None:
            out[key] = ""
        else:
            out[key] = str(v)
    return out


class Discovery:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_manifest: Optional[OnManifest] = None,
    ):
        self.loop = loop
        self.on_manifest = on_manifest
        self.queue: asyncio.Queue = asyncio.Queue()
        self.azc: AsyncZeroconf | None = None
        self.browser: AsyncServiceBrowser | None = None
        self._task: asyncio.Task | None = None
        self._name_to_gw: dict[str, str] = {}  # mDNS service name -> gateway_id

    async def start(self) -> None:
        self.azc = AsyncZeroconf()
        self.browser = AsyncServiceBrowser(
            self.azc.zeroconf, SERVICE_TYPE, handlers=[self._on_change]
        )
        self._task = asyncio.create_task(self._consume())
        log.info("browsing for %s", SERVICE_TYPE)

    async def stop(self) -> None:
        if self.browser:
            await self.browser.async_cancel()
        if self.azc:
            await self.azc.async_close()
        if self._task:
            self._task.cancel()

    # --- zeroconf thread: only schedule, never block ---
    def _on_change(self, zeroconf, service_type, name, state_change) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, (name, state_change))

    # --- asyncio loop ---
    async def _consume(self) -> None:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            while True:
                name, change = await self.queue.get()
                try:
                    if change in (ServiceStateChange.Added, ServiceStateChange.Updated):
                        await self._handle_up(client, name)
                    elif change == ServiceStateChange.Removed:
                        self._handle_down(name)
                except Exception:
                    log.exception("error handling %s for %s", change, name)

    async def _handle_up(self, client: httpx.AsyncClient, name: str) -> None:
        info = await self.azc.async_get_service_info(SERVICE_TYPE, name)
        if not info:
            log.warning("could not resolve service info for %s", name)
            return

        props = _decode_props(info.properties)
        gateway_id = props.get("gateway_id") or name.split(".")[0]
        manifest_path = props.get("manifest_path", "/api/manifest")
        addrs = info.parsed_addresses()
        ip = addrs[0] if addrs else None
        port = info.port
        hostname = (info.server or "").rstrip(".") or None

        manifest = None
        if ip:
            url = f"http://{ip}:{port}{manifest_path}"
            try:
                r = await client.get(url)
                r.raise_for_status()
                manifest = r.json()
            except Exception:
                log.exception("manifest fetch failed: %s", url)

        # Detect whether the manifest actually changed since last seen, so we
        # skip redundant AAS re-syncs on periodic mDNS re-announcements.
        prev = registry.get(gateway_id)
        changed = manifest is not None and (prev or {}).get("manifest") != manifest

        self._name_to_gw[name] = gateway_id
        registry.upsert(
            gateway_id,
            service_name=name,
            ip=ip,
            port=port,
            hostname=hostname,
            serial_number=(manifest or {}).get("serial_number"),
            manifest=manifest,
            device_count=len((manifest or {}).get("configured_connectors", [])),
        )
        log.info("gateway UP: %s @ %s:%s", gateway_id, ip, port)

        if changed and self.on_manifest is not None:
            network = {"ip": ip, "port": port, "hostname": hostname, "gateway_id": gateway_id}
            await self.on_manifest(manifest, network)

    def _handle_down(self, name: str) -> None:
        gateway_id = self._name_to_gw.get(name)
        if gateway_id:
            registry.mark_offline(gateway_id)
            log.info("gateway DOWN: %s", gateway_id)
