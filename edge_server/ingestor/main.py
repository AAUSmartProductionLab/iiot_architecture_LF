"""
Event-driven TimescaleDB ingestion.

Subscribes once to the wildcard `uns/#` (covers all current + future device
topics, no broker restart) and to BaSyx submodel events. Device AID
create/update events (diff-gated) populate `topic_map`; delete events (and
datapoints dropped from an AID) remove their mappings. Data messages are looked
up and inserted into `measurements`. AAS is the config source only — telemetry
values never flow through the AAS.
"""

import hashlib
import json
import logging
import time

import httpx
import paho.mqtt.client as mqtt

from . import config
from .aid_parser import _device_from_id, parse_aid
from .timescale import Timescale

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ingestor")

ts = Timescale(config.TS_DSN)
_signatures: dict[str, str] = {}  # device -> schema signature (diff-gate)


def apply_aid(submodel: dict) -> None:
    if not config.AUTO_MAPPING_ENABLED:
        return
    points = parse_aid(submodel)
    if not points:
        return
    device = points[0]["device"]
    sig = hashlib.sha256(
        json.dumps(sorted((p["uns_topic"], p["datatype"], p["unit"]) for p in points)).encode()
    ).hexdigest()
    if _signatures.get(device) == sig:
        return  # no real change -> no churn
    for p in points:
        ts.upsert_topic({"topic": p["uns_topic"], **p})
    removed = ts.remove_device_topics(device, keep={p["uns_topic"] for p in points})
    _signatures[device] = sig  # Only mark applied after all database writes succeed.
    log.info("configured ingestion: device=%s datapoints=%d (removed %d)", device, len(points), removed)


def remove_aid(submodel: dict) -> None:
    if not submodel or submodel.get("idShort") != "AssetInterfacesDescription":
        return
    device = _device_from_id(submodel.get("id", ""))
    _signatures.pop(device, None)
    removed = ts.remove_device_topics(device)
    if removed:
        log.info("device AID deleted: device=%s, removed %d mapping(s)", device, removed)


def backfill() -> None:
    if not config.AUTO_MAPPING_ENABLED:
        return
    try:
        r = httpx.get(f"{config.BASYX_URL}/submodels", timeout=10)
        r.raise_for_status()
        for sm in r.json().get("result", []):
            apply_aid(sm)
    except Exception:
        log.exception("backfill failed")


def _sample(payload) -> tuple[object, float | None]:
    """Split a message into (value, timestamp).

    Adapters publish {"value": ..., "ts": <unix seconds>}; a device publishing
    natively may send a bare JSON value (e.g. 21.5) or an object without "value".
    """
    if isinstance(payload, dict) and "value" in payload:
        stamp = payload.get("ts")
        return payload["value"], stamp if isinstance(stamp, (int, float)) else None
    return payload, None


def on_message(client, userdata, msg) -> None:
    # Never let an exception escape: paho re-raises callback exceptions in its
    # network thread, which would silently stop all ingestion.
    try:
        if msg.topic.startswith("sm-repository/"):
            if not config.AUTO_MAPPING_ENABLED:
                return
            submodel = json.loads(msg.payload)
            if msg.topic.endswith("/deleted"):
                remove_aid(submodel)
            else:
                apply_aid(submodel)
            return
        # data plane
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            log.debug("skipping non-JSON message on %s", msg.topic)
            return
        value, stamp = _sample(payload)
        meta = ts.lookup(msg.topic) or {}
        ts.insert(msg.topic, value, meta.get("device"), meta.get("datapoint"), meta.get("unit"), stamp)
    except Exception:
        log.exception("message handling failed: %s", msg.topic)


def on_connect(client, userdata, flags, reason_code, properties) -> None:
    if reason_code.is_failure:
        log.error("MQTT connect failed: %s", reason_code)
        return
    # (Re)subscribe on every connect so a broker restart doesn't end ingestion.
    if config.AUTO_MAPPING_ENABLED:
        client.subscribe(config.EVENT_TOPIC)
    client.subscribe(config.DATA_TOPIC)
    log.info("subscribed: %s, %s", config.EVENT_TOPIC, config.DATA_TOPIC)


def main() -> None:
    ts.connect()
    backfill()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="timescale-ingestor")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.BROKER_HOST, config.BROKER_PORT)
    client.loop_start()

    while True:
        time.sleep(config.REFRESH_INTERVAL)
        backfill()  # periodic safety net


if __name__ == "__main__":
    main()
