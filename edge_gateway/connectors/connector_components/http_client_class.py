"""
This module defines an HTTP/HTTPS client for accessing data via 
REST APIs. 
"""

import requests
import logging
from .models import HTTPClientConfig

logger = logging.getLogger(__name__)

class HTTPClient:
    """
    An HTTP Client.
    """

    def __init__(self, config: HTTPClientConfig):
        self.host = config.host
        self.path = config.path if config.path.startswith("/") else f"/{config.path}"
        self.protocol = config.protocol.lower()
        if config.port is None:
            if self.protocol == "https":
                self.port = 443
            else:
                self.port = 80
        else:
            self.port = config.port
        self.url = (f"{self.protocol}://"
                    f"{self.host}:{self.port if self.port is not None else ''}"
                    f"{self.path}")
        self.poll_rate = config.poll_rate
        self.timeout = config.timeout

        self.session = requests.Session()

    #------------------------------
    # Connection / Disconneciton
    #------------------------------

    def close(self):
        self.session.close()

    # -------------------------
    # Read
    # -------------------------

    def read(self):
        try:
            res = self.session.get(
                self.url,
                timeout=self.timeout
                )
            res.raise_for_status()
            return res.json()
        except requests.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            raise