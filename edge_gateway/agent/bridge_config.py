"""Apply the server bridge IP to the HiveMQ bridge config and restart the broker.

Needs the broker config dir + Docker socket mounted (both present in the
container). Without them (host-Python dev) it degrades to a no-op.
"""

import logging
import os
import re
from pathlib import Path

log = logging.getLogger("bridge")

BRIDGE_CONFIG_PATH = os.getenv(
    "BRIDGE_CONFIG_PATH",
    "/app/broker/extensions/hivemq-bridge-extension/conf/config.xml",
)
HIVEMQ_CONTAINER = os.getenv("HIVEMQ_CONTAINER", "hivemq")


def apply_bridge_ip(server_ip: str) -> bool:
    """Rewrite the bridge <host> and restart HiveMQ. Returns True if restarted."""
    if not _rewrite_host(server_ip):
        return False
    return _restart_hivemq()


def _rewrite_host(server_ip: str) -> bool:
    path = Path(BRIDGE_CONFIG_PATH)
    if not path.exists():
        log.warning("bridge config not found at %s; skipping re-template", path)
        return False
    xml = path.read_text(encoding="utf-8")
    # Regex (not ElementTree) to preserve the xsi schema attributes and comments.
    new_xml, n = re.subn(
        r"(<host>).*?(</host>)", rf"\g<1>{server_ip}\g<2>", xml, count=1, flags=re.S
    )
    if n == 0:
        log.warning("no <host> element in bridge config; skipping")
        return False
    if new_xml != xml:
        path.write_text(new_xml, encoding="utf-8")
        log.info("bridge config <host> set to %s", server_ip)
    return True


def _restart_hivemq() -> bool:
    try:
        import docker

        docker.from_env().containers.get(HIVEMQ_CONTAINER).restart()
        log.info("restarted HiveMQ container '%s'", HIVEMQ_CONTAINER)
        return True
    except Exception:
        log.exception("failed to restart HiveMQ container '%s'", HIVEMQ_CONTAINER)
        return False
