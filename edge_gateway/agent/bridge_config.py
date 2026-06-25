"""Apply the server bridge IP to the HiveMQ bridge config and restart the broker.

Needs the broker config dir + Docker socket mounted (both present in the
container). Without them (host-Python dev) it degrades to a no-op.
"""

import logging
import os
import re
from pathlib import Path

import docker

log = logging.getLogger("bridge")

BRIDGE_CONFIG_PATH = os.getenv(
    "BRIDGE_CONFIG_PATH",
    "/app/broker/extensions/hivemq-bridge-extension/conf/config.xml",
)
HIVEMQ_CONTAINER = os.getenv("HIVEMQ_CONTAINER", "hivemq")


def apply_bridge_ip(server_ip: str, uns_prefix: str | None = None) -> bool:
    """Rewrite the bridge <host> (and, if given, the UNS destination) and restart
    HiveMQ. Returns True if the broker was restarted."""
    if not _rewrite_config(server_ip, uns_prefix):
        return False
    return _restart_hivemq()


def _rewrite_config(server_ip: str, uns_prefix: str | None) -> bool:
    path = Path(BRIDGE_CONFIG_PATH)
    if not path.exists():
        log.warning("bridge config not found at %s; skipping re-template", path)
        return False
    xml = orig = path.read_text(encoding="utf-8")
    # Regex (not ElementTree) to preserve the xsi schema attributes and comments.
    # The host value is a plain address, so match `[^<]*` between the tags: that
    # way a stray "<host>" token elsewhere (e.g. in a comment) can't anchor a
    # greedy match that swallows the real tags in between.
    xml, n = re.subn(
        r"(<host>)[^<]*(</host>)", rf"\g<1>{server_ip}\g<2>", xml, count=1
    )
    if n == 0:
        log.warning("no <host> element in bridge config; skipping")
        return False

    if uns_prefix:
        prefix = uns_prefix.strip().strip("/")
        # PUB topic destination: <uns-prefix>/{#} (HiveMQ substitutes {#} with the
        # matched local topic). {{#}} in the rf-string emits a literal {#}.
        xml, dn = re.subn(
            r"(<destination>)[^<]*(</destination>)",
            rf"\g<1>{prefix}/{{#}}\g<2>", xml, count=1,
        )
        # SUB commands filter mirrors the UNS path with its leading segment swapped
        # to "commands" (uns/site/... -> commands/site/...), anchored on the
        # existing "commands/" so the PUB filter ("#") is left untouched.
        parts = prefix.split("/")
        cmd = "/".join(["commands", *parts[1:]]) if len(parts) > 1 else "commands"
        xml, _ = re.subn(
            r"(<filter>)commands/[^<]*(</filter>)",
            rf"\g<1>{cmd}/#\g<2>", xml, count=1,
        )
        if dn:
            log.info("bridge UNS destination set to %s/{#}", prefix)

    if xml != orig:
        path.write_text(xml, encoding="utf-8")
        log.info("bridge config updated (host=%s)", server_ip)
    return True


def restart_broker() -> bool:
    """Restart the HiveMQ container without touching config.

    Used on a timer to reset the HiveMQ Enterprise Bridge Extension's 5-hour
    trial (each restart re-enters trial mode), keeping the bridge alive.
    """
    return _restart_hivemq()


def _restart_hivemq() -> bool:
    try:
        docker.from_env().containers.get(HIVEMQ_CONTAINER).restart()
        log.info("restarted HiveMQ container '%s'", HIVEMQ_CONTAINER)
        return True
    except Exception:
        log.exception("failed to restart HiveMQ container '%s'", HIVEMQ_CONTAINER)
        return False
