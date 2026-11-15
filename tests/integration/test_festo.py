"""Read/write the exact Festo NodeIds and exercise the real OPC UA adapter."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import pytest
from asyncua import Client, ua
from festo_module import POINTS, connector, create_server, node_id


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_festo_typed_nodes_and_writes():
    async def check():
        endpoint = f"opc.tcp://127.0.0.1:{port()}"
        server, _ = await create_server(endpoint)
        async with server:
            async with Client(endpoint) as client:
                for _name, suffix, dtype in POINTS:
                    node = client.get_node(node_id(suffix))
                    assert await node.read_data_type_as_variant_type() == getattr(ua.VariantType, dtype)
                    value = True if dtype == "Boolean" else 123
                    await node.write_value(ua.Variant(value, getattr(ua.VariantType, dtype)))
                    assert await node.read_value() == value
    asyncio.run(check())


@pytest.mark.skipif(shutil.which("mosquitto") is None, reason="mosquitto not installed")
def test_festo_real_adapter(tmp_path):
    import paho.mqtt.client as mqtt
    root = Path(__file__).resolve().parents[2]
    opc_port, mqtt_port = port(), port()
    cfg = connector(f"opc.tcp://127.0.0.1:{opc_port}")
    cfg["device_key"] = cfg.pop("device_id")
    cfg["mqtt"] = {"broker_host": "127.0.0.1", "broker_port": mqtt_port}
    config_file = tmp_path / "connector.json"
    config_file.write_text(json.dumps(cfg))
    processes = []
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    got = {}
    sub.on_message = lambda c, u, m: got.setdefault(m.topic, []).append(json.loads(m.payload)["value"])
    try:
        processes.append(subprocess.Popen(["mosquitto", "-p", str(mqtt_port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        processes.append(subprocess.Popen([sys.executable, str(root / "tests/simulators/festo_module.py"),
                                          "--port", str(opc_port), "--period", "1.3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        deadline = time.monotonic() + 20
        for p in (mqtt_port, opc_port):
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", p), timeout=0.5):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        pytest.fail(f"test service did not start on {p}")
                    time.sleep(0.1)
        sub.connect("127.0.0.1", mqtt_port)
        sub.subscribe("devices/festo_trial/#")
        sub.loop_start()
        processes.append(subprocess.Popen([sys.executable, "-m", "connectors.run_adapter"],
            cwd=root / "edge_gateway", env={**os.environ, "CONFIG_PATH": str(config_file)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if all(len(set(got.get(dp["local_topic"], []))) >= 2 for dp in cfg["datapoints"]):
                break
            time.sleep(0.1)
        for dp in cfg["datapoints"]:
            values = got.get(dp["local_topic"], [])
            assert len(set(values)) >= 2, (dp["name"], values)
            assert all(type(v) is (bool if dp["datatype"] == "bool" else int) for v in values)
    finally:
        sub.disconnect()
        sub.loop_stop()
        for proc in reversed(processes):
            proc.terminate()
            proc.wait(timeout=10)
