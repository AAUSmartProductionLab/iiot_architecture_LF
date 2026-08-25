"""
This module defines an HTTP client for accessing data via 
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
        self.port = config.port
        self.url = f"http://{config.host}:{config.port}{config.uri}"
        self.poll_rate = config.poll_rate
        self.timeout = config.timeout

        self.session = requests.Session()

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

    def close(self):
        self.session.close()