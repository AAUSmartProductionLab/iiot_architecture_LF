"""Run all test-device simulators in one process.

    python tests/simulators/run_simulators.py            # all protocols
    python tests/simulators/run_simulators.py opcua s7   # a subset

* OPC UA server on :4840 (asyncua), namespace 2, nodes ns=2;s=Station1.<Name>
* Modbus TCP server on :5020 (pymodbus 3.6-3.9), float32 holding registers
* S7 server on :102 (python-snap7 3.0; port 102 needs root or CAP_NET_BIND_SERVICE)
* MQTT power meter publishing bare JSON numbers to meter1/... on MQTT_HOST:1883

Every value changes on each tick (0.5 s), so report-by-exception publishers
publish on every poll and data gaps are visible. Devices are defined in
devices.py.
"""

import asyncio
import logging
import math
import struct
import sys
import threading
import time

from devices import DEVICES, MQTT_HOST, MQTT_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("sims")
TICK = 0.5
T0 = time.time()


def wave(i: int, base: float, amp: float = 0.1) -> float:
    """A slowly varying value per datapoint index."""
    t = time.time() - T0
    return base * (1 + amp * math.sin(t / 5 + i))


# --- OPC UA -----------------------------------------------------------------
async def opcua_server():
    from asyncua import Server, ua

    spec = DEVICES["opcua"]
    srv = Server()
    await srv.init()
    srv.set_endpoint(f"opc.tcp://0.0.0.0:{spec['port']}/")
    idx = await srv.register_namespace("urn:iiot-test:festo")
    assert idx == 2, f"expected namespace index 2, got {idx}"
    obj = await srv.nodes.objects.add_object(idx, "Station1")
    initial = {"Double": 0.0, "Int32": 0, "Boolean": False}
    variant = {"Double": ua.VariantType.Double, "Int32": ua.VariantType.Int32, "Boolean": ua.VariantType.Boolean}
    nodes = []
    for name, dtype, _unit, node_id in spec["datapoints"]:
        ident = node_id.split(";s=", 1)[1]
        var = await obj.add_variable(ua.NodeId(ident, idx), ident.split(".")[-1], initial[dtype], variant[dtype])
        nodes.append((var, dtype))
    async with srv:
        log.info("OPC UA server on %s", spec["endpoint"])
        n = 0
        while True:
            for i, (var, dtype) in enumerate(nodes):
                if dtype == "Double":
                    v = ua.Variant(wave(i, 20.0 + 10 * i), ua.VariantType.Double)
                elif dtype == "Int32":
                    v = ua.Variant(n, ua.VariantType.Int32)
                else:
                    v = ua.Variant(n % 4 < 2, ua.VariantType.Boolean)  # toggles every second
                await var.write_value(v)
            n += 1
            await asyncio.sleep(TICK)


# --- Modbus TCP -------------------------------------------------------------
async def modbus_server():
    from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
    from pymodbus.server import StartAsyncTcpServer

    try:  # pymodbus <= 3.9
        from pymodbus.datastore import ModbusSlaveContext as Device

        ctx_kw = "slaves"
    except ImportError:  # pymodbus 3.10+
        from pymodbus.datastore import ModbusDeviceContext as Device

        ctx_kw = "devices"
    spec = DEVICES["modbus"]
    ctx = ModbusServerContext(**{ctx_kw: Device(hr=ModbusSequentialDataBlock(1, [0] * 64))}, single=True)
    bases = [12.0, 230.0, 4.0, 1000.0, 50.0]

    async def update():
        while True:
            for i, (_name, _dt, _unit, register) in enumerate(spec["datapoints"]):
                regs = list(struct.unpack(">HH", struct.pack(">f", wave(i, bases[i % len(bases)], 0.05))))
                ctx[0].setValues(3, register, regs)  # fc 3 = holding registers
            await asyncio.sleep(TICK)

    asyncio.create_task(update())
    log.info("Modbus TCP server on :%d", spec["port"])
    await StartAsyncTcpServer(context=ctx, address=("0.0.0.0", spec["port"]))


# --- S7 ---------------------------------------------------------------------
def s7_server():
    from snap7.server import Server
    from snap7.type import SrvArea

    spec = DEVICES["s7"]
    db = bytearray(64)  # must be a bytearray: the server serves it in place
    srv = Server()
    srv.register_area(SrvArea.DB, spec["db"], db)
    srv.start(tcp_port=spec["port"])
    log.info("S7 server on :%d (DB%d)", spec["port"], spec["db"])
    n = 0
    while True:
        for i, (_name, dtype, _unit, start) in enumerate(spec["datapoints"]):
            if dtype == "REAL":
                struct.pack_into(">f", db, start, wave(i, 10.0 * (i + 1)))
            elif dtype == "DINT":
                struct.pack_into(">i", db, start, n)
        n += 1
        time.sleep(TICK)


# --- MQTT-native power meter -----------------------------------------------
def mqtt_meter():
    import json

    import paho.mqtt.client as mqtt

    spec = DEVICES["mqtt"]
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sim-power-meter")
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()
    log.info("MQTT power meter publishing to %s:%d", MQTT_HOST, MQTT_PORT)
    bases = [16.0, 15.0, 17.0, 11.0, 0.93]
    while True:
        for i, (_name, _dt, _unit, topic) in enumerate(spec["datapoints"]):
            client.publish(topic, json.dumps(round(wave(i, bases[i], 0.03), 3)))
        time.sleep(TICK)


def main(selected: list[str]) -> None:
    threads = []
    if "s7" in selected:
        threads.append(threading.Thread(target=s7_server, daemon=True))
    if "mqtt" in selected:
        threads.append(threading.Thread(target=mqtt_meter, daemon=True))
    for t in threads:
        t.start()

    async def run_async():
        tasks = []
        if "opcua" in selected:
            tasks.append(opcua_server())
        if "modbus" in selected:
            tasks.append(modbus_server())
        if tasks:
            await asyncio.gather(*tasks)
        else:
            while True:
                await asyncio.sleep(3600)

    asyncio.run(run_async())


if __name__ == "__main__":
    main(sys.argv[1:] or list(DEVICES))
