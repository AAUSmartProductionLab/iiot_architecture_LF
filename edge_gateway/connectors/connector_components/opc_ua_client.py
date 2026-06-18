"""
A robust async OPC-UA client adapter.
"""

import asyncio
import logging
from asyncua import Client, ua

logger = logging.getLogger(__name__)


class AsyncOPCUAClient:
    def __init__(self, url: str):
        self.url = url
        self.client: Client | None = None
        self._node_cache = {}
        self._connected = False
        self._subscriptions = []

    # -------------------------
    # Connection management
    # -------------------------
    async def connect(self, timeout=4):
        if self._connected:
            return

        try:
            self.client = Client(self.url, timeout=timeout)
            await self.client.connect()
            self._connected = True
            logger.info(f"Connected to {self.url}")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False
            raise

        self._node_cache.clear()

    async def disconnect(self):
        if self.client and self._connected:
            for sub in self._subscriptions:
                await sub.delete()
            self._subscriptions.clear()

            await self.client.disconnect()
            self._connected = False
            logger.info("Disconnected")

    async def reconnect(self, retries=3, delay=2):
        for i in range(retries):
            try:
                await self.disconnect()
                await self.connect()
                return
            
            except Exception:
                if i == retries -1:
                    raise RuntimeError("Reconnect failed")
                logger.warning(f"Reconnect attempt {i+1} failed")
                await asyncio.sleep(delay * (2 ** i))
                

    def is_connected(self):
        return self._connected

    # -------------------------
    # Node handling (cached)
    # -------------------------
    def _ensure_client(self):
        if not self.client or not self._connected:
            raise RuntimeError("Client not connected")
    
    def get_node(self, node_id: str):
        self._ensure_client()
        if node_id not in self._node_cache:
            self._node_cache[node_id] = self.client.get_node(node_id)
        return self._node_cache[node_id]

    # -------------------------
    # Read / Write
    # -------------------------
    async def read(self, node_id: str):
        try:
            node = self.get_node(node_id)
            return await node.read_value()
        except Exception as e:
            logger.error(f"Read failed", extra={"node_id": node_id, "error": str(e)})
            raise

    async def safe_read(self, node_id: str, retries=2):
        for i in range(retries):
            try:
                return await self.read(node_id)
            except Exception:
                if i == retries - 1:
                    raise
                await self.reconnect()
        

    async def write(self, node_id: str, value):
        try:
            node = self.get_node(node_id)
            await node.write_value(ua.Variant(value))
        except Exception as e:
            logger.error("Write failed", extra={"node_id": node_id, "error": str(e)})
            raise

    async def safe_write(self, node_id: str, value, retries=2):
        for i in range(retries):
            try:
                return await self.write(node_id, value)
            except Exception:
                if i == retries - 1:
                    raise
                await self.reconnect()

    # -------------------------
    # Subscriptions
    # -------------------------
    async def subscribe_datachange(self, node_id: str, handler, interval=1000):
        self._ensure_client()

        sub = await self.client.create_subscription(interval, handler)
        node = self.get_node(node_id)
        handle = await sub.subscribe_data_change(node)

        self._subscriptions.append(sub)
        return sub, handle

    # -------------------------
    # Context manager
    # -------------------------
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()