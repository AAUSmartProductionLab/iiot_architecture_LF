"""Run the real protocol adapters against the test-device simulators.

For OPC UA, Modbus TCP and S7: start the simulators and a mosquitto broker,
launch `python -m connectors.run_adapter` with a connector built from
tests/simulators/devices.py, and check that every datapoint is published on its
local topic with a decoded value at the configured interval.

Needs `mosquitto` on PATH (skipped otherwise). S7 needs port 102 (root or
CAP_NET_BIND_SERVICE; skipped otherwise). The simulators need pymodbus < 3.10;
point SIM_PYTHON at an interpreter that has it if the test env has a newer one.

    python -m pytest tests/integration -v
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "simulators"))
from devices import DEVICES  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("mosquitto") is None, reason="mosquitto not installed")

INTERVAL = 0.5
RUN_S = 6


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def can_bind_102() -> bool:
    try:
        with socket.socket() as s:
            # Like the snap7 server: a port in TIME_WAIT from a previous run is fine.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 102))
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def env():
    mqtt_port = free_port()
    broker = subprocess.Popen(["mosquitto", "-p", str(mqtt_port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    protos = ["opcua", "modbus"] + (["s7"] if can_bind_102() else [])
    sims = subprocess.Popen(
        [os.getenv("SIM_PYTHON", sys.executable), "run_simulators.py", *protos],
        cwd=ROOT / "tests" / "simulators",
        env={**os.environ, "MQTT_PORT": str(mqtt_port)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(4)
    yield {"mqtt_port": mqtt_port, "protos": protos}
    sims.terminate()
    broker.terminate()


def connector_for(proto: str) -> dict:
    spec = DEVICES[proto]
    if proto == "opcua":
        connection = {"endpoint_url": spec["endpoint"]}
        dps = [
            {"name": n, "datatype": dt.lower(), "unit": u, "local_topic": f"devices/{n}", "address": {"node_id": nid}}
            for n, dt, u, nid in spec["datapoints"]
        ]
        protocol = "opcua"
    elif proto == "modbus":
        connection = {"host": spec["host"], "port": spec["port"], "unit_id": spec["unit_id"]}
        dps = [
            {"name": n, "datatype": dt, "unit": u, "local_topic": f"devices/{n}", "address": {"register": reg}}
            for n, dt, u, reg in spec["datapoints"]
        ]
        protocol = "modbus-tcp"
    else:
        connection = {"host": spec["host"], "rack": spec["rack"], "slot": spec["slot"]}
        dps = [
            {"name": n, "datatype": dt.lower(), "unit": u, "local_topic": f"devices/{n}",
             "address": {"area": "DB", "db_number": spec["db"], "start": start}}
            for n, dt, u, start in spec["datapoints"]
        ]
        protocol = "s7"
    return {"device_key": spec["device"], "protocol": protocol, "connection": connection,
            "interval": INTERVAL, "datapoints": dps}


@pytest.mark.parametrize("proto", ["opcua", "modbus", "s7"])
def test_adapter_publishes_every_datapoint(env, proto, tmp_path):
    if proto not in env["protos"]:
        pytest.skip("S7 simulator needs port 102")
    import paho.mqtt.client as mqtt

    cfg = connector_for(proto)
    cfg["mqtt"] = {"broker_host": "127.0.0.1", "broker_port": env["mqtt_port"]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))

    got: dict[str, list] = {}
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sub.on_message = lambda c, u, m: got.setdefault(m.topic, []).append((time.time(), json.loads(m.payload)))
    sub.connect("127.0.0.1", env["mqtt_port"])
    sub.subscribe("devices/#")
    sub.loop_start()
    adapter = subprocess.Popen(
        [sys.executable, "-m", "connectors.run_adapter"], cwd=ROOT / "edge_gateway",
        env={**os.environ, "CONFIG_PATH": str(path)}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(RUN_S)
    adapter.terminate()
    log = adapter.communicate()[0]
    sub.loop_stop()

    assert "CONNECTED" in log and "CONNECT_FAILED" not in log, log[-2000:]
    for dp in cfg["datapoints"]:
        samples = got.get(dp["local_topic"], [])
        assert len(samples) >= 3, f"{dp['name']}: {len(samples)} samples\n{log[-1500:]}"
        values = [p["value"] for _t, p in samples]
        assert all(isinstance(v, (int, float, bool)) for v in values), values
        gaps = [b[0] - a[0] for a, b in zip(samples, samples[1:])]
        assert max(gaps) < INTERVAL * 3, f"{dp['name']}: polling gaps {gaps}"


def test_modbus_unreachable_is_reported(env, tmp_path):
    cfg = connector_for("modbus")
    cfg["connection"]["port"] = free_port()  # nothing listens there
    cfg["mqtt"] = {"broker_host": "127.0.0.1", "broker_port": env["mqtt_port"]}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    adapter = subprocess.Popen(
        [sys.executable, "-m", "connectors.run_adapter"], cwd=ROOT / "edge_gateway",
        env={**os.environ, "CONFIG_PATH": str(tmp_path / "config.json")},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    # A refused TCP connection can take several seconds on Windows, including
    # the Modbus client's retries. Allow the failure to reach the connector log.
    time.sleep(15)
    adapter.terminate()
    log = adapter.communicate()[0]
    assert "CONNECT_FAILED" in log and "INFO:connector:CONNECTED" not in log
