"""Edge Server Agent FastAPI app.

Starts mDNS discovery + the liveness monitor on startup and exposes the
dashboard API (see api.py). Run (host dev): uvicorn agent.main:app --port 8000
(cwd = edge_server/).
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import router
from .discovery import Discovery
from .liveness import LivenessMonitor
from .registration_service import registration_service

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    # On every changed manifest, (re)build the gateway's AAS in BaSyx (idempotent).
    disc = Discovery(loop, on_manifest=registration_service.register_gateway)
    await disc.start()
    monitor = LivenessMonitor(interval=config.LIVENESS_INTERVAL)
    await monitor.start()
    app.state.discovery = disc
    app.state.liveness = monitor
    yield
    await monitor.stop()
    await disc.stop()


app = FastAPI(title="Edge Server Agent", lifespan=lifespan)

# Allow the React dashboard (served from a different origin/port) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
