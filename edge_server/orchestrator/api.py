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

from . import config, measurements
from .aas import ids
from .basyx_client import fetch_shell_with_submodels
from .registration_service import registration_service
from .registry import registry

router = APIRouter(prefix="/api")


def _summarise(rec: dict) -> dict:
    manifest = rec.get("manifest") or {}
    return {
        "gateway_id": rec.get("gateway_id"),
        "serial_number": rec.get("serial_number"),
        "ip": rec.get("ip"),
        "port": rec.get("port"),
        "hostname": rec.get("hostname"),
        "online": rec.get("online", False),
        "last_seen": rec.get("last_seen"),
        "device_count": rec.get("device_count", 0),
        # Northbound specs (for the topology view): MQTT bridge + local broker.
        "bridge": manifest.get("bridge"),
        "mqtt": manifest.get("mqtt"),
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


@router.get("/aas")
async def aas_by_id(id: str):
    """Proxy any shell + its submodels from BaSyx by AAS id (gateway or device)."""
    try:
        return await fetch_shell_with_submodels(id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="AAS not found in BaSyx")
        raise HTTPException(status_code=502, detail=f"BaSyx error: {e}")


@router.get("/measurements/latest")
async def measurements_latest():
    """Latest ingested value per device/datapoint (from TimescaleDB)."""
    return measurements.latest()


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
                    # Southbound specs (for the topology view): protocol connection.
                    "connection": c.get("connection", {}),
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
    # Configure restarts the HiveMQ broker (~10-15s), so allow a generous timeout.
    async with httpx.AsyncClient(timeout=45.0) as client:
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
        # Forward the gateway's own client errors (e.g. 400 invalid connector)
        # as-is instead of masking them all as a generic 502 bad-gateway.
        status = e.response.status_code
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        if 400 <= status < 500:
            raise HTTPException(status_code=status, detail=detail)
        raise HTTPException(status_code=502, detail=f"gateway/provision error: {detail}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        # Surface AAS build / unexpected failures as a clean error. Without this
        # the 500 is generated above CORSMiddleware and the browser reports it as
        # a CORS failure instead of showing the real reason.
        raise HTTPException(status_code=400, detail=f"provisioning failed: {e}")


@router.delete("/gateways/{gateway_id}/connectors/{device_key}")
async def deprovision(gateway_id: str, device_key: str):
    """Remove a device/service from a gateway (from the Web UI) + drop its AAS."""
    rec = registry.get(gateway_id)
    if not rec:
        raise HTTPException(status_code=404, detail="unknown gateway")
    try:
        return await registration_service.deprovision_device(rec, device_key)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        if 400 <= status < 500:
            raise HTTPException(status_code=status, detail=detail)
        raise HTTPException(status_code=502, detail=f"gateway/deprovision error: {detail}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"deprovision failed: {e}")


@router.get("/connectors/status")
async def connectors_status():
    """Live connection state for every connector across all gateways (UI badges).

    Best-effort: unreachable gateways are skipped rather than failing the whole
    response, so one offline gateway doesn't blank the dashboard.
    """
    out = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for rec in registry.list():
            ip, port = rec.get("ip"), rec.get("port")
            if not ip or not port:
                continue
            try:
                r = await client.get(f"http://{ip}:{port}/api/connectors/status")
                r.raise_for_status()
                statuses = r.json()
            except Exception:
                continue
            for device_key, st in statuses.items():
                out.append({"gateway_id": rec.get("gateway_id"), "device_key": device_key, **st})
    return out


@router.get("/gateways/{gateway_id}/connectors/{device_key}/logs")
async def connector_logs(gateway_id: str, device_key: str, tail: int = 200):
    """Proxy a connector's adapter logs from the gateway (for the UI Logs tab)."""
    rec = registry.get(gateway_id)
    if not rec or not rec.get("ip"):
        raise HTTPException(status_code=404, detail="unknown or unreachable gateway")
    url = f"http://{rec['ip']}:{rec['port']}/api/connectors/{device_key}/logs"
    return await _proxy_logs(url, tail)


@router.get("/gateways/{gateway_id}/logs/{target}")
async def gateway_logs(gateway_id: str, target: str, tail: int = 200):
    """Proxy gateway-level logs (target: agent | broker) for the UI Logs tab."""
    rec = registry.get(gateway_id)
    if not rec or not rec.get("ip"):
        raise HTTPException(status_code=404, detail="unknown or unreachable gateway")
    url = f"http://{rec['ip']}:{rec['port']}/api/logs/{target}"
    return await _proxy_logs(url, tail)


async def _proxy_logs(url: str, tail: int) -> dict:
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        try:
            r = await client.get(url, params={"tail": tail})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"gateway logs fetch failed: {e}")
