"""Server agent configuration via environment variables."""

import os

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

# Liveness health-poll cadence (seconds). User-tunable; default 20s.
# (A future enhancement exposes this via the API for runtime control.)
LIVENESS_INTERVAL = float(os.getenv("LIVENESS_INTERVAL", "20"))
