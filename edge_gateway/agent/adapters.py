"""
Manage per-connector adapter containers via the Docker socket.

When a connector is provisioned, the gateway-agent launches one adapter
container (image `ADAPTER_IMAGE`) that runs the protocol->MQTT loop, passing the
connector config as CONNECTOR_CONFIG. Containers are named `adapter-<device_key>`
and replaced on re-provision. No-op (returns False) when autostart is disabled or
Docker is unavailable, so host-Python dev still works.
"""

import json
import logging

from . import config

log = logging.getLogger("adapters")


def _container_name(device_key: str) -> str:
    return f"adapter-{device_key}"


def start_adapter(descriptor: dict) -> bool:
    if not config.ADAPTER_AUTOSTART:
        return False
    device_key = descriptor["device_key"]
    name = _container_name(device_key)
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
    try:
        import docker

        client = docker.from_env()
        try:  # replace any existing adapter for this device
            client.containers.get(name).remove(force=True)
        except Exception:
            pass
        kwargs = dict(
            name=name,
            environment={"CONNECTOR_CONFIG": json.dumps(cfg)},
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            labels={"iiot.role": "adapter", "iiot.device_key": device_key},
        )
        if config.ADAPTER_NETWORK:
            kwargs["network"] = config.ADAPTER_NETWORK
        client.containers.run(config.ADAPTER_IMAGE, **kwargs)
        log.info("started adapter container %s", name)
        return True
    except Exception:
        log.exception("failed to start adapter container %s", name)
        return False


def stop_adapter(device_key: str) -> bool:
    try:
        import docker

        docker.from_env().containers.get(_container_name(device_key)).remove(force=True)
        return True
    except Exception:
        return False
