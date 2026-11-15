"""Export a Festo reference flow; use for readiness/reuse trials, not hand-build timing."""
import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulators"))
from festo_module import POINTS, STUDY_NAMES, node_id
import generate_flows as gen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gen.DEVICES = copy.deepcopy(gen.DEVICES)
    gen.DEVICES["opcua"] = {"device": "festo_trial", "endpoint": args.endpoint,
        "datapoints": [(n, dt, "", node_id(s)) for n, s, dt in POINTS if n in STUDY_NAMES]}
    for proto in ("modbus", "s7", "mqtt"):
        gen.DEVICES[proto]["datapoints"] = []
    gen.INTERVAL_MS = 1000
    gen.UNS_DEVICES = gen.UNS_PREFIX + "/devices/festo_trial/"
    nodes = gen.opcua_tab().json() + gen.server_tab().json()
    nodes = [n for n in nodes if n.get("topic") != "meter1/#"]
    for n in nodes:
        n.pop("credentials", None)
    args.output.write_text(json.dumps(nodes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
