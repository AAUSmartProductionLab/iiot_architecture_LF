"""Orchestrator AAS (AID) and the ingestor's message handling, without services."""

import json
from types import SimpleNamespace

from basyx.aas.adapter import json as aas_json

from ingestor import main as ingestor
from ingestor.aid_parser import parse_aid
from orchestrator.api import ProvisionReq
from orchestrator.registration_service import RegistrationService

MQTT = {"broker_host": "gw", "broker_port": 1883, "uns_prefix": "uns/aau/lab"}


def device_aid(datapoints, interval=0.5):
    connector = {
        "device_key": "cell", "protocol": "s7", "connection": {"host": "10.0.0.5"}, "interval": interval,
        "datapoints": [
            {"name": n, "datatype": "real", "unit": u, "local_topic": f"devices/{n}", "address": {"start": 4 * i}}
            for i, (n, u) in enumerate(datapoints)
        ],
    }
    submodels, _shell = RegistrationService()._build_device("GW1", connector, MQTT)
    aid = next(s for s in submodels if s.id_short == "AssetInterfacesDescription")
    return json.loads(json.dumps(aid, cls=aas_json.AASToJsonEncoder))


def test_aid_has_uns_topics_and_polling_time():
    aid = device_aid([("torque", "Nm"), ("angle", "deg")])
    rows = parse_aid(aid)
    assert [(r["uns_topic"], r["unit"]) for r in rows] == [
        ("uns/aau/lab/devices/torque", "Nm"),
        ("uns/aau/lab/devices/angle", "deg"),
    ]
    assert json.dumps(aid).count('"pollingTime"') == 2


def test_provision_request_does_not_send_nulls():
    body = {"gateway_id": "g", "device_id": "d", "protocol": "s7", "connection": {}, "datapoints": []}
    dumped = ProvisionReq(**body).model_dump(exclude={"gateway_id"}, exclude_none=True)
    assert "interval" not in dumped and "manufacturer" not in dumped


class FakeTs:
    def __init__(self):
        self.topics = {}
        self.rows = []

    def upsert_topic(self, t):
        self.topics[t["topic"]] = {k: t.get(k) for k in ("device", "datapoint", "unit")}

    def remove_device_topics(self, device, keep=None):
        stale = [t for t, m in self.topics.items() if m["device"] == device and t not in (keep or set())]
        for t in stale:
            del self.topics[t]
        return len(stale)

    def lookup(self, topic):
        return self.topics.get(topic)

    def insert(self, topic, value, device, datapoint, unit, ts=None):
        self.rows.append((topic, value, device, datapoint, unit, ts))


def msg(topic, payload):
    return SimpleNamespace(topic=topic, payload=payload if isinstance(payload, bytes) else json.dumps(payload).encode())


def test_ingestor_messages(monkeypatch):
    fake = FakeTs()
    monkeypatch.setattr(ingestor, "ts", fake)
    monkeypatch.setattr(ingestor, "_signatures", {})
    ingestor.on_message(None, None, msg("sm-repository/r/submodels/created", device_aid([("torque", "Nm"), ("angle", "deg")])))
    assert set(fake.topics) == {"uns/aau/lab/devices/torque", "uns/aau/lab/devices/angle"}

    ingestor.on_message(None, None, msg("uns/aau/lab/devices/torque", {"value": 12.5, "ts": 1.0}))
    ingestor.on_message(None, None, msg("uns/aau/lab/devices/angle", 42.0))       # bare number: used to kill the thread
    ingestor.on_message(None, None, msg("uns/aau/lab/devices/angle", b"not json"))  # skipped
    assert fake.rows[0][:5] == ("uns/aau/lab/devices/torque", 12.5, "GW1_cell", "torque", "Nm")
    assert fake.rows[0][5] == 1.0
    assert fake.rows[1][1] == 42.0 and len(fake.rows) == 2

    # A datapoint dropped from the AID loses its mapping; deleting the AID drops the rest.
    ingestor.on_message(None, None, msg("sm-repository/r/submodels/updated", device_aid([("torque", "Nm")])))
    assert set(fake.topics) == {"uns/aau/lab/devices/torque"}
    ingestor.on_message(None, None, msg("sm-repository/r/submodels/deleted", device_aid([("torque", "Nm")])))
    assert fake.topics == {}


