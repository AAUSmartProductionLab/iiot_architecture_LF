"""Adapter container entrypoint: build a Connector from CONNECTOR_CONFIG and run it.

    docker run -e CONNECTOR_CONFIG='{...}' iiot/connector-adapter
"""

import json
import logging
import os

from .connector_class import Connector

logging.basicConfig(level=logging.INFO)


def main() -> None:
    config = json.loads(os.environ["CONNECTOR_CONFIG"])
    Connector(config).run()


if __name__ == "__main__":
    main()
