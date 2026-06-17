"""Ingestor configuration via environment variables."""

import os

BROKER_HOST = os.getenv("BROKER_HOST", "hivemq")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))

BASYX_URL = os.getenv("BASYX_URL", "http://aas-environment:8081")
TS_DSN = os.getenv("TS_DSN", "postgresql://postgres:admin@timescale:5432/postgres")

# Wildcard data subscription (covers all current + future device topics, no restart),
# and the BaSyx submodel event family (learns device AID schemas).
DATA_TOPIC = os.getenv("DATA_TOPIC", "uns/#")
EVENT_TOPIC = os.getenv("EVENT_TOPIC", "sm-repository/#")

# Periodic BaSyx back-fill (safety net if an event was missed).
REFRESH_INTERVAL = float(os.getenv("REFRESH_INTERVAL", "60"))
