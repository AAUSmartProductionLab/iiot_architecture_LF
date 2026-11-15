"""Read-only check of fresh study rows; no flow deployment or database mutation.

Set standard libpq PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD environment variables.
Example: python tests/evaluation/verify_contract.py --condition baseline
         --since 2026-11-12T13:00:00Z --protocol s7
FULL additionally requires --gateway-serial (the manifest serial, not gateway_id).
This checks metadata and JSON types, not physical accuracy or delivery loss.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "simulators"))
sys.path.insert(0, str(ROOT / "edge_server"))
from devices import DEVICES, uns_topic
from festo_module import connector
from orchestrator.aas.ids import device_system_id


def study_points(protocol):
    if protocol == "festo":
        cfg = connector("opc.tcp://localhost:14840")
        return "festo_trial", [(p["name"], p["datatype"], p["unit"], uns_topic("festo_trial/" + p["name"]))
                               for p in cfg["datapoints"]]
    spec = DEVICES[protocol]
    return spec["device"], [(name, dtype, unit, uns_topic(name))
                            for name, dtype, unit, _addr in spec["datapoints"]]


def valid_type(value, datatype):
    kind = datatype.lower()
    if kind in {"boolean", "bool"}:
        return type(value) is bool
    if kind in {"int32", "dint"}:
        return type(value) is int
    if kind in {"uint16", "uint32"}:
        return type(value) is int and 0 <= value < 2 ** int(kind[4:])
    return type(value) in (int, float) and math.isfinite(value)


def evaluate(rows, protocols, condition, serial=None):
    """Rows are fresh (topic, device, datapoint, unit, value), oldest first."""
    results = []
    for proto in protocols:
        device, points = study_points(proto)
        if condition == "full":
            if not serial:
                raise ValueError("FULL requires a gateway serial")
            device = device_system_id(serial, device)
        for name, dtype, unit, topic in points:
            candidates = [r for r in rows if r[0] == topic]
            valid = [r for r in candidates if r[1:4] == (device, name, unit)
                     and valid_type(r[4], dtype)]
            results.append({"topic": topic, "expected_device": device,
                            "rows": len(candidates), "valid_rows": len(valid),
                            "invalid_rows": len(candidates) - len(valid),
                            "pass": bool(candidates) and candidates[-1] in valid})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=["baseline", "full"], required=True)
    parser.add_argument("--gateway-serial")
    parser.add_argument("--protocol", choices=["festo", "opcua", "modbus", "s7"], action="append")
    parser.add_argument("--since", required=True, help="UTC trial start, ISO 8601")
    args = parser.parse_args()
    if args.condition == "full" and not args.gateway_serial:
        parser.error("--gateway-serial is required for FULL")
    try:
        since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    except ValueError:
        parser.error("--since must be an ISO 8601 timestamp")
    if since.tzinfo is None or since >= datetime.now(timezone.utc):
        parser.error("--since must include a timezone and be in the past")
    import psycopg
    protocols = args.protocol or ["festo"]
    topics = [p[3] for proto in protocols for p in study_points(proto)[1]]
    with psycopg.connect("") as conn:
        rows = conn.execute(
            "SELECT topic, device, datapoint, unit, value FROM measurements "
            "WHERE time >= %s AND time <= now() AND topic = ANY(%s) ORDER BY time",
            (since, topics),
        ).fetchall()
    results = evaluate(rows, protocols, args.condition, args.gateway_serial)
    passed = all(r["pass"] for r in results)
    print(json.dumps({"condition": args.condition, "since": since.isoformat(),
                      "pass": passed, "points": results}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
