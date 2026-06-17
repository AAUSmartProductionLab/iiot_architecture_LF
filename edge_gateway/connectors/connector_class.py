"""
A Connector: composes a protocol client + an MQTT publisher into a polling loop.

It reads each configured datapoint from the field protocol (Modbus, S7, …) and
publishes the value to the gateway's local MQTT broker on the datapoint's local
topic; the HiveMQ bridge forwards it on to the edge server (UNS).

Config shape (typically passed as CONNECTOR_CONFIG JSON to the adapter container):
    {
      "device_key": "...", "protocol": "s7",
      "connection": { ...protocol connection params... },
      "datapoints": [ {"name","datatype","unit","local_topic","address":{...}} ],
      "mqtt": {"broker_host","broker_port"}, "interval": 2.0
    }
"""

import json
import logging
import time

from .connector_components.mqtt_pub_class import MqttPublisher

log = logging.getLogger("connector")


class Connector:
    def __init__(self, config: dict):
        self.config = config
        self.protocol = (config.get("protocol") or "").lower()
        self.connection = config.get("connection", {}) or {}
        self.datapoints = config.get("datapoints", []) or []
        self.mqtt_cfg = config.get("mqtt", {}) or {}
        self.interval = float(config.get("interval", 2.0))
        self.client = self._make_client()
        self.publisher = MqttPublisher(
            self.mqtt_cfg.get("broker_host", "localhost"),
            int(self.mqtt_cfg.get("broker_port", 1883)),
            client_id=config.get("device_key"),
        )

    def _make_client(self):
        p = self.protocol
        if p.startswith("s7") or p == "snap7":
            from .connector_components.s7_client_class import S7Client

            return S7Client(
                self.connection.get("host"),
                self.connection.get("rack", 0),
                self.connection.get("slot", 1),
            )
        if p.startswith("modbus"):
            from .connector_components.modbus_sync_tcp_client_class import ModbusClient

            return ModbusClient(
                self.connection.get("host"), int(self.connection.get("port", 502))
            )
        raise ValueError(f"unsupported protocol: {self.protocol}")

    def _connect_with_retry(self):
        while True:
            try:
                self.client.connect()
                if getattr(self.client, "connected", True):
                    return
            except Exception as e:
                log.warning("connect failed (%s); retrying in 3s", e)
            time.sleep(3)

    def run(self):
        self._connect_with_retry()
        self.publisher.connect()
        log.info("connector running: protocol=%s datapoints=%d", self.protocol, len(self.datapoints))
        while True:
            for dp in self.datapoints:
                try:
                    value = self.client.read_datapoint(dp)
                    topic = dp.get("local_topic") or f"devices/{dp.get('name')}"
                    self.publisher.publish(topic, json.dumps({"value": value, "ts": time.time()}))
                except Exception:
                    log.exception("read/publish failed for %s", dp.get("name"))
            time.sleep(self.interval)
