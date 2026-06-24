"""The gateway's authoritative self-description.

Owns this gateway's configured connectors + bridge config. The server pulls
`build_manifest()` over HTTP after discovery.

Connectors are persisted to disk (one descriptor.json per device, under the
ADAPTER_CONFIG_DIR named volume that also holds each adapter's config.json), so
they survive an agent/container restart. `load_persisted_connectors()` rehydrates
them on startup. The bridge config is still in-memory (the HiveMQ bridge itself
persists in the broker's own config).
"""

import json
import logging
import os

from . import config

log = logging.getLogger("manifest")

# In-memory state. Connectors are mirrored to disk (see persistence helpers).
_connectors: dict[str, dict] = {}  # device_key -> connector descriptor
_bridge: dict = {
    "configured": False,
    "server_ip": None,
    "uns_prefix": config.UNS_PREFIX,
}


def _descriptor_path(device_key: str) -> str:
    return os.path.join(config.ADAPTER_CONFIG_DIR, device_key, "descriptor.json")


def _persist(descriptor: dict) -> None:
    """Write a connector descriptor to its instance dir (best-effort).

    No-op when ADAPTER_CONFIG_DIR isn't present (e.g. host-Python dev without the
    named volume), so it never creates stray directories off the volume.
    """
    if not os.path.isdir(config.ADAPTER_CONFIG_DIR):
        return
    path = _descriptor_path(descriptor["device_key"])
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(descriptor, f, indent=2)
    except Exception:
        log.warning("could not persist connector %s", descriptor.get("device_key"), exc_info=True)


def _unpersist(device_key: str) -> None:
    try:
        os.remove(_descriptor_path(device_key))
    except FileNotFoundError:
        pass
    except Exception:
        log.warning("could not remove persisted connector %s", device_key, exc_info=True)


def load_persisted_connectors() -> int:
    """Rehydrate connectors from disk into memory on startup. Returns the count.

    The adapter containers keep running across a restart (restart_policy
    unless-stopped), so this only restores the agent's self-description; it does
    not relaunch adapters.
    """
    try:
        entries = os.listdir(config.ADAPTER_CONFIG_DIR)
    except FileNotFoundError:
        return 0
    except Exception:
        log.warning("could not scan %s for persisted connectors", config.ADAPTER_CONFIG_DIR, exc_info=True)
        return 0
    count = 0
    for name in entries:
        path = _descriptor_path(name)
        try:
            with open(path, encoding="utf-8") as f:
                descriptor = json.load(f)
        except FileNotFoundError:
            continue
        except Exception:
            log.warning("skipping unreadable connector descriptor %s", path, exc_info=True)
            continue
        _connectors[descriptor.get("device_key") or name] = descriptor
        count += 1
    if count:
        log.info("rehydrated %d connector(s) from %s", count, config.ADAPTER_CONFIG_DIR)
    return count


def get_bridge_state() -> dict:
    return dict(_bridge)


def set_bridge_state(server_ip: str) -> dict:
    _bridge["server_ip"] = server_ip
    _bridge["configured"] = bool(server_ip)
    return dict(_bridge)


def upsert_connector(descriptor: dict) -> dict:
    """Insert or update a connector by its device_key (idempotent), persisting it."""
    _connectors[descriptor["device_key"]] = descriptor
    _persist(descriptor)
    return descriptor


def remove_connector(device_key: str) -> bool:
    """Drop a connector by its device_key. Returns False if it wasn't present."""
    existed = _connectors.pop(device_key, None) is not None
    _unpersist(device_key)
    return existed


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
