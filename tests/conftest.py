"""Make the gateway and server packages importable from the repo-level tests.

edge_gateway/ and edge_server/ are each their own application root (their
Dockerfiles copy agent/, connectors/, orchestrator/, ingestor/ to /app).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("edge_gateway", "edge_server", "tests/simulators"):
    path = str(ROOT / sub)
    if path not in sys.path:
        sys.path.insert(0, path)
