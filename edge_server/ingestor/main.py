"""
Event-driven TimescaleDB ingestion.

Subscribes once to the wildcard `uns/#` (covers all current + future device
topics, no broker restart) and to BaSyx submodel events. Device AID
create/update events (diff-gated) populate `topic_map`; data messages are looked
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
from .aid_parser import parse_aid
from .timescale import Timescale

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ingestor")

ts = Timescale(config.TS_DSN)
_signatures: dict[str, str] = {}  # device -> schema signature (diff-gate)


def apply_aid(submodel: dict) -> None:
    points = parse_aid(submodel)
    if not points:
        return
    device = points[0]["device"]
    sig = hashlib.sha256(
        json.dumps(sorted((p["uns_topic"], p["datatype"], p["unit"]) for p in points)).encode()
    ).hexdigest()
    if _signatures.get(device) == sig:
        return  # no real change -> no churn
    _signatures[device] = sig
    for p in points:
        ts.upsert_topic({"topic": p["uns_topic"], **p})
    log.info("configured ingestion: device=%s datapoints=%d", device, len(points))


def backfill() -> None:
    try:
        r = httpx.get(f"{config.BASYX_URL}/submodels", timeout=10)
        for sm in r.json().get("result", []):
            apply_aid(sm)
    except Exception:
        log.exception("backfill failed")


def on_message(client, userdata, msg) -> None:
    if msg.topic.startswith("sm-repository/"):
        try:
            apply_aid(json.loads(msg.payload))
        except Exception:
            log.exception("event handling failed: %s", msg.topic)
        return
    # data plane
    try:
        payload = json.loads(msg.payload)
    except Exception:
        return
    meta = ts.lookup(msg.topic) or {}
    try:
        ts.insert(
            msg.topic,
            payload.get("value"),
            meta.get("device"),
            meta.get("datapoint"),
            meta.get("unit"),
            payload.get("ts"),
        )
    except Exception:
        log.exception("insert failed: %s", msg.topic)


def main() -> None:
    ts.connect()
    backfill()

    client = mqtt.Client(client_id="timescale-ingestor")
    client.on_connect = lambda c, u, f, rc: (
        c.subscribe(config.EVENT_TOPIC),
        c.subscribe(config.DATA_TOPIC),
        log.info("subscribed: %s, %s", config.EVENT_TOPIC, config.DATA_TOPIC),
    )
    client.on_message = on_message
    client.connect(config.BROKER_HOST, config.BROKER_PORT)
    client.loop_start()

    while True:
        time.sleep(config.REFRESH_INTERVAL)
        backfill()  # periodic safety net


if __name__ == "__main__":
    main()