def test_manual_mapping_blocks_events_and_backfill(monkeypatch):
    fake = FakeTs()
    monkeypatch.setattr(ingestor, "ts", fake)
    monkeypatch.setattr(ingestor.config, "AUTO_MAPPING_ENABLED", False)
    monkeypatch.setattr(ingestor.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("backfill called")))
    aid = device_aid([("torque", "Nm")])
    ingestor.apply_aid(aid)
    ingestor.backfill()
    ingestor.on_message(None, None, msg("sm-repository/r/submodels/created", aid))
    assert fake.topics == {}
    fake.upsert_topic({"topic": "uns/torque", "device": "cell", "datapoint": "torque", "unit": "Nm"})
    ingestor.on_message(None, None, msg("sm-repository/r/submodels/deleted", aid))
    ingestor.on_message(None, None, msg("uns/torque", 12.5))
    assert fake.rows[-1][2:5] == ("cell", "torque", "Nm")


def test_aid_retries_after_database_failure(monkeypatch):
    import pytest
    fake = FakeTs()
    monkeypatch.setattr(ingestor, "ts", fake)
    monkeypatch.setattr(ingestor, "_signatures", {})
    aid = device_aid([("torque", "Nm")])
    original = fake.upsert_topic
    fake.upsert_topic = lambda t: (_ for _ in ()).throw(RuntimeError("database unavailable"))
    with pytest.raises(RuntimeError):
        ingestor.apply_aid(aid)
    fake.upsert_topic = original
    ingestor.apply_aid(aid)
    assert fake.topics


def test_discovery_disabled_retains_liveness(monkeypatch):
    import asyncio
    from orchestrator import main
    calls = []

    class Discovery:
        def __init__(self, *a, **k):
            pass
        async def start(self):
            calls.append("discovery_start")
        async def stop(self):
            calls.append("discovery_stop")

    class Monitor:
        def __init__(self, *a, **k):
            pass
        async def start(self):
            calls.append("monitor_start")
        async def stop(self):
            calls.append("monitor_stop")

    monkeypatch.setattr(main, "Discovery", Discovery)
    monkeypatch.setattr(main, "LivenessMonitor", Monitor)
    monkeypatch.setattr(main.config, "DISCOVERY_ENABLED", False)
    async def check():
        async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
            assert calls == ["monitor_start"]
    asyncio.run(check())
    assert calls == ["monitor_start", "monitor_stop"]


def test_discovery_retries_failed_aas_sync(monkeypatch):
    import asyncio
    from orchestrator import discovery
    from orchestrator.registry import Registry

    monkeypatch.setattr(discovery, "registry", Registry())
    monkeypatch.setattr(discovery, "AAS_RETRY_DELAY", 0)
    manifest = {"gateway_id": "gw1", "serial_number": "SN1", "configured_connectors": []}
    info = SimpleNamespace(properties={b"gateway_id": b"gw1"}, port=8000, server="gw1.local.",
                           parsed_addresses=lambda: ["10.0.0.9"])

    class Zeroconf:
        async def async_get_service_info(self, *a):
            return info

    class Client:
        async def get(self, url):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: manifest)

    syncs = []

    async def on_manifest(m, network):
        syncs.append(network["ip"])
        if len(syncs) == 1:
            raise ConnectionError("BaSyx not ready")

    async def check():
        disc = discovery.Discovery(asyncio.get_running_loop(), on_manifest=on_manifest)
        disc.azc = Zeroconf()
        name = "gw1._aasgw._tcp.local."
        await disc._handle_up(Client(), name)  # first sync fails
        assert discovery.registry.get("gw1")["aas_synced"] is False
        retry = await asyncio.wait_for(disc.queue.get(), 1)
        assert retry == (name, discovery.ServiceStateChange.Updated)
        await disc._handle_up(Client(), name)  # retry succeeds
        await disc._handle_up(Client(), name)  # unchanged manifest: no further sync
        assert syncs == ["10.0.0.9", "10.0.0.9"]
        assert discovery.registry.get("gw1")["aas_synced"] is True
        assert disc._retries == {}

    asyncio.run(check())


def test_festo_metadata_preserves_empty_units():
    from festo_module import connector
    cfg = connector("opc.tcp://simulator:14840")
    submodels, _ = RegistrationService()._build_device("GW1", cfg, MQTT)
    aid = next(s for s in submodels if s.id_short == "AssetInterfacesDescription")
    rows = parse_aid(json.loads(json.dumps(aid, cls=aas_json.AASToJsonEncoder)))
    assert len(rows) == 5
    assert all(p["device"] == "GW1_festo_trial" and p["unit"] == "" for p in rows)
    assert all(p["uns_topic"].startswith("uns/aau/lab/devices/festo_trial/") for p in rows)
