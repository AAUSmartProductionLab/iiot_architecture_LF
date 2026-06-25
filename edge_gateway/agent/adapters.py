"""
Manage per-connector adapter containers via the Docker socket.

When a connector is provisioned, the gateway-agent writes that connector's
config to <ADAPTER_CONFIG_DIR>/<device_key>/config.json (on a named Docker volume
shared with the adapters) and launches one adapter container (image
`ADAPTER_IMAGE`) that mounts the volume read-only and reads its config via
CONFIG_PATH, then runs the protocol->MQTT loop.

Containers are named `adapter-<device_key>` and replaced on re-provision. The
image is immutable (code baked in at build time); only the per-connector config
differs between instances. No-op (returns False) when autostart is disabled or
Docker is unavailable, so host-Python dev still works.
"""

import json
import logging
import os
import shutil

import docker

from . import config

log = logging.getLogger("adapters")


def _container_name(device_key: str) -> str:
    return f"adapter-{device_key}"


def _instance_dir(device_key: str) -> str:
    return os.path.join(config.ADAPTER_CONFIG_DIR, device_key)


def _write_config(descriptor: dict) -> str:
    """Write the connector's config.json into its instance dir. Returns the path
    as seen INSIDE the adapter container (under the mounted config volume)."""
    device_key = descriptor["device_key"]
    cfg = {
        "device_key": device_key,
        "protocol": descriptor.get("protocol"),
        "connection": descriptor.get("connection", {}),
        "datapoints": descriptor.get("datapoints", []),
        "mqtt": {
            "broker_host": config.ADAPTER_BROKER_HOST,
            "broker_port": config.ADAPTER_BROKER_PORT,
        },
    }
    inst = _instance_dir(device_key)
    os.makedirs(inst, exist_ok=True)
    with open(os.path.join(inst, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    # The volume is mounted at ADAPTER_CONFIG_DIR inside the adapter, so the
    # container-visible path mirrors the agent-side layout.
    return os.path.join(config.ADAPTER_CONFIG_DIR, device_key, "config.json")


def start_adapter(descriptor: dict) -> bool:
    if not config.ADAPTER_AUTOSTART:
        return False
    device_key = descriptor["device_key"]
    name = _container_name(device_key)
    config_path = _write_config(descriptor)
    try:
        client = docker.from_env()
        try:  # replace any existing adapter for this device
            client.containers.get(name).remove(force=True)
        except Exception:
            pass
        kwargs = dict(
            name=name,
            environment={"CONFIG_PATH": config_path},
            volumes={
                config.ADAPTER_CONFIG_VOLUME: {"bind": config.ADAPTER_CONFIG_DIR, "mode": "ro"}
            },
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            labels={"iiot.role": "adapter", "iiot.device_key": device_key},
        )
        if config.ADAPTER_NETWORK:
            kwargs["network"] = config.ADAPTER_NETWORK
        client.containers.run(config.ADAPTER_IMAGE, **kwargs)
        log.info("started adapter container %s (config %s)", name, config_path)
        return True
    except Exception:
        log.exception("failed to start adapter container %s", name)
        return False


def _parse_failed(line: str) -> tuple[str | None, str | None]:
    """Pull `reason=… detail=…` out of a CONNECT_FAILED log line."""
    if "reason=" not in line:
        return None, None
    rest = line.split("reason=", 1)[1]
    if " detail=" in rest:
        reason, detail = rest.split(" detail=", 1)
    else:
        reason, detail = rest, None
    return reason.strip() or None, (detail.strip() if detail else None)


def connector_status(device_key: str) -> dict:
    """Live connection state for one adapter, derived from its container state +
    the CONNECTED / CONNECT_FAILED markers the adapter logs.

    state: connected | error | starting | stopped. `reason`/`detail` are set on
    error (reason is the surface-level wizard message; detail is the full text).
    """
    name = _container_name(device_key)
    try:
        container = docker.from_env().containers.get(name)
    except Exception:
        return {"state": "stopped", "container": "absent", "reason": None, "detail": "no adapter container"}

    container_state = getattr(container, "status", "unknown")
    try:
        logs = container.logs(tail=200).decode("utf-8", "replace")
    except Exception:
        logs = ""

    state, reason, detail = "starting", None, None
    for line in reversed(logs.splitlines()):
        if "CONNECT_FAILED" in line:
            state = "error"
            reason, detail = _parse_failed(line)
            break
        if "CONNECTED" in line:
            state = "connected"
            break
    if container_state in ("exited", "dead") and state != "error":
        state = "stopped"
    return {"state": state, "container": container_state, "reason": reason, "detail": detail}


def container_logs(name: str, tail: int = 200) -> str:
    """Tail a container's logs by name (best-effort)."""
    try:
        container = docker.from_env().containers.get(name)
        return container.logs(tail=tail).decode("utf-8", "replace")
    except Exception as e:
        return f"(no logs for {name}: {e})"


def connector_logs(device_key: str, tail: int = 200) -> str:
    return container_logs(_container_name(device_key), tail)


def stop_adapter(device_key: str) -> bool:
    removed = False
    try:
        docker.from_env().containers.get(_container_name(device_key)).remove(force=True)
        removed = True
    except Exception:
        pass
    # Best-effort cleanup of the connector's instance config.
    shutil.rmtree(_instance_dir(device_key), ignore_errors=True)
    return removed
