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
                    f"{self.host}:{self.port}"
                    f"{self.path}")
        self.poll_rate = config.poll_rate
        self.timeout = config.timeout
        self.verify = config.cert_path if config.cert_path else config.verify_ssl

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
                timeout = self.timeout,
                verify = self.verify
            )
            res.raise_for_status()
            return res.json()
        except requests.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            raise