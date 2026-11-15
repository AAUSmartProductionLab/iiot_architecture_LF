from datetime import datetime
from urllib.parse import urlsplit, parse_qs

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator import api, config
from orchestrator.basyx_client import to_validated_json
from orchestrator.registration_service import RegistrationService
from festo_module import connector


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_API_BASE_URL", "https://history.example.test")
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_aas_describes_source_live_and_history(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_API_BASE_URL", "https://history.example.test")
    monkeypatch.setattr(config, "PUBLIC_MQTT_URL", "mqtts://broker.example.test:8883")
    svc = RegistrationService()
    mqtt = svc._gateway_mqtt({"mqtt": {"local_broker_host": "mqtt-broker", "local_broker_port": 1883},
                             "bridge": {"uns_prefix": "uns/site", "server_ip": "192.0.2.20"}})
    sms, shell = svc._build_device("GW1", connector("opc.tcp://192.0.2.40:14840"), mqtt)
    encoded = [to_validated_json(s) for s in sms]
    shell = to_validated_json(shell)
    ts = next(s for s in encoded if s["idShort"] == "TimeSeries")
    assert any(r["keys"][0]["value"] == ts["id"] for r in shell["submodels"])
    assert ts["semanticId"]["keys"][0]["value"] == "https://admin-shell.io/idta/TimeSeries/1/1"
    segments = next(e for e in ts["submodelElements"] if e["idShort"] == "Segments")["value"]
    assert len(segments) == 5
    properties = {e["idShort"]: e.get("value") for e in segments[0]["value"]}
    assert properties["Endpoint"] == "https://history.example.test/api/measurements/history"
    assert parse_qs(properties["Query"])["device"] == ["GW1_festo_trial"]
    aid = next(s for s in encoded if s["idShort"] == "AssetInterfacesDescription")
    iface = next(e for e in aid["submodelElements"] if e["idShort"] == "InterfaceMQTT")
    ep = next(e for e in iface["value"] if e["idShort"] == "EndpointMetadata")
    assert next(e["value"] for e in ep["value"] if e["idShort"] == "base") == "mqtts://broker.example.test:8883"
    from ingestor.aid_parser import parse_aid
    assert all(p["uns_topic"].startswith("uns/site/devices/festo_trial/") for p in parse_aid(aid))
    # Different device IDs cannot share a history query; reserved characters round-trip.
    cfg = connector("opc.tcp://host:4840")
    cfg["datapoints"][0]["name"] = "temperature & pressure"
    cfg["datapoints"] = cfg["datapoints"][:1]
    updated, _ = svc._build_device("GW2", cfg, mqtt)
    ts2 = next(s for s in map(to_validated_json, updated) if s["idShort"] == "TimeSeries")
    seg = ts2["submodelElements"][1]["value"]
    assert len(seg) == 1
    query = next(e["value"] for e in seg[0]["value"] if e["idShort"] == "Query")
    assert parse_qs(query)["datapoint"] == ["temperature & pressure"]
    assert parse_qs(query)["device"] == ["GW2_festo_trial"]


def test_default_window_and_pagination(client, monkeypatch):
    calls = []
    def history(*args):
        calls.append(args)
        return [{"time": "2026-11-15T00:00:00+00:00", "unit": "old-unit", "value": 1}], True
    monkeypatch.setattr(api.measurements, "history", history)
    result = client.get("/api/measurements/history", params={"device": "GW1_festo_trial", "datapoint": "carrier_id", "limit": 1})
    assert result.status_code == 200
    body = result.json()
    assert (datetime.fromisoformat(body["end"]) - datetime.fromisoformat(body["start"])).total_seconds() == 3600
    query = parse_qs(urlsplit(body["next_url"]).query)
    assert query["offset"] == ["1"] and query["start"] == [body["start"]]
    assert body["records"][0]["unit"] == "old-unit"


@pytest.mark.parametrize("extra", [
    {"start": "2026-11-15T00:00:00"}, {"limit": 10001}, {"offset": -1},
    {"start": "2026-11-15T00:00:00Z", "end": "2026-11-14T00:00:00Z"},
    {"start": "2026-01-01T00:00:00Z", "end": "2026-11-15T00:00:00Z"},
])
def test_invalid_queries_do_not_touch_database(client, monkeypatch, extra):
    monkeypatch.setattr(api.measurements, "history", lambda *a: pytest.fail("invalid query reached DB"))
    result = client.get("/api/measurements/history", params={"device": "d", "datapoint": "p", **extra})
    assert result.status_code == 422


def test_empty_is_distinct_from_outage(client, monkeypatch):
    monkeypatch.setattr(api.measurements, "history", lambda *a: ([], False))
    assert client.get("/api/measurements/history?device=d&datapoint=p").json()["records"] == []
    def fail(*args):
        raise RuntimeError("private connection details")
    monkeypatch.setattr(api.measurements, "history", fail)
    result = client.get("/api/measurements/history?device=d&datapoint=p")
    assert result.status_code == 503 and "private" not in result.text


def test_public_urls_cannot_embed_credentials():
    with pytest.raises(ValueError):
        config._public_url("https://user:secret@server", ("https",))


def test_pagination_cap_is_explicit(client, monkeypatch):
    monkeypatch.setattr(api.measurements, "history", lambda *args: ([], True))
    result = client.get("/api/measurements/history?device=d&datapoint=p&offset=100000&limit=1000")
    assert result.status_code == 200
    assert result.json()["has_more"] and result.json()["page_limit_reached"]
    assert result.json()["next_url"] is None
