"""Adapter container entrypoint: load the connector config, build a Connector, run it.

Config comes from CONNECTOR_CONFIG (a JSON env var the gateway-agent sets when it
launches the container) or, as a fallback for local runs, a JSON file at
CONFIG_PATH (default ./config.json). It is deserialized into a validated
ConnectorConfig, which selects the protocol client.

    docker run -e CONNECTOR_CONFIG='{...}' iiot/connector-adapter
    python -m connectors.run_adapter            # reads ./config.json
"""

import asyncio
import logging
import os

from .config_model import parse_connector
from .connector_class import Connector

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("run_adapter")


def _load_config():
    raw = os.environ.get("CONNECTOR_CONFIG")
    if raw:
        return parse_connector(raw)
    path = os.environ.get("CONFIG_PATH", "config.json")
    with open(path, encoding="utf-8") as f:
        return parse_connector(f.read())


def main() -> None:
    config = _load_config()
    log.info("starting adapter for device_key=%s protocol=%s", config.device_key, config.protocol)
    asyncio.run(Connector(config).run())


if __name__ == "__main__":
    main()
