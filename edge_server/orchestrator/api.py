"""Dashboard API (consumed by the React UI).

  GET  /api/gateways            liveness list (in-memory registry)
  GET  /api/gateways/{id}/aas   proxy shell + submodels from BaSyx
  GET  /api/devices             device summaries (from cached manifests)
  POST /api/gateways/register   manual fallback (mDNS unavailable)
  POST /api/provision           Web UI device config -> gateway + AAS
"""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import config
from .aas import ids
from .basyx_client import fetch_shell_with_submodels
from .registration_service import registration_service
from .registry import registry

router = APIRouter(prefix="/api")


def _summarise(rec: dict) -> dict:
    return {
        "gateway_id": rec.get("gateway_id"),
        "serial_number": rec.get("serial_number"),
        "ip": rec.get("ip"),
        "port": rec.get("port"),
        "hostname": rec.get("hostname"),
        "online": rec.get("online", False),
        "last_seen": rec.get("last_seen"),
        "device_count": rec.get("device_count", 0),
    }


@router.get("/server-info")
async def server_info():
    """The server's own LAN IP — i.e. the broker address gateways bridge to."""
    return {"server_ip": config.resolve_server_ip()}


@router.get("/gateways")
async def list_gateways():
    return [_summarise(r) for r in registry.list()]


@router.get("/gateways/{gateway_id}/aas")
async def gateway_aas(gateway_id: str):
    rec = registry.get(gateway_id)
    if not rec or not rec.get("serial_number"):
        raise HTTPException(status_code=404, detail="unknown gateway or missing serial")
    aas_id = ids.aas_id(ids.gateway_system_id(rec["serial_number"]))
    try:
        return await fetch_shell_with_submodels(aas_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="AAS not found in BaSyx")
        raise HTTPException(status_code=502, detail=f"BaSyx error: {e}")


@router.get("/devices")
async def list_devices():
    """Flat list of connectors across all known gateways (from cached manifests)."""
    out = []
    for rec in registry.list():
        manifest = rec.get("manifest") or {}
        serial = rec.get("serial_number")
        for c in manifest.get("configured_connectors", []):
            device_key = c.get("device_key") or c.get("device_id")
            out.append(
                {
                    "gateway_id": rec.get("gateway_id"),
                    "gateway_serial": serial,
                    "device_key": device_key,
                    "device_id": c.get("device_id"),
                    "protocol": c.get("protocol"),
                    "datapoints": c.get("datapoints", []),
                    "device_aas_id": ids.aas_id(ids.device_system_id(serial, device_key))
                    if serial and device_key
                    else None,
                }
            )
    return out


class RegisterReq(BaseModel):
    ip: str
    port: int = 8000
    manifest_path: str = "/api/manifest"


@router.post("/gateways/register")
async def register_gateway(req: RegisterReq):
    """Inject a gateway as if it had been discovered via mDNS."""
    url = f"http://{req.ip}:{req.port}{req.manifest_path}"
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            manifest = r.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"manifest fetch failed: {e}")

    gateway_id = manifest.get("gateway_id")
    if not gateway_id:
        raise HTTPException(status_code=502, detail="manifest missing gateway_id")

    registry.upsert(
        gateway_id,
        service_name=None,
        ip=req.ip,
        port=req.port,
        serial_number=manifest.get("serial_number"),
        manifest=manifest,
        device_count=len(manifest.get("configured_connectors", [])),
    )
    network = {"ip": req.ip, "port": req.port, "hostname": None, "gateway_id": gateway_id}
    await registration_service.register_gateway(manifest, network)
    return {"gateway_id": gateway_id, "status": "registered"}


class ConfigureReq(BaseModel):
    # Optional: defaults to the edge server's own IP (the broker gateways bridge to).
    server_bridge_ip: str | None = None


@router.post("/gateways/{gateway_id}/configure")
async def configure_gateway(gateway_id: str, req: ConfigureReq):
    """Proxy a bridge-IP configuration to the gateway (gateways have no CORS).

    The bridge target is the edge server's own IP, so it defaults to that when
    the caller doesn't supply one.
    """
    rec = registry.get(gateway_id)
    if not rec or not rec.get("ip"):
        raise HTTPException(status_code=404, detail="unknown or unreachable gateway")
    bridge_ip = req.server_bridge_ip or config.resolve_server_ip()
    url = f"http://{rec['ip']}:{rec['port']}/api/configure"
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        try:
            r = await client.post(url, json={"server_bridge_ip": bridge_ip})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"gateway configure failed: {e}")


class ProvisionReq(BaseModel):
    gateway_id: str
    device_id: str
    protocol: str  # modbus-tcp, opcua, s7, usb, …
    connection: dict = {}  # protocol connection params
    datapoints: list = []  # each: {name, datatype, unit, local_topic, address:{…}}
    # Optional real-world device identity (flows into the device Digital Nameplate).
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None


@router.post("/provision")
async def provision(req: ProvisionReq):
    """Configure a device/service on a gateway (from the Web UI) + sync its AAS."""
    rec = registry.get(req.gateway_id)
    if not rec:
        raise HTTPException(status_code=404, detail="unknown gateway")
    device_config = req.model_dump(exclude={"gateway_id"})
    try:
        # provision_device also refreshes the cached manifest on `rec`.
        return await registration_service.provision_device(rec, device_config)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"gateway/provision error: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
