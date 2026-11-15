"""Write the Mosquitto bridge to the edge server and restart the local broker.

The gateway's local Mosquitto includes every *.conf in its conf.d directory. The
bridge lives in conf.d/bridge.conf, which this module (re)writes from the server
IP and UNS prefix; Mosquitto only reads bridge settings at startup, so the broker
container is restarted afterwards.

Needs the broker config dir + Docker socket mounted (both present in the agent
container). Without them (host-Python dev) it degrades to a no-op.
"""

import logging
import os
import re
from pathlib import Path

import docker

from . import config

log = logging.getLogger("bridge")

BRIDGE_CONFIG_PATH = os.getenv("BRIDGE_CONFIG_PATH", "/app/broker/config/conf.d/bridge.conf")

_SAFE_HOST = re.compile(r"^[A-Za-z0-9.\-:\[\]]+$")
_SAFE_TOPIC = re.compile(r"^[A-Za-z0-9_\-./]+$")


def render_bridge(server_ip: str, uns_prefix: str, server_port: int = 1883) -> str:
    """Mosquitto bridge config.

    Data: local `devices/<x>` -> server `<uns_prefix>/devices/<x>` (the AID's
    uns_topic mirrors this; see orchestrator registration_service._uns_topic).
    Commands: server `commands/<site path>/#` -> same topic locally, for the
    planned bidirectional extension. The two directions use disjoint topic
    trees, so nothing is echoed back.
    """
    if not _SAFE_HOST.match(server_ip or ""):
        raise ValueError(f"invalid server address {server_ip!r}")
    prefix = (uns_prefix or "").strip().strip("/")
    if not prefix or not _SAFE_TOPIC.match(prefix):
        raise ValueError(f"invalid UNS prefix {uns_prefix!r}")
    base = config.LOCAL_BASE_TOPIC.strip("/")
    parts = prefix.split("/")
    commands = "/".join(["commands", *parts[1:]]) if len(parts) > 1 else "commands"
    return "\n".join(
        [
            "# Written by the gateway agent (POST /api/configure). Do not edit by hand.",
            "connection edge-server",
            f"address {server_ip}:{server_port}",
            f"remote_clientid bridge-{config.GATEWAY_ID}",
            "cleansession true",
            "try_private false",
            "notifications false",
            "restart_timeout 2 30",
            f'topic {base}/# out 0 "" {prefix}/',
            f"topic {commands}/# in 0",
            "",
        ]
    )


def apply_bridge_ip(server_ip: str, uns_prefix: str | None = None) -> bool:
    """(Re)write the bridge config and restart the broker. Returns True if the
    broker was restarted."""
    path = Path(BRIDGE_CONFIG_PATH)
    if not path.parent.is_dir():
        log.warning("broker conf.d not found at %s; skipping bridge config", path.parent)
        return False
    text = render_bridge(server_ip, uns_prefix or config.UNS_PREFIX)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
        log.info("bridge config written (server=%s, uns=%s)", server_ip, uns_prefix)
    return restart_broker()


def restart_broker() -> bool:
    try:
        docker.from_env().containers.get(config.BROKER_CONTAINER).restart()
        log.info("restarted broker container '%s'", config.BROKER_CONTAINER)
        return True
    except Exception:
        log.exception("failed to restart broker container '%s'", config.BROKER_CONTAINER)
        return False
