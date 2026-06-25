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

# The gateway is protocol-agnostic: the protocol is chosen per connector at
# provisioning time, not constrained here (and never advertised over mDNS).
# This list is informational only.
SUPPORTED_ADAPTERS = ["modbus-tcp", "opcua", "s7", "usb"]

# --- protocol adapter containers (managed by the agent via the Docker socket) ---
# When enabled, provisioning a connector launches one adapter container per device.
ADAPTER_AUTOSTART = os.getenv("ADAPTER_AUTOSTART", "false").lower() == "true"
ADAPTER_IMAGE = os.getenv("ADAPTER_IMAGE", "iiot/connector-adapter")
ADAPTER_NETWORK = os.getenv("ADAPTER_NETWORK")  # docker network linking adapter<->device<->broker
# The local broker the adapter publishes to (reachable on ADAPTER_NETWORK).
ADAPTER_BROKER_HOST = os.getenv("ADAPTER_BROKER_HOST", "gw-broker")
ADAPTER_BROKER_PORT = int(os.getenv("ADAPTER_BROKER_PORT", "1883"))

# Per-connector adapter config files: the agent writes <dir>/<device_key>/config.json
# and mounts it into each adapter. Backed by a NAMED Docker volume shared
# agent<->adapters — not a bind mount: the agent launches adapters via the host
# socket, so bind-mount paths would resolve on the host, not in the agent.
ADAPTER_CONFIG_DIR = os.getenv("ADAPTER_CONFIG_DIR", "/app/instances")
ADAPTER_CONFIG_VOLUME = os.getenv("ADAPTER_CONFIG_VOLUME", "adapter_configs")

# Container names whose logs the UI can stream (this agent + the local broker).
AGENT_CONTAINER = os.getenv("AGENT_CONTAINER", "gateway-agent")
HIVEMQ_CONTAINER = os.getenv("HIVEMQ_CONTAINER", "hivemq")

# Periodically restart the HiveMQ container to reset the Enterprise Bridge
# Extension's 5-hour trial (restart every N hours, < 5). 0 disables.
BRIDGE_RESTART_HOURS = float(os.getenv("BRIDGE_RESTART_HOURS", "4"))
