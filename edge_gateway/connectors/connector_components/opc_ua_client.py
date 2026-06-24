"""
A robust async OPC-UA client adapter.
"""

import asyncio
import logging
from asyncua import Client, ua
from iiot_architecture_LF.edge_gateway.connectors.connector_components.models import OPCUAReadRequest, OPCUAWriteRequest, OPCUAClientConfig

logger = logging.getLogger(__name__)


class AsyncOPCUAClient:
    def __init__(self, config: OPCUAClientConfig):
        self.url = config.url
        if not self.url:
            raise ValueError("Missing OPC UA URL argument.")

        self.timeout = config.timeout
        self.client: Client | None = None
        self._node_cache = {}
        self._connected = False
        self._subscriptions = []

    # -------------------------
    # Connection management
    # -------------------------
    async def connect(self):
        if self._connected:
            return

        try:
            self.client = Client(self.url, timeout=self.timeout)
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
    async def _read(self, request: OPCUAReadRequest):
        try:
            node_id = request.node_id
            if node_id is None:
                raise ValueError("Missing 'node_id'")

            node = self.get_node(node_id)
            value = await node.read_value()
            
            return {node_id: value}

        except Exception as e:
            logger.error(f"Read failed on node: {request.node_id}, error: {e}")
            raise

    async def safe_read(self, request: OPCUAReadRequest):

        retries = request.retries
        for i in range(retries):
            try:
                return await self._read(request)
            
            except Exception:
                if i == retries - 1:
                    raise
                await self.reconnect()
        

    async def _write(self, request: OPCUAWriteRequest):
        try:
            node_id = request.node_id
            value = request.value

            if node_id is None:
                raise ValueError("Missing 'node_id'")
            if value is None:
                raise ValueError("Missing 'value'")
            node = self.get_node(node_id)
            await node.write_value(ua.Variant(value))

        except Exception as e:
            logger.error(f"Write failed on node: {request.node_id}, error: {e}")
            raise

    async def safe_write(self, request: OPCUAWriteRequest):

        retries = request.retries
        for i in range(retries):
            try:
                return await self._write(request)
            
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
    # Subscribe (poll loop)
    # -------------------------
    async def subscribe(self, datapoints, on_value, interval=2.0):
        """Poll each datapoint every `interval`s and hand its value to on_value.
        Uses safe_read so a dropped connection is retried transparently. dp's
        node id is read from dp['address']['node_id']."""
        while True:
            for dp in datapoints:
                node_id = (dp.get("address") or {}).get("node_id")
                try:
                    value = await self.safe_read(node_id)
                    on_value(dp, value)
                except Exception as e:
                    logger.error(f"OPC UA read failed for {dp.get('name')}: {e}")
            await asyncio.sleep(interval)

    # -------------------------
    # Context manager
    # -------------------------
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()