"""Standalone Festo CECC-LK interface simulator matching festo_opcua.py.

python tests/simulators/festo_module.py --host 0.0.0.0 --port 14840
Use --manual to preserve client control writes instead of cycling test values.
No connection to real equipment is made. NodeIds match the supplied client;
the namespace URI and process dynamics are synthetic, not a PLC digital twin.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path

from asyncua import Server, ua

BASE = "|var|CECC-LK.Application."
STOP = "FBs.stpStopper1."
# name, suffix, OPC UA type; UInt32 product type inferred from PLC udi naming.
POINTS = [
    ("conveyor_right", STOP + "convConveyor.xRight", "Boolean"),
    ("carrier_available", STOP + "stpStopper.cpfssStopper.xCarrierAvailable", "Boolean"),
    ("release_stopper", STOP + "stpStopper.cpfssStopper.xReleaseStopper", "Boolean"),
    ("read_rfid", STOP + "stpStopper.stManualControl.xReadRfid", "Boolean"),
    ("carrier_id", STOP + "stpStopper.stRfidVisu.uiCarrierID", "UInt16"),
    ("write_rfid", STOP + "stpStopper.stManualControl.xWriteRfid", "Boolean"),
    ("product_id", STOP + "stRfidData.stMesData.udiPNo", "UInt32"),
    ("job_started", "fromCDPX.stManualWorkplace.xManualJobStarted", "Boolean"),
    ("job_finished", "fromCDPX.stManualWorkplace.xManualJobFinished", "Boolean"),
]
STUDY_NAMES = {"conveyor_right", "carrier_available", "carrier_id", "product_id", "job_finished"}


def node_id(suffix):
    return "ns=2;s=" + BASE + suffix


def connector(endpoint):
    return {"device_id": "festo_trial", "protocol": "opcua", "interval": 1.0,
            "connection": {"endpoint_url": endpoint}, "datapoints": [
                {"name": name, "datatype": "bool" if dtype == "Boolean" else dtype.lower(),
                 "unit": "", "local_topic": f"devices/festo_trial/{name}",
                 "address": {"node_id": node_id(suffix)}}
                for name, suffix, dtype in POINTS if name in STUDY_NAMES]}


async def create_server(endpoint):
    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    idx = await server.register_namespace("urn:iiot-study:simulated-festo-cecc-lk")
    if idx != 2:
        raise RuntimeError(f"Expected namespace index 2, got {idx}")
    obj = await server.nodes.objects.add_object(idx, "FestoTrialModule")
    nodes = {}
    for name, suffix, dtype in POINTS:
        initial = name == "carrier_available" if dtype == "Boolean" else (101 if name == "carrier_id" else 1001)
        node = await obj.add_variable(ua.NodeId(BASE + suffix, idx), name,
                                      ua.Variant(initial, getattr(ua.VariantType, dtype)))
        await node.set_writable()
        nodes[name] = node
    return server, nodes


async def run(endpoint, manual, period):
    server, nodes = await create_server(endpoint)
    async with server:
        print(f"READY {endpoint} mode={'manual' if manual else 'automatic'}", flush=True)
        step = 0
        while True:
            if not manual:
                for name, _suffix, dtype in POINTS:
                    value = bool(step % 2) if dtype == "Boolean" else (
                        100 + step % 100 if name == "carrier_id" else 1000 + step % 100)
                    await nodes[name].write_value(ua.Variant(value, getattr(ua.VariantType, dtype)))
                step += 1
            else:
                if await nodes["release_stopper"].read_value():
                    await nodes["carrier_available"].write_value(False)
                else:
                    await nodes["carrier_available"].write_value(True)
                # RFID flags and carrier_id remain client-controlled in manual mode.
            await asyncio.sleep(period)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=14840)
    parser.add_argument("--period", type=float, default=3.0)
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--export", type=Path, help="Write connector JSON then exit; host must be reachable from gateway")
    args = parser.parse_args()
    if args.period <= 0:
        parser.error("period must be positive")
    endpoint = f"opc.tcp://{args.host}:{args.port}"
    if args.export:
        args.export.write_text(json.dumps(connector(endpoint), indent=2) + "\n", encoding="utf-8")
        return
    logging.basicConfig(level=logging.ERROR)
    try:
        asyncio.run(run(endpoint, args.manual, args.period))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
