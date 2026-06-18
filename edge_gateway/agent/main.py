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

from fastapi import FastAPI
from pydantic import BaseModel

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


@app.post("/api/configure")
async def configure(req: ConfigureReq):
    """Record the server bridge IP, re-template the HiveMQ bridge config and
    restart the broker (best-effort; no-op when run as host Python without the
    broker mount / Docker socket)."""
    state = manifest.set_bridge_state(req.server_bridge_ip)
    restarted = await asyncio.to_thread(bridge_config.apply_bridge_ip, req.server_bridge_ip)
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
    manifest.upsert_connector(descriptor)
    # Launch the protocol->MQTT adapter container (no-op if autostart disabled).
    adapter_started = await asyncio.to_thread(adapters.start_adapter, descriptor)
    return {**descriptor, "adapter_started": adapter_started}
