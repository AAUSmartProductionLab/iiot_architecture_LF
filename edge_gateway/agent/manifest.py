"""The gateway's authoritative self-description.

Owns this gateway's ephemeral in-memory state (bridge config + configured
connectors). The server pulls `build_manifest()` over HTTP after discovery.
"""

from . import config

# Ephemeral in-memory state (lost on restart; rebuilt by reconfiguration).
_connectors: dict[str, dict] = {}  # device_key -> connector descriptor
_bridge: dict = {
    "configured": False,
    "server_ip": None,
    "uns_prefix": config.UNS_PREFIX,
}


def get_bridge_state() -> dict:
    return dict(_bridge)


def set_bridge_state(server_ip: str) -> dict:
    _bridge["server_ip"] = server_ip
    _bridge["configured"] = bool(server_ip)
    return dict(_bridge)


def upsert_connector(descriptor: dict) -> dict:
    """Insert or update a connector by its device_key (idempotent)."""
    _connectors[descriptor["device_key"]] = descriptor
    return descriptor


def list_connectors() -> list[dict]:
    return list(_connectors.values())


def build_manifest() -> dict:
    return {
        "schema_version": "1.0",
        "gateway_id": config.GATEWAY_ID,
        "hardware_model": config.HARDWARE_MODEL,
        "serial_number": config.SERIAL_NUMBER,
        "manufacturer": config.MANUFACTURER,
        "firmware_version": config.FIRMWARE_VERSION,
        "software_components": [
            {"name": "gateway-agent", "version": config.FIRMWARE_VERSION},
            {"name": "python-runtime", "version": "3.11"},
        ],
        "supported_adapters": config.SUPPORTED_ADAPTERS,
        "bridge": get_bridge_state(),
        "mqtt": {
            "local_broker_host": config.LOCAL_BROKER_HOST,
            "local_broker_port": config.LOCAL_BROKER_PORT,
            "local_base_topic": config.LOCAL_BASE_TOPIC,
        },
        "configured_connectors": list_connectors(),
    }
