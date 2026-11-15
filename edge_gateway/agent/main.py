"""Edge Gateway Agent FastAPI app.

Endpoints: GET /api/health, GET /api/manifest, POST /api/configure,
POST /api/connectors. Advertises over mDNS on startup. Run (host dev):
uvicorn agent.main:app --port 8000 (cwd = edge_gateway/).
"""

import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from connectors.config_model import parse_connector

from . import adapters, bridge_config, config, manifest
from .discovery import Advertiser
from .opcua_browse import BrowseReq, browse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gateway-agent")

advertiser = Advertiser(config.GATEWAY_ID, config.AGENT_PORT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if manifest.load_bridge_state():
        log.info("restored bridge state: %s", manifest.get_bridge_state())
    # Restore connectors persisted on the config volume so a restart doesn't drop
    # every device, and (re)start any adapter whose container is missing or
    # stopped, e.g. after redeploy.sh removed them to pick up a rebuilt image.
    restored = manifest.load_persisted_connectors()
    if restored:
        log.info("restored %d persisted connector(s)", restored)
        started = await asyncio.to_thread(adapters.ensure_running, manifest.list_connectors())
        if started:
            log.info("relaunched %d adapter container(s)", started)
    await advertiser.start()
    log.info("advertising %s on mDNS (port %s)", config.GATEWAY_ID, config.AGENT_PORT)
    yield
    await advertiser.stop()
    log.info("stopped advertising %s", config.GATEWAY_ID)


app = FastAPI(title="Edge Gateway Agent", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "gateway_id": config.GATEWAY_ID}


@app.post("/api/opcua/browse")
async def browse_opcua(req: BrowseReq):
    try:
        return await browse(req)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="OPC UA browse timed out; try a smaller folder")
    except Exception as exc:
        log.warning("OPC UA browse failed: %s", exc)
        raise HTTPException(status_code=502, detail="Cannot browse this node. Check endpoint, NodeId and anonymous read access.")


@app.get("/api/manifest")
async def get_manifest():
    return manifest.build_manifest()


class ConfigureReq(BaseModel):
    server_bridge_ip: str
    # UNS root the bridge republishes local topics under, e.g.
    # "uns/enterprise/site/area/line". Optional: leaves the current value when omitted.
    uns_prefix: str | None = None


@app.post("/api/configure")
async def configure(req: ConfigureReq):
    """Record the server bridge IP (+ optional UNS prefix), write the Mosquitto
    bridge config and restart the broker (best-effort; no-op when run as host
    Python without the broker mount / Docker socket)."""
    uns = (req.uns_prefix or manifest.get_bridge_state()["uns_prefix"]).strip().strip("/")
    try:
        bridge_config.render_bridge(req.server_bridge_ip, uns)  # validate before storing
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    state = manifest.set_bridge_state(req.server_bridge_ip, uns)
    restarted = await asyncio.to_thread(bridge_config.apply_bridge_ip, req.server_bridge_ip, uns)
    return {**state, "broker_restarted": restarted}


class ConnectorReq(BaseModel):
    device_id: str | None = None
    protocol: str  # e.g. modbus-tcp, opcua, s7, usb — gateway is protocol-agnostic
    connection: dict = {}  # protocol connection params (host/port, endpoint_url, …)
    # Polling interval in seconds: every datapoint is read once per interval.
    interval: float = Field(default=2.0, ge=0.05)
    datapoints: list = []  # each: {name, datatype, unit, local_topic, address:{…}}
    # Optional real-world device identity (flows into the device Digital Nameplate).
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None


def _device_key(req: "ConnectorReq") -> str:
    if req.device_id:
        return re.sub(r"[^A-Za-z0-9_.-]", "-", req.device_id)
    return f"{req.protocol}-{uuid.uuid4().hex[:8]}"


@app.post("/api/connectors", status_code=201)
async def add_connector(req: ConnectorReq):
    """Declare a device/connector on this gateway (idempotent by device_key).

    Protocol-agnostic: the gateway stores whatever connection/datapoint params it
    is given. The live protocol->MQTT loop is implemented in Phase 6.
    """
    # Only <LOCAL_BASE_TOPIC>/... is bridged to the server (see bridge_config),
    # so a datapoint published elsewhere would never be ingested.
    base = config.LOCAL_BASE_TOPIC.strip("/") + "/"
    for dp in req.datapoints:
        topic = (dp.get("local_topic") or "").strip() if isinstance(dp, dict) else ""
        if topic and not topic.startswith(base):
            raise HTTPException(
                status_code=400,
                detail=f"local topic {topic!r} must start with {base!r} to be bridged to the server",
            )
    device_key = _device_key(req)
    descriptor = {
        "device_key": device_key,
        "device_id": req.device_id or device_key,
        "protocol": req.protocol,
        "connection": req.connection,
        "interval": req.interval,
        "datapoints": req.datapoints,
        "manufacturer": req.manufacturer,
        "model": req.model,
        "serial_number": req.serial_number,
    }
    # Validate against the connector data model (config_model) before storing or
    # launching an adapter, so a misconfigured connector fails fast with a clear
    # error rather than crash-looping a container.
    try:
        parse_connector(descriptor)
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=[{"loc": err["loc"], "msg": err["msg"]} for err in e.errors()],
        )
    manifest.upsert_connector(descriptor)
    # Launch the protocol->MQTT adapter container (no-op if autostart disabled).
    adapter_started = await asyncio.to_thread(adapters.start_adapter, descriptor)
    return {**descriptor, "adapter_started": adapter_started}


@app.get("/api/connectors/status")
async def connectors_status():
    """Live connection state per connector (for the UI status badges)."""
    out = {}
    for c in manifest.list_connectors():
        key = c["device_key"]
        out[key] = await asyncio.to_thread(adapters.connector_status, key)
    return out


@app.get("/api/connectors/{device_key}/logs")
async def connector_logs(device_key: str, tail: int = 200):
    """Recent adapter container logs for one connector (for the UI Logs tab)."""
    logs = await asyncio.to_thread(adapters.connector_logs, device_key, tail)
    return {"device_key": device_key, "logs": logs}


# Gateway-level log targets the UI can stream (the agent itself + the broker).
_SYSTEM_CONTAINERS = {
    "agent": config.AGENT_CONTAINER,
    "broker": config.BROKER_CONTAINER,
}


@app.get("/api/logs/{target}")
async def system_logs(target: str, tail: int = 200):
    """Recent logs for a gateway-level container (target: agent | broker)."""
    name = _SYSTEM_CONTAINERS.get(target)
    if not name:
        raise HTTPException(status_code=404, detail=f"unknown log target {target}")
    logs = await asyncio.to_thread(adapters.container_logs, name, tail)
    return {"target": target, "logs": logs}


@app.delete("/api/connectors/{device_key}")
async def delete_connector(device_key: str):
    """Remove a connector and stop its adapter container (idempotent)."""
    removed = manifest.remove_connector(device_key)
    if not removed:
        raise HTTPException(status_code=404, detail=f"unknown connector {device_key}")
    # Tear down the adapter container + its instance config (best-effort).
    await asyncio.to_thread(adapters.stop_adapter, device_key)
    return {"device_key": device_key, "removed": True}
