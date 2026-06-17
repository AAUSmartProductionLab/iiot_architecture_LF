"""Server agent configuration via environment variables."""

import os
import socket

# Eclipse BaSyx v2 AAS Environment base URL (Phase 2+).
BASYX_URL = os.getenv("BASYX_URL", "http://localhost:8081")

# Base IRI for AAS/submodel/asset identifiers. Used to mint globally unique,
# deterministic ids: {AAS_BASE_URL}/aas/{system_id}, /submodels/instances/...,
# /assets/{system_id}. Should be a namespace you control.
AAS_BASE_URL = os.getenv("AAS_BASE_URL", "https://smart-production.aau.dk")

# Where this agent's FastAPI app listens.
AGENT_PORT = int(os.getenv("AGENT_PORT", "8000"))

# Timeout for outbound HTTP (manifest fetch, BaSyx calls).
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "5.0"))

# TimescaleDB (read-only, for the dashboard's latest-value display). The
# measurements endpoint degrades to [] if the DB is unreachable.
TS_DSN = os.getenv("TS_DSN", "postgresql://postgres:admin@localhost:5432/postgres")

# Liveness health-poll cadence (seconds). User-tunable; default 20s.
# (A future enhancement exposes this via the API for runtime control.)
LIVENESS_INTERVAL = float(os.getenv("LIVENESS_INTERVAL", "20"))

# The edge server's own LAN IP = the address gateways should bridge their MQTT to
# (the server runs HiveMQ). Defaults to auto-detection; override with SERVER_IP
# (needed when the orchestrator runs in bridge networking, where auto-detect
# returns the container IP instead of the host's).
SERVER_IP = os.getenv("SERVER_IP")


def resolve_server_ip() -> str:
    if SERVER_IP:
        return SERVER_IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packets sent; selects the egress iface
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()
