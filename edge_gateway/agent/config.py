"""Gateway agent configuration from environment variables."""

import os

from .identity import resolve_identity

# Identity (the stable key for this gateway's AAS on the server side).
# Auto-derived and persisted for plug-and-play; override via env on real hardware.
_ident = resolve_identity()
GATEWAY_ID = _ident["gateway_id"]
SERIAL_NUMBER = _ident["serial_number"]

# Descriptive fields that cannot be auto-generated meaningfully: generic defaults,
# overridable via env.
MANUFACTURER = os.getenv("MANUFACTURER", "Community IIoT")
HARDWARE_MODEL = os.getenv("HARDWARE_MODEL", "Generic Edge Gateway")
FIRMWARE_VERSION = os.getenv("FIRMWARE_VERSION", "0.1.0")

# Where this agent's FastAPI app listens (also advertised via mDNS).
AGENT_PORT = int(os.getenv("AGENT_PORT", "8000"))

# Local HiveMQ broker this gateway publishes to (the bridge forwards onward).
LOCAL_BROKER_HOST = os.getenv("LOCAL_BROKER_HOST", "localhost")
LOCAL_BROKER_PORT = int(os.getenv("LOCAL_BROKER_PORT", "1883"))
LOCAL_BASE_TOPIC = os.getenv("LOCAL_BASE_TOPIC", "devices")

# UNS prefix the bridge remaps local `devices/...` topics onto, on the server.
UNS_PREFIX = os.getenv("UNS_PREFIX", "uns/enterprise/site/area/line")

# Southbound protocols this gateway can adapt (only modbus-tcp wired for the MVD).
SUPPORTED_ADAPTERS = ["modbus-tcp"]
