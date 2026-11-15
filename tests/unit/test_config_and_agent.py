"""Connector validation, the Mosquitto bridge config and the gateway agent API."""

import importlib
import json

import pytest
from pydantic import ValidationError

from connectors.config_model import parse_connector


def connector(protocol, connection, datapoints, **extra):
    return {"device_key": "d", "protocol": protocol, "connection": connection, "datapoints": datapoints, **extra}


# --- connector model ---------------------------------------------------------

def test_modbus_bit_registers_need_bool():
    dp = {"name": "c", "datatype": "float32", "address": {"register": 0, "register_type": "coil"}}
    with pytest.raises(ValidationError):
        parse_connector(connector("modbus-tcp", {"host": "h"}, [dp]))


def test_modbus_legacy_quantity_is_accepted():
    dp = {"name": "f", "datatype": "float32", "address": {"register": 0, "quantity": 2}}
    assert parse_connector(connector("modbus-tcp", {"host": "h"}, [dp])).datapoints[0].datatype == "float32"


def test_s7_bytes_needs_size_and_unknown_type_rejected():
    ok = {"name": "b", "datatype": "bytes", "address": {"start": 0, "size": 4}}
    parse_connector(connector("s7", {"host": "h"}, [ok]))
    for bad in ({"name": "b", "datatype": "bytes", "address": {"start": 0}},
                {"name": "s", "datatype": "string", "address": {"start": 0}}):
        with pytest.raises(ValidationError):
            parse_connector(connector("s7", {"host": "h"}, [bad]))


def test_interval_bounds():
    dp = {"name": "n", "datatype": "float64", "address": {"node_id": "ns=2;s=x"}}
    assert parse_connector(connector("opcua", {"endpoint_url": "opc.tcp://h:4840"}, [dp], interval=0.5)).interval == 0.5
    with pytest.raises(ValidationError):
        parse_connector(connector("opcua", {"endpoint_url": "opc.tcp://h:4840"}, [dp], interval=0.001))


# --- gateway agent ----------------------------------------------------------------

@pytest.fixture()
def agent(tmp_path, monkeypatch):
    (tmp_path / "conf.d").mkdir()
    (tmp_path / "instances").mkdir()
    monkeypatch.setenv("IDENTITY_FILE", str(tmp_path / "identity.json"))
    monkeypatch.setenv("ADAPTER_CONFIG_DIR", str(tmp_path / "instances"))
    monkeypatch.setenv("BRIDGE_CONFIG_PATH", str(tmp_path / "conf.d" / "bridge.conf"))
    monkeypatch.setenv("GATEWAY_ID", "gw-test")
    monkeypatch.setenv("ADAPTER_AUTOSTART", "false")
    from agent import adapters, bridge_config, config, main, manifest

    for mod in (config, manifest, bridge_config, adapters, main):
        importlib.reload(mod)
    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        yield client, tmp_path, manifest


def test_bridge_config_maps_devices_to_uns(agent):
    from agent.bridge_config import render_bridge

    text = render_bridge("192.168.1.20", "uns/aau/lab/line1")
    assert "address 192.168.1.20:1883" in text
    assert 'topic devices/# out 0 "" uns/aau/lab/line1/' in text
    assert "topic commands/aau/lab/line1/# in 0" in text
    with pytest.raises(ValueError):
        render_bridge("1.2.3.4\nconnection evil", "uns/x")


def test_configure_writes_bridge_and_persists_state(agent):
    client, tmp, manifest = agent
    r = client.post("/api/configure", json={"server_bridge_ip": "10.0.0.9", "uns_prefix": "uns/aau/lab"})
    assert r.status_code == 200
    assert 'out 0 "" uns/aau/lab/' in (tmp / "conf.d" / "bridge.conf").read_text()
    # Simulate an agent restart: in-memory state reset, then restored from disk.
    manifest._bridge.update(configured=False, server_ip=None, uns_prefix="uns/enterprise/site/area/line")
    assert manifest.load_bridge_state()
    assert manifest.get_bridge_state()["uns_prefix"] == "uns/aau/lab"
    assert client.post("/api/configure", json={"server_bridge_ip": "bad host!"}).status_code == 400


def test_connector_with_several_datapoints_and_interval(agent):
    client, tmp, _ = agent
    body = {
        "device_id": "cell", "protocol": "s7", "connection": {"host": "10.0.0.5"}, "interval": 0.5,
        "datapoints": [
            {"name": f"p{i}", "datatype": "real", "local_topic": f"devices/p{i}", "address": {"start": 4 * i}}
            for i in range(3)
        ],
    }
    r = client.post("/api/connectors", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["interval"] == 0.5 and len(r.json()["datapoints"]) == 3
    stored = json.loads((tmp / "instances" / "cell" / "descriptor.json").read_text())
    assert stored["interval"] == 0.5


def test_local_topic_must_be_bridged(agent):
    client, _, _ = agent
    body = {
        "device_id": "x", "protocol": "opcua", "connection": {"endpoint_url": "opc.tcp://h:4840"},
        "datapoints": [{"name": "a", "datatype": "float64", "local_topic": "zone1/a", "address": {"node_id": "ns=2;s=a"}}],
    }
    assert client.post("/api/connectors", json=body).status_code == 400
