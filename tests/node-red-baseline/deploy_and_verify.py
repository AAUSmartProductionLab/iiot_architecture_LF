"""Deploy the baseline flows to a running Node-RED and check the stored data.

    python deploy_and_verify.py              # deploy, wait 20 s, verify
    python deploy_and_verify.py --verify     # only verify (flows already deployed)

Node-RED: http://127.0.0.1:1880 (NODE_RED_URL). Database: PG_* env vars, same
defaults as generate_flows.py. The check passes when every datapoint of every
test device has rows from the last WINDOW seconds with device, datapoint and
unit filled in.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "simulators"))
from devices import DEVICES  # noqa: E402
from generate_flows import PG, all_flows  # noqa: E402

NODE_RED = os.getenv("NODE_RED_URL", "http://127.0.0.1:1880")
WINDOW = int(os.getenv("WINDOW", "20"))


def deploy() -> None:
    body = json.dumps(all_flows()).encode()  # includes the DB credentials
    req = urllib.request.Request(
        f"{NODE_RED}/flows", data=body, method="POST",
        headers={"Content-Type": "application/json", "Node-RED-Deployment-Type": "full"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        print("deployed:", r.status)


def verify() -> bool:
    dsn = (f"host={PG['host']} port={PG['port']} dbname={PG['database']} "
           f"user={PG['user']} password={PG['password']}")
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """
            SELECT device, datapoint, unit, count(*), (array_agg(value ORDER BY time DESC))[1]
            FROM measurements
            WHERE time > now() - make_interval(secs => %s)
            GROUP BY device, datapoint, unit
            """,
            (WINDOW,),
        ).fetchall()
    got = {(r[0], r[1]): r for r in rows}
    ok = True
    print(f"{'device':16s} {'datapoint':16s} {'unit':6s} {'rows':>5s}  latest")
    for proto, spec in DEVICES.items():
        for name, _dt, unit, _addr in spec["datapoints"]:
            r = got.get((spec["device"], name))
            if not r or r[2] != unit:
                ok = False
                print(f"{spec['device']:16s} {name:16s} {unit:6s}  MISSING")
            else:
                print(f"{spec['device']:16s} {name:16s} {unit:6s} {r[3]:5d}  {r[4]}")
    print("PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--verify" not in sys.argv:
        deploy()
        time.sleep(WINDOW)
    sys.exit(0 if verify() else 1)
