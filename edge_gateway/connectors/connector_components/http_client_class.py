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
    #------------------------------
    # Instantiation
    #------------------------------
    def __init__(self, config: HTTPClientConfig):
        # Attributes
        self.host = config.host
        self.path = config.path if config.path.startswith("/") else f"/{config.path}"
        self.protocol = config.protocol.lower()
        self.timeout = config.timeout
        self.verify = config.cert_path if config.cert_path else config.verify_ssl
        self.port = config.port

        # URL Construction
        self.url = (f"{self.protocol}://"
                    f"{self.host}"
                    f"{f':{self.port}' if self.port is not None else ''}"
                    f"{self.path}")
        self.poll_rate = config.poll_rate

        # Session instantiation
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