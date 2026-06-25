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
from pydantic import BaseModel, ValidationError

from connectors.config_model import parse_connector

from . import adapters, bridge_config, config, manifest
from .discovery import Advertiser

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gateway-agent")

advertiser = Advertiser(config.GATEWAY_ID, config.AGENT_PORT)


async def _periodic_broker_restart():
    """Restart HiveMQ every BRIDGE_RESTART_HOURS to reset the bridge trial."""
    interval = config.BRIDGE_RESTART_HOURS * 3600
    if interval <= 0:
        return
    while True:
        await asyncio.sleep(interval)
        log.info("periodic HiveMQ restart (every %sh) to reset the bridge trial", config.BRIDGE_RESTART_HOURS)
        await asyncio.to_thread(bridge_config.restart_broker)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Restore connectors persisted on the config volume so a restart doesn't drop
    # every device (the adapter containers themselves survive via restart policy).
    restored = manifest.load_persisted_connectors()
    if restored:
        log.info("restored %d persisted connector(s)", restored)
    await advertiser.start()
    log.info("advertising %s on mDNS (port %s)", config.GATEWAY_ID, config.AGENT_PORT)
    restart_task = asyncio.create_task(_periodic_broker_restart())
    yield
    restart_task.cancel()
    await advertiser.stop()
    log.info("stopped advertising %s", config.GATEWAY_ID)


app = FastAPI(title="Edge Gateway Agent", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "gateway_id": config.GATEWAY_ID}


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
    """Record the server bridge IP (+ optional UNS prefix), re-template the HiveMQ
    bridge config and restart the broker (best-effort; no-op when run as host
    Python without the broker mount / Docker socket)."""
    state = manifest.set_bridge_state(req.server_bridge_ip, req.uns_prefix)
    restarted = await asyncio.to_thread(
        bridge_config.apply_bridge_ip, req.server_bridge_ip, req.uns_prefix
    )
    return {**state, "broker_restarted": restarted}


class ConnectorReq(BaseModel):
    device_id: str | None = None
    protocol: str  # e.g. modbus-tcp, opcua, s7, usb — gateway is protocol-agnostic
    connection: dict = {}  # protocol connection params (host/port, endpoint_url, …)
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
    device_key = _device_key(req)
    descriptor = {
        "device_key": device_key,
        "device_id": req.device_id or device_key,
        "protocol": req.protocol,
        "connection": req.connection,
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
    "broker": config.HIVEMQ_CONTAINER,
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
