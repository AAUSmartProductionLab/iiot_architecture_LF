"""Connector: instantiate a protocol client (chosen by config.protocol) plus an
MQTT publisher, then stream each datapoint's value to its local topic.

The per-protocol reading lives in the connector_components clients (Modbus, S7,
OPC UA); this module is just the wiring. Each client exposes an async
`subscribe(datapoints, on_value, interval)` that polls its own `read` under the
hood and calls `on_value(dp, value)` for every sample — here that publishes to
the gateway's local MQTT broker on the datapoint's local topic; the HiveMQ
bridge forwards it to the edge server (UNS).

Adding a protocol = adding a client + one case in `_make_client`.
"""

import asyncio
import json
import logging
import time

from .config_model import ConnectorConfig
from .connector_components.models import S7ClientConfig
from .connector_components.mqtt_pub_class import MqttPublisher
from .connector_components.s7_client_class import S7Client

# The Modbus and OPC UA clients are mid-rework (dataclass-based config + a
# `models.models` import) and are not yet wired to this Connector's uniform
# dict-based interface. Import them defensively so an in-progress / incompatible
# client module can't take down the whole adapter — S7 still works. A clear error
# is raised in _make_client only if one of those protocols is actually requested.
try:
    from .connector_components.modbus_async_tcp_client_class import AsyncModbusClient
except Exception:  # noqa: BLE001 - tolerate an in-progress client module
    AsyncModbusClient = None

try:
    from .connector_components.opc_ua_client import AsyncOPCUAClient
except Exception:  # noqa: BLE001 - tolerate an in-progress client module
    AsyncOPCUAClient = None

log = logging.getLogger("connector")

# Structured markers the gateway-agent greps out of `docker logs` to report a
# connector's live connection state back to the UI. Keep these strings stable.
MARK_CONNECTED = "CONNECTED"
MARK_FAILED = "CONNECT_FAILED"


async def _maybe_await(result):
    """Await `result` if it's a coroutine (async clients), else return it as-is
    (sync clients like S7's blocking connect())."""
    if asyncio.iscoroutine(result):
        return await result
    return result


def _classify_connect_error(e: Exception) -> tuple[str, str]:
    """Map a raw connect exception to a short, user-facing reason + detail.

    The reason is what the wizard shows ("timeout", "connection refused", …);
    the detail is the full message, kept for the Logs tab.
    """
    detail = str(e) or e.__class__.__name__
    s = detail.lower()
    if "timed out" in s or "timeout" in s:
        return "timeout", detail
    if "refused" in s:
        return "connection refused", detail
    if any(t in s for t in ("unreachable", "no route", "name or service", "resolve", "getaddrinfo")):
        return "host unreachable", detail
    return "failed to connect", detail


class Connector:
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.client = self._make_client()
        self.publisher = MqttPublisher(
            config.mqtt.broker_host,
            config.mqtt.broker_port,
            client_id=config.device_key,
        )

    def _make_client(self):
        # The discriminated union guarantees `protocol` is one of these three and
        # that `connection` is the matching typed model.
        c = self.config
        if c.protocol == "modbus-tcp":
            if AsyncModbusClient is None:
                raise ValueError("modbus-tcp adapter unavailable (client integration in progress)")
            return AsyncModbusClient(c.connection.model_dump())
        if c.protocol == "opcua":
            if AsyncOPCUAClient is None:
                raise ValueError("opcua adapter unavailable (client integration in progress)")
            return AsyncOPCUAClient(c.connection.endpoint_url)
        if c.protocol == "s7":
            return S7Client(
                S7ClientConfig(
                    host=c.connection.host,
                    rack=c.connection.rack,
                    slot=c.connection.slot,
                )
            )
        raise ValueError(f"unsupported protocol: {c.protocol}")

    def _publish(self, dp: dict, value):
        topic = dp.get("local_topic") or f"devices/{dp.get('name')}"
        payload = json.dumps({"value": value, "ts": time.time()})
        # Publish JSON {value, ts} straight to the datapoint topic — the shape the
        # server ingestor expects (it json.loads the payload and reads `value`/`ts`,
        # resolving the device via the AID topic map). We go through the publisher's
        # underlying paho client because MqttPublisher.publish() fans a *dict* out to
        # per-key subtopics, which doesn't match that UNS/AID contract.
        if not self.publisher.connected:
            return
        info = self.publisher.client.publish(topic, payload, qos=self.publisher.qos)
        info.wait_for_publish()

    async def run(self):
        """Connect the protocol client + MQTT publisher, then stream values.

        Connect is retried (rather than crash-looping the container) so the
        connection state stays observable: each attempt logs a CONNECTED or
        CONNECT_FAILED marker the gateway-agent reads back for the UI. subscribe()
        polls each datapoint and the _publish callback forwards it to the broker;
        a mid-stream failure drops back to the reconnect loop.
        """
        self.publisher.connect()
        # by_alias keeps wire names (e.g. Modbus "register") in the address dicts
        # the protocol clients read from.
        datapoints = [dp.model_dump(by_alias=True) for dp in self.config.datapoints]
        backoff = max(self.config.interval, 2.0)
        try:
            while True:
                try:
                    await _maybe_await(self.client.connect())
                except Exception as e:  # noqa: BLE001 - report + retry any connect failure
                    reason, detail = _classify_connect_error(e)
                    log.error("%s reason=%s detail=%s", MARK_FAILED, reason, detail)
                    await asyncio.sleep(backoff)
                    continue
                log.info("%s protocol=%s datapoints=%d", MARK_CONNECTED, self.config.protocol, len(datapoints))
                try:
                    await self.client.subscribe(datapoints, self._publish, self.config.interval)
                except Exception as e:  # noqa: BLE001 - lost connection mid-stream; reconnect
                    log.error("STREAM_ERROR detail=%s", e)
                    await _maybe_await(self.client.disconnect())
                    await asyncio.sleep(backoff)
        finally:
            await _maybe_await(self.client.disconnect())
            self.publisher.disconnect()
