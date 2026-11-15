"""Run and time the ablation study: onboard the Festo module's five signals.

Each level removes one more framework feature; L4 is plain Node-RED.

  L0  Full framework        auto-discovery, OPC UA tag browsing, automatic mapping
  L1  No auto-discovery     register the gateway by IP
  L2  No tag browsing       type NodeIds from the device sheet
  L3  No automatic mapping  write the topic_map rows by hand
  L4  Node-RED baseline     build the whole flow by hand

  python tests/ablation/study.py check          # environment health
  python tests/ablation/study.py trial L2       # reset, show the task card, time the operator
  python tests/ablation/study.py pilot L2       # reset, then do the task via the API (machine baseline)
  python tests/ablation/study.py prepare L0     # reset only; L0 is normal operation
  python tests/ablation/study.py report         # results/trials.csv and results/summary.md
  python tests/ablation/study.py cards          # filled-in task cards: materials/task_cards.md

A trial ends automatically once all five signals are stored with the expected
device, datapoint, unit and JSON type. Settings: tests/ablation/config.json.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import queue
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import psycopg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "tests" / "simulators"), str(ROOT / "tests" / "evaluation"), str(ROOT / "edge_server")]
from festo_module import POINTS, STUDY_NAMES, connector, node_id  # noqa: E402
from orchestrator.aas.ids import device_system_id  # noqa: E402
from verify_contract import valid_type  # noqa: E402

RESULTS = HERE / "results"
STATE_FILE = RESULTS / "state.json"
TASKS_FILE = HERE / "materials" / "tasks.md"

# auto_mapping: the ingestor maps topics from the device AIDs (off: topic_map by hand).
LEVELS = {
    "L0": {"name": "Full framework", "framework": True, "discovery": True, "browse": True, "auto_mapping": True},
    "L1": {"name": "No auto-discovery", "framework": True, "discovery": False, "browse": True, "auto_mapping": True},
    "L2": {"name": "No tag browsing", "framework": True, "discovery": False, "browse": False, "auto_mapping": True},
    "L3": {"name": "No automatic mapping", "framework": True, "discovery": False, "browse": False,
           "auto_mapping": False},
    "L4": {"name": "Node-RED baseline", "framework": False},
}
# (datapoint name, datatype) in device order.
STUDY = [(n, "bool" if t == "Boolean" else t.lower()) for n, _s, t in POINTS if n in STUDY_NAMES]

ORCH_PATTERN = r"uvicorn.*orchestrator\.main:app"
NODERED_PATTERN = r"node-red.red\.js"
ACCESS_LOG = re.compile(r'"(GET|POST|PUT|PATCH|DELETE) (\S+) HTTP/[\d.]+" (\d{3})')


# --- small helpers ----------------------------------------------------------

def load_config() -> SimpleNamespace:
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    cfg["server_dir"] = str(Path(os.path.expanduser(cfg["server_dir"])))
    return SimpleNamespace(**cfg)


def log(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="milliseconds") if dt else None


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sh(args, cwd=None, env=None, check=True, timeout=300) -> subprocess.CompletedProcess:
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, args))} failed ({p.returncode}): {(p.stderr or p.stdout).strip()}")
    return p


def ssh(cfg, command: str, timeout=180) -> subprocess.CompletedProcess:
    return sh(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", cfg.gateway_ssh, command], timeout=timeout)


def wait_until(what: str, fn, timeout=60.0, interval=1.0):
    deadline, last = time.time() + timeout, None
    while time.time() < deadline:
        try:
            result = fn()
            if result:
                return result
        except Exception as exc:  # keep polling until the deadline
            last = exc
        time.sleep(interval)
    raise RuntimeError(f"timed out waiting for {what}" + (f": {last}" if last else ""))


def get_json(url: str, timeout=10.0):
    r = httpx.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def post_json(url: str, body: dict, timeout=60.0):
    r = httpx.post(url, json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"POST {url} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def find_processes(pattern: str, name: str) -> list[int]:
    """PIDs of processes called `name` (e.g. python.exe) whose command line matches the regex."""
    if os.name == "nt":
        script = (f"Get-CimInstance Win32_Process -Filter \"Name = '{name}'\" | "
                  f"Where-Object {{ $_.CommandLine -match '{pattern}' }} | ForEach-Object {{ $_.ProcessId }}")
        out = sh(["powershell", "-NoProfile", "-Command", script], check=False).stdout.split()
    else:
        out = sh(["pgrep", "-f", pattern], check=False).stdout.split()
    return [int(pid) for pid in out if pid.isdigit()]


def kill_matching(pattern: str, name: str) -> list[int]:
    pids = [pid for pid in find_processes(pattern, name) if pid not in (os.getpid(), os.getppid())]
    for pid in pids:
        if os.name == "nt":
            sh(["taskkill", "/F", "/T", "/PID", str(pid)], check=False)
        else:
            sh(["kill", str(pid)], check=False)
    return pids


def other_study_runs() -> list[int]:
    """Other trial/pilot runs of this script (the reset would invalidate them)."""
    return [pid for pid in find_processes(r"study\.py\s+(trial|pilot)", "python.exe" if os.name == "nt" else "")
            if pid not in (os.getpid(), os.getppid())]


def start_detached(args, cwd, env, log_path: Path) -> None:
    """Start a process that outlives this script, logging to log_path."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008}  # DETACHED_PROCESS
              if os.name == "nt" else {"start_new_session": True})
    with open(log_path, "ab") as logf:
        subprocess.Popen(args, cwd=cwd, env=env, stdout=logf, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, **kwargs)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_state(state: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def orch_api(cfg) -> str:
    return f"http://localhost:{cfg.orchestrator_port}/api"


def gateway_url(cfg) -> str:
    return f"http://{cfg.gateway_ip}:{cfg.gateway_port}"


def nodered_url(cfg) -> str:
    return f"http://127.0.0.1:{cfg.node_red_port}"


def nodered_dir(cfg) -> Path:
    return ROOT / cfg.node_red_dir


def expected_device(cfg, level: str, serial: str) -> str:
    """The device identity when the task card's device id is used (examples in the cards)."""
    return cfg.device_id if level == "L4" else device_system_id(serial, cfg.device_id)


def device_rule(level: str, serial: str):
    """(description, predicate) for a device identity that counts. L0-L3 accept any device
    on this gateway, including an automatically named one; L4 any non-empty name."""
    if level == "L4":
        return "any non-empty device name", lambda d: bool(d and d.strip())
    prefix = f"{serial}_"
    return f"{prefix}<device id>", lambda d: bool(d) and d.startswith(prefix)


def file_size(path) -> int:
    try:
        return Path(path).stat().st_size
    except (TypeError, OSError):
        return 0


def read_from(path, offset: int) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace")
    except (TypeError, OSError):
        return ""


# --- environment reset ------------------------------------------------------

def reset_gateway(cfg) -> dict:
    """Remove all connectors and the bridge setting; restart the gateway services."""
    base = gateway_url(cfg)
    for c in get_json(base + "/api/manifest").get("configured_connectors", []):
        httpx.delete(f"{base}/api/connectors/{c.get('device_key') or c.get('device_id')}", timeout=60)
    ssh(cfg, "docker ps -aq --filter label=iiot.role=adapter | xargs -r docker rm -f >/dev/null; "
             "docker exec gateway-agent rm -f /data/bridge_state.json /app/broker/config/conf.d/bridge.conf && "
             "docker restart gateway-agent mqtt-broker >/dev/null")
    manifest = wait_until("gateway agent", lambda: get_json(base + "/api/manifest", 3), 120, 2)
    if manifest["configured_connectors"] or manifest["bridge"]["configured"]:
        raise RuntimeError("gateway still has connectors or a bridge after the reset")
    return manifest


def study_filter(cfg, serial: str):
    """Rows from earlier trials: the task's device, any device of this gateway, the task topics."""
    names = [n for n, _ in STUDY]
    topics = ([f"{cfg.uns_prefix}/devices/{cfg.device_id}/{n}" for n in names]
              + [f"{cfg.uns_prefix}/devices/{n}" for n in names])
    return ("device = %s OR device LIKE %s OR topic = ANY(%s)",
            (cfg.device_id, serial.replace("_", "\\_") + "\\_%", topics))


def write_rows_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "topic", "device", "datapoint", "value", "unit"])
        for t, topic, device, dp, value, unit in rows:
            w.writerow([t.isoformat(), topic, device, dp, json.dumps(value), unit])


def archive_study_rows(cfg, serial: str, dest: Path) -> int:
    """Move earlier Festo rows to a CSV (stale values would show in the dashboard)."""
    where, params = study_filter(cfg, serial)
    with psycopg.connect(cfg.pg_dsn, autocommit=True) as conn:
        rows = conn.execute("SELECT time, topic, device, datapoint, value, unit FROM measurements "
                            f"WHERE {where} ORDER BY time", params).fetchall()
        if rows:
            write_rows_csv(dest, rows)
            conn.execute(f"DELETE FROM measurements WHERE {where}", params)
        conn.execute("TRUNCATE topic_map")
    return len(rows)


def restart_basyx(cfg) -> None:
    sh(["docker", "restart", "aas-environment"])
    wait_until("BaSyx", lambda: httpx.get(cfg.basyx_url + "/shells", timeout=3).status_code == 200, 180, 2)


def set_ingestor(cfg, level: str) -> None:
    """Run the ingestor with AID-driven mapping on (L0-L2) or off (L3); stop it for L4."""
    spec = LEVELS[level]
    if not spec["framework"]:
        sh(["docker", "stop", "timescale-ingestor"], check=False)
        return
    flag = "true" if spec["auto_mapping"] else "false"
    sh(["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "timescale-ingestor"],
       cwd=cfg.server_dir, env=dict(os.environ, AUTO_MAPPING_ENABLED=flag))
    env = sh(["docker", "inspect", "timescale-ingestor", "--format", "{{range .Config.Env}}{{println .}}{{end}}"]).stdout
    if f"AUTO_MAPPING_ENABLED={flag}" not in env:
        raise RuntimeError("ingestor did not pick up AUTO_MAPPING_ENABLED")


def start_orchestrator(cfg, level: str, log_path: Path) -> None:
    py = Path(cfg.server_dir) / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = dict(os.environ,
               DISCOVERY_ENABLED="true" if LEVELS[level]["discovery"] else "false",
               SERVER_IP=cfg.server_ip,
               PUBLIC_API_BASE_URL=f"http://{cfg.server_ip}:{cfg.orchestrator_port}",
               PUBLIC_MQTT_URL=f"mqtt://{cfg.server_ip}:1883",
               BASYX_URL=cfg.basyx_url, TS_DSN=cfg.pg_dsn, PYTHONUNBUFFERED="1")
    start_detached([str(py), "-u", "-m", "uvicorn", "orchestrator.main:app", "--host", "0.0.0.0",
                    "--port", str(cfg.orchestrator_port)], cfg.server_dir, env, log_path)
    wait_until("orchestrator", lambda: get_json(orch_api(cfg) + "/health", 2), 60)


def find_gateway(cfg) -> str | None:
    for g in get_json(orch_api(cfg) + "/gateways", 3):
        if g.get("ip") == cfg.gateway_ip and g.get("online"):
            return g["gateway_id"]
    return None


def start_nodered(cfg, log_path: Path, backup: Path) -> None:
    """Start Node-RED with an empty workspace (earlier flows are moved to backup)."""
    d = nodered_dir(cfg)
    for name in ("flows.json", "flows_cred.json", ".flows.json.backup", ".flows_cred.json.backup"):
        if (d / name).exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d / name), str(backup / name))
    start_detached(["node", str(d / "node_modules" / "node-red" / "red.js"), "--userDir", str(d),
                    "--port", str(cfg.node_red_port)], str(d), dict(os.environ), log_path)
    wait_until("Node-RED", lambda: httpx.get(nodered_url(cfg), timeout=2).status_code == 200, 120)


def prepare(cfg, level: str, force=False) -> dict:
    spec, ts = LEVELS[level], stamp()
    others = other_study_runs()
    if others and not force:
        raise SystemExit(f"Another trial or pilot is running (PID {', '.join(map(str, others))}). "
                         "Finish it first (type q in its terminal), or pass --force.")
    log(f"Preparing {level}: {spec['name']}")
    log("Stopping the orchestrator and Node-RED")
    kill_matching(ORCH_PATTERN, "python.exe")
    kill_matching(NODERED_PATTERN, "node.exe")
    log("Resetting the gateway (connectors, bridge)")
    manifest = reset_gateway(cfg)
    serial = manifest["serial_number"]
    log("Archiving earlier Festo rows and clearing topic_map")
    archived = archive_study_rows(cfg, serial, RESULTS / "archive" / f"{ts}.csv")
    log("Restarting BaSyx (clears every AAS)")
    restart_basyx(cfg)
    log("Ingestor: " + ("stopped" if not spec["framework"] else
                        f"automatic mapping {'on' if spec['auto_mapping'] else 'off'}"))
    set_ingestor(cfg, level)
    state = {"level": level, "prepared_at": iso(utcnow()), "serial": serial,
             "gateway_id": manifest["gateway_id"], "archived_rows": archived}
    if spec["framework"]:
        state["orchestrator_log"] = str(RESULTS / "logs" / f"orchestrator_{ts}.log")
        log(f"Starting the orchestrator (discovery {'on' if spec['discovery'] else 'off'})")
        start_orchestrator(cfg, level, Path(state["orchestrator_log"]))
        if spec["discovery"]:
            wait_until("gateway discovery", lambda: find_gateway(cfg), 60)
            wait_until("gateway AAS", lambda: get_json(cfg.basyx_url + "/shells", 3).get("result"), 60)
            log("Gateway discovered and registered")
    else:
        state["nodered_log"] = str(RESULTS / "logs" / f"nodered_{ts}.log")
        log("Starting Node-RED with an empty workspace")
        start_nodered(cfg, Path(state["nodered_log"]), RESULTS / "nodered_backup" / ts)
    save_state(state)
    log(f"{level} is ready")
    return state


# --- measuring --------------------------------------------------------------

def snapshot(cfg, since: datetime):
    with psycopg.connect(cfg.pg_dsn) as conn:
        return conn.execute(
            "SELECT topic, device, datapoint, unit, count(*), min(time), max(time), "
            "(array_agg(value ORDER BY time DESC))[1] FROM measurements WHERE time >= %s "
            "GROUP BY 1, 2, 3, 4", (since,)).fetchall()


def device_points(groups, device) -> dict:
    """Per study point: rows stored under `device`, and whether the latest is valid."""
    points = {}
    for name, dtype in STUDY:
        mine = [g for g in groups if g[2] == name and g[1] == device]
        latest = max(mine, key=lambda g: g[6]) if mine else None
        ok = bool(latest) and (latest[3] or "") == "" and valid_type(latest[7], dtype)
        points[name] = {"ok": ok, "rows": sum(g[4] for g in mine),
                        "topic": latest[0] if latest else None,
                        "unit": latest[3] if latest else None,
                        "latest_value": latest[7] if latest else None,
                        "first_row": iso(min(g[5] for g in mine)) if mine else None}
    return points


def evaluate(groups, accept):
    """Best acceptable device (most valid points); all five must be under that one device."""
    scored = []
    for device in sorted({g[1] for g in groups if g[1] and accept(g[1])}):
        points = device_points(groups, device)
        scored.append((sum(p["ok"] for p in points.values()), sum(p["rows"] for p in points.values()),
                       device, points))
    _ok, _rows, device, points = max(scored, default=(0, 0, None, device_points(groups, None)))
    total = sum(g[4] for g in groups)
    unmapped = sum(g[4] for g in groups if g[1] is None)
    return points, total, unmapped, device


def api_activity(text: str) -> dict:
    counts = Counter()
    for method, path, code in ACCESS_LOG.findall(text):
        if method != "GET":
            if path.endswith("/gateways/register"):
                kind = "register"
            elif path.endswith("/configure"):
                kind = "configure_bridge"
            elif path.endswith("/opcua/browse"):
                kind = "browse"
            elif path.endswith("/provision"):
                kind = "provision"
            elif method == "DELETE":
                kind = "deprovision"
            else:
                kind = "other_write"
            counts[kind] += 1
            counts["writes"] += 1
        if int(code) >= 400:
            counts["errors"] += 1
    return dict(counts)


def nodered_activity(text: str) -> dict:
    return {"deploys": len(re.findall(r"Started (?:modified )?(?:flows|nodes)", text)),
            "errors": text.count("[error]"), "warnings": text.count("[warn]")}


def flow_stats(flows: list) -> dict:
    tabs = [n for n in flows if n.get("type") == "tab"]
    nodes = [n for n in flows if n.get("type") != "tab" and "z" in n]
    config = [n for n in flows if n.get("type") != "tab" and "z" not in n]
    functions = [n for n in nodes if n.get("type") == "function"]
    return {"tabs": len(tabs), "nodes": len(nodes), "config_nodes": len(config),
            "function_nodes": len(functions),
            "function_lines": sum(len([l for l in (n.get("func") or "").splitlines() if l.strip()])
                                  for n in functions),
            "node_types": dict(Counter(n["type"] for n in nodes))}


def container_started_after(name: str, t0: datetime) -> bool:
    out = sh(["docker", "inspect", name, "--format", "{{.State.StartedAt}}"], check=False).stdout.strip()
    try:
        started = datetime.fromisoformat(re.sub(r"(\.\d{6})\d*", r"\1", out.replace("Z", "+00:00")))
    except ValueError:
        return False
    return started > t0


def task_parts(cfg, level: str, serial: str) -> tuple[str, str]:
    """(Common section, level section) of materials/tasks.md with this lab's values."""
    text = TASKS_FILE.read_text(encoding="utf-8")
    common = re.search(r"^## Common\n(.*?)(?=^## )", text, re.S | re.M)
    section = re.search(rf"^## {level}\b.*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    values = {"gateway_ip": cfg.gateway_ip, "endpoint": cfg.opcua_endpoint, "server_ip": cfg.server_ip,
              "device_id": cfg.device_id, "uns_prefix": cfg.uns_prefix, "dashboard": cfg.dashboard_url,
              "expected_device": expected_device(cfg, level, serial), "serial": serial,
              "node_red": f"http://localhost:{cfg.node_red_port}"}

    def fill(match) -> str:
        body = match.group(1).strip() if match else ""
        for key, value in values.items():
            body = body.replace("{" + key + "}", str(value))
        return body
    return fill(common), fill(section)


def show_task(cfg, level: str, state: dict) -> None:
    common, section = task_parts(cfg, level, state["serial"])
    print("\n" + "=" * 78 + f"\nTASK {level}: {LEVELS[level]['name']}\n" + "=" * 78)
    print(common + "\n\n" + section + "\n" + "=" * 78)


def write_cards(cfg) -> Path:
    """All task cards, filled in, in one file to keep open during the trials."""
    serial = load_state().get("serial") or get_json(gateway_url(cfg) + "/api/manifest")["serial_number"]
    common, _ = task_parts(cfg, "L0", serial)
    parts = ["# Task cards (filled in for this lab)", "",
             "Generated by `study.py cards` from `tasks.md` and `config.json`; the runner prints the same "
             "card when a trial starts. Device documentation: [device_sheet.md](device_sheet.md).", "",
             "## Every level", "", common, "",
             f"In L4 there is no gateway prefix: the device is `{cfg.device_id}`."]
    for level, spec in LEVELS.items():
        parts += ["", f"## {level} {spec['name']}", "", task_parts(cfg, level, serial)[1]]
    out = HERE / "materials" / "task_cards.md"
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return out


def run_trial(cfg, level: str, operator: str, pilot_fn=None) -> dict:
    state = load_state()
    if state.get("level") != level:
        raise SystemExit(f"Environment is prepared for {state.get('level')}, not {level}. Run 'prepare {level}'.")
    rule, accept = device_rule(level, state["serial"])
    device = None
    trial_id = f"{stamp()}_{level}_{operator}"
    tdir = RESULTS / "trials" / trial_id
    commands: queue.Queue = queue.Queue()

    if pilot_fn is None:
        show_task(cfg, level, state)
        print(f"\nTrial ID: {trial_id}")
        answer = input("Start the screen recording, then press Enter to START the clock (q = cancel): ")
        if answer.strip().lower() == "q":
            raise SystemExit("cancelled")

        def reader():
            for line in sys.stdin:
                commands.put(line.strip())
        threading.Thread(target=reader, daemon=True).start()

    t0 = utcnow()
    orch_offset = file_size(state.get("orchestrator_log"))
    nr_offset = file_size(state.get("nodered_log"))
    print(f"\nCLOCK STARTED {t0:%H:%M:%S} UTC  |  trial {trial_id}")
    if pilot_fn is None:
        print("Commands: 'm <text>' milestone, 'n <text>' note, 's' status, 'q' give up.\n")

    pilot_error: list = []
    if pilot_fn is not None:
        def run_pilot():
            try:
                pilot_fn(cfg, level, state)
            except Exception as exc:
                pilot_error.append(repr(exc))
        threading.Thread(target=run_pilot, daemon=True).start()

    events, status, first_data, success = [], "running", None, None
    last_ok, last_beat, points, total, unmapped = -1, time.time(), {}, 0, 0
    deadline = time.time() + 60 * cfg.timeout_minutes

    def elapsed(at=None):
        s = ((at or utcnow()) - t0).total_seconds()
        return f"{int(s // 60):02d}:{s % 60:04.1f}"

    try:
        while status == "running":
            groups = snapshot(cfg, t0)
            points, total, unmapped, device = evaluate(groups, accept)
            now = utcnow()
            if total and first_data is None:
                first_data = now
                print(f"[{elapsed(now)}] first row stored")
            n_ok = sum(p["ok"] for p in points.values())
            if n_ok != last_ok:
                print(f"[{elapsed(now)}] valid points {n_ok}/{len(STUDY)}")
                last_ok = n_ok
            if n_ok == len(STUDY):
                success, status = now, "success"
                break
            while not commands.empty():
                cmd = commands.get()
                if cmd.lower() in ("q", "quit"):
                    status = "aborted"
                elif cmd.lower() == "s":
                    print(f"   device: {device or '-'} (counts: {rule})")
                    for name, p in points.items():
                        line = f"   {name:18s} {'OK ' if p['ok'] else '-- '} rows={p['rows']}"
                        others = sorted({g[1] for g in groups if g[2] == name and g[1] and g[1] != device})
                        if not p["rows"] and others:
                            line += f"  stored under device {', '.join(others)} instead"
                        print(line)
                    print(f"   rows since start: {total} (without metadata: {unmapped})")
                elif cmd[:2].lower() in ("m ", "n "):
                    kind = "milestone" if cmd[0].lower() == "m" else "note"
                    events.append({"type": kind, "text": cmd[2:].strip(), "at": iso(now),
                                   "elapsed_s": round((now - t0).total_seconds(), 1)})
                    print(f"[{elapsed(now)}] {kind} recorded: {cmd[2:].strip()}")
                elif cmd:
                    print("   commands: m <text> | n <text> | s | q")
            if pilot_error:
                status = "pilot_failed"
            elif time.time() > deadline:
                status = "timeout"
            elif time.time() - last_beat >= 60:
                print(f"[{elapsed()}] still running, valid points {n_ok}/{len(STUDY)}")
                last_beat = time.time()
            if status == "running":
                time.sleep(1)
    except KeyboardInterrupt:
        status = "aborted"

    t_end = success or utcnow()
    print("\a", end="")
    record = {
        "trial_id": trial_id, "level": level, "level_name": LEVELS[level]["name"],
        "features": {k: v for k, v in LEVELS[level].items() if k != "name"},
        "operator": operator, "status": status, "started_at": iso(t0), "ended_at": iso(t_end),
        "duration_s": round((t_end - t0).total_seconds(), 1),
        "time_to_first_data_s": round((first_data - t0).total_seconds(), 1) if first_data else None,
        "time_to_valid_data_s": round((success - t0).total_seconds(), 1) if success else None,
        "device": device, "device_rule": rule, "events": events, "points": points,
        "rows_total": total, "rows_without_metadata": unmapped, "pilot_error": pilot_error or None,
    }
    tdir.mkdir(parents=True, exist_ok=True)

    def save():
        (tdir / "trial.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    save()  # the timing is kept even if collecting the evidence fails or is interrupted
    print("Saving the evidence...", flush=True)
    try:
        collect_evidence(cfg, level, state, t0, tdir, record, orch_offset, nr_offset)
    except BaseException as exc:  # includes Ctrl+C while saving
        record["evidence_error"] = repr(exc)
    save()
    print_summary(record, tdir)
    return record


def collect_evidence(cfg, level, state, t0, tdir: Path, record: dict, orch_offset: int, nr_offset: int) -> None:
    """Save what was configured and the raw rows; count API/Node-RED activity."""
    try:
        with psycopg.connect(cfg.pg_dsn) as conn:
            write_rows_csv(tdir / "rows.csv", conn.execute(
                "SELECT time, topic, device, datapoint, value, unit FROM measurements "
                "WHERE time >= %s ORDER BY time", (t0,)).fetchall())
            topic_map = conn.execute("SELECT topic, device, datapoint, datatype, unit FROM topic_map").fetchall()
        (tdir / "topic_map.json").write_text(json.dumps([list(r) for r in topic_map], indent=2), encoding="utf-8")
        record["topic_map_rows"] = len(topic_map)
    except Exception as exc:
        record["evidence_error_db"] = repr(exc)
    try:
        manifest = get_json(gateway_url(cfg) + "/api/manifest")
        (tdir / "gateway_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        record["gateway_connectors"] = [
            {"device_key": c.get("device_key"), "interval_s": c.get("interval"),
             "datapoints": [d.get("name") for d in c.get("datapoints", [])]}
            for c in manifest.get("configured_connectors", [])]
        record["bridge_configured"] = manifest.get("bridge", {}).get("configured")
    except Exception as exc:
        record["evidence_error_gateway"] = repr(exc)
    try:
        if LEVELS[level]["framework"]:
            text = read_from(state.get("orchestrator_log"), orch_offset)
            (tdir / "orchestrator.log").write_text(text, encoding="utf-8")
            record["api"] = api_activity(text)
            if not LEVELS[level]["browse"] and record["api"].get("browse"):
                record["protocol_violation"] = "Browse used in a level without tag browsing"
            record["ingestor_restarted"] = container_started_after("timescale-ingestor", t0)
        else:
            text = read_from(state.get("nodered_log"), nr_offset)
            (tdir / "nodered.log").write_text(text, encoding="utf-8")
            record["nodered"] = nodered_activity(text)
            flows_path = nodered_dir(cfg) / "flows.json"
            if flows_path.exists():
                flows = json.loads(flows_path.read_text(encoding="utf-8") or "[]")
                shutil.copy(flows_path, tdir / "flows.json")
                record["nodered"].update(flow_stats(flows))
    except Exception as exc:
        record["evidence_error_logs"] = repr(exc)


def print_summary(record: dict, tdir: Path) -> None:
    print("\n" + "-" * 78)
    print(f"{record['trial_id']}: {record['status'].upper()}")
    if record["time_to_valid_data_s"] is not None:
        print(f"time to valid data: {record['time_to_valid_data_s']} s "
              f"(first row after {record['time_to_first_data_s']} s), device {record['device']}")
    else:
        print(f"duration: {record['duration_s']} s")
    if record.get("api"):
        print(f"dashboard actions: {record['api']}")
    if record.get("nodered"):
        nr = record["nodered"]
        print(f"Node-RED: {nr.get('deploys')} deploy(s), {nr.get('nodes', '?')} nodes, "
              f"{nr.get('function_lines', '?')} lines of function code")
    if record.get("protocol_violation"):
        print(f"WARNING: {record['protocol_violation']}")
    if record.get("pilot_error"):
        print(f"pilot error: {record['pilot_error']}")
    print(f"evidence: {tdir}")
    print("-" * 78)


# --- automated operator (pilot) ---------------------------------------------

def browse(cfg, gw: str, node: str) -> list:
    body = {"endpoint_url": cfg.opcua_endpoint, "node_id": node}
    return post_json(f"{orch_api(cfg)}/gateways/{gw}/opcua/browse", body)["nodes"]


def pilot_framework(cfg, level: str, state: dict) -> None:
    api = orch_api(cfg)
    if LEVELS[level]["discovery"]:
        gw = wait_until("discovered gateway", lambda: find_gateway(cfg), 30)
    else:
        gw = post_json(f"{api}/gateways/register", {"ip": cfg.gateway_ip, "port": cfg.gateway_port})["gateway_id"]
    post_json(f"{api}/gateways/{gw}/configure", {})
    dev = cfg.device_id
    if LEVELS[level]["browse"]:
        module = next(n for n in browse(cfg, gw, "i=85") if n["name"] == "FestoTrialModule")
        datapoints = [{"name": n["name"], "datatype": n["datatype"], "unit": "",
                       "local_topic": f"devices/{dev}/{n['name']}", "address": {"node_id": n["node_id"]}}
                      for n in browse(cfg, gw, module["node_id"]) if n["name"] in STUDY_NAMES]
    else:
        datapoints = connector(cfg.opcua_endpoint)["datapoints"]  # typed from the device sheet
    post_json(f"{api}/provision", {"gateway_id": gw, "device_id": dev, "protocol": "opcua", "interval": 1.0,
                                   "connection": {"endpoint_url": cfg.opcua_endpoint},
                                   "datapoints": datapoints})
    if not LEVELS[level]["auto_mapping"]:
        device = device_system_id(state["serial"], dev)
        with psycopg.connect(cfg.pg_dsn, autocommit=True) as conn:
            for dp in datapoints:
                conn.execute("INSERT INTO topic_map (topic, device, datapoint, datatype, unit) "
                             "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (topic) DO NOTHING",
                             (f"{cfg.uns_prefix}/{dp['local_topic']}", device, dp["name"], dp["datatype"], ""))
        sh(["docker", "restart", "timescale-ingestor"])


def reference_flow(cfg) -> list:
    """The Festo reference flow (generate_festo.py) with this lab's broker and database."""
    sys.path.insert(0, str(nodered_dir(cfg)))
    import generate_flows as gen
    gen.DEVICES = copy.deepcopy(gen.DEVICES)
    gen.DEVICES["opcua"] = {"device": cfg.device_id, "endpoint": cfg.opcua_endpoint,
                            "datapoints": [(n, t, "", node_id(s)) for n, s, t in POINTS if n in STUDY_NAMES]}
    for proto in ("modbus", "s7", "mqtt"):
        gen.DEVICES[proto]["datapoints"] = []
    gen.INTERVAL_MS = 1000
    gen.UNS_DEVICES = f"{cfg.uns_prefix}/devices/{cfg.device_id}/"
    nodes = [n for n in gen.opcua_tab().json() + gen.server_tab().json() if n.get("topic") != "meter1/#"]
    pg = psycopg.conninfo.conninfo_to_dict(cfg.pg_dsn)
    for n in nodes:
        if n.get("type") == "mqtt-broker":
            n["broker"], n["port"] = cfg.server_ip, "1883"
        if n.get("type") == "postgreSQLConfig":
            n.update(host=pg.get("host", "127.0.0.1"), port=int(pg.get("port", 5432)), database=pg.get("dbname"))
            n["credentials"] = {"user": pg.get("user"), "password": pg.get("password")}
    return nodes


def pilot_nodered(cfg, level: str, state: dict) -> None:
    r = httpx.post(nodered_url(cfg) + "/flows", json=reference_flow(cfg), timeout=30,
                   headers={"Node-RED-Deployment-Type": "full"})
    r.raise_for_status()


# --- checks and reporting ---------------------------------------------------

def check(cfg) -> bool:
    results = []

    def item(name, fn):
        try:
            detail = fn()
            results.append(True)
            print(f"  OK    {name}" + (f"  ({detail})" if detail not in (None, True) else ""))
        except Exception as exc:
            results.append(False)
            print(f"  FAIL  {name}: {exc}")

    print("Server (this PC)")
    item("Docker services", lambda: ", ".join(
        n for n in ("timescale", "mqtt-broker", "aas-environment", "dashboard")
        if n in sh(["docker", "ps", "--format", "{{.Names}}"]).stdout) or (_ for _ in ()).throw(RuntimeError("none")))
    item("TimescaleDB", lambda: psycopg.connect(cfg.pg_dsn).close())
    item("BaSyx", lambda: httpx.get(cfg.basyx_url + "/shells", timeout=5).raise_for_status() and None)
    item("orchestrator venv", lambda: (Path(cfg.server_dir) / ".venv").exists() or (_ for _ in ()).throw(
        RuntimeError(f"no .venv in {cfg.server_dir}; run redeploy.ps1 -NoStart")))
    item("Node-RED installed", lambda: (nodered_dir(cfg) / "node_modules" / "node-red" / "red.js").exists()
         or (_ for _ in ()).throw(RuntimeError("run npm install in " + cfg.node_red_dir)))
    print("Gateway")
    item("gateway API", lambda: get_json(gateway_url(cfg) + "/api/health")["gateway_id"])
    item("SSH", lambda: ssh(cfg, "echo ok", 30).stdout.strip())
    item("Festo simulator container", lambda: ssh(cfg, "docker inspect -f '{{.State.Status}}' festo-sim", 30).stdout.strip())
    item("gateway reaches the simulator", lambda: f"{len(post_json(gateway_url(cfg) + '/api/opcua/browse', {'endpoint_url': cfg.opcua_endpoint, 'node_id': 'ns=2;i=1'})['nodes'])} nodes")

    def skew():
        remote = float(ssh(cfg, "date +%s.%N", 30).stdout)
        delta = abs(remote - time.time())
        if delta > 2:
            raise RuntimeError(f"gateway clock differs by {delta:.1f} s; rows are stamped by the gateway")
        return f"{delta:.2f} s"
    item("clock difference", skew)
    print("State: " + json.dumps(load_state()) if STATE_FILE.exists() else "State: not prepared yet")
    return all(results)


def report() -> None:
    trials = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((RESULTS / "trials").glob("*/trial.json"))]
    if not trials:
        raise SystemExit("no trials yet")
    fields = ["trial_id", "level", "level_name", "operator", "status", "started_at", "time_to_first_data_s",
              "time_to_valid_data_s", "duration_s", "milestones", "notes", "api_writes", "api_errors",
              "browse_calls", "provision_calls", "ingestor_restarted", "nodered_deploys", "nodered_nodes",
              "nodered_function_lines", "rows_without_metadata", "protocol_violation"]
    rows = []
    for t in trials:
        api, nr = t.get("api") or {}, t.get("nodered") or {}
        rows.append({
            **{k: t.get(k) for k in fields if k in t},
            "milestones": "; ".join(f"{e['elapsed_s']}s {e['text']}" for e in t["events"] if e["type"] == "milestone"),
            "notes": "; ".join(e["text"] for e in t["events"] if e["type"] == "note"),
            "api_writes": api.get("writes"), "api_errors": api.get("errors"),
            "browse_calls": api.get("browse"), "provision_calls": api.get("provision"),
            "nodered_deploys": nr.get("deploys"), "nodered_nodes": nr.get("nodes"),
            "nodered_function_lines": nr.get("function_lines")})
    with open(RESULTS / "trials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = ["# Ablation study results", "",
             "Time to valid data = from pressing Enter until all five signals are stored with the expected "
             "metadata. Only successful trials count towards the times.", "",
             "| Level | Operator | Trials (ok/all) | Median s | Min s | Max s | Median first row s |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for level in LEVELS:
        for operator in sorted({t["operator"] for t in trials if t["level"] == level}):
            group = [t for t in trials if t["level"] == level and t["operator"] == operator]
            ok = [t for t in group if t["status"] == "success"]
            times = [t["time_to_valid_data_s"] for t in ok]
            firsts = [t["time_to_first_data_s"] for t in ok if t["time_to_first_data_s"] is not None]
            fmt = lambda v: f"{v:.0f}" if v is not None else "-"
            lines.append(f"| {level} {LEVELS[level]['name']} | {operator} | {len(ok)}/{len(group)} | "
                         f"{fmt(statistics.median(times) if times else None)} | {fmt(min(times) if times else None)} | "
                         f"{fmt(max(times) if times else None)} | {fmt(statistics.median(firsts) if firsts else None)} |")
    flagged = [t["trial_id"] for t in trials if t.get("protocol_violation")]
    if flagged:
        lines += ["", "Protocol violations (Browse used where disabled): " + ", ".join(flagged)]
    lines += ["", f"Per-trial data: results/trials.csv ({len(trials)} trials)."]
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="check the environment")
    for name in ("prepare", "trial", "pilot"):
        p = sub.add_parser(name)
        p.add_argument("level", choices=list(LEVELS))
        p.add_argument("--force", action="store_true", help="reset even if another trial or pilot is running")
        if name in ("trial", "pilot"):
            p.add_argument("--no-prepare", action="store_true", help="skip the reset")
    sub.add_parser("report", help="write results/trials.csv and results/summary.md")
    sub.add_parser("cards", help="write the filled-in task cards to materials/task_cards.md")
    args = parser.parse_args()
    cfg = load_config()
    if args.cmd == "check":
        sys.exit(0 if check(cfg) else 1)
    if args.cmd == "cards":
        return print(f"written: {write_cards(cfg)}")
    if args.cmd == "report":
        return report()
    if args.cmd == "prepare" or not args.no_prepare:
        prepare(cfg, args.level, force=args.force)
    if args.cmd == "trial":
        run_trial(cfg, args.level, "operator")
    elif args.cmd == "pilot":
        fn = pilot_framework if LEVELS[args.level]["framework"] else pilot_nodered
        run_trial(cfg, args.level, "pilot", pilot_fn=fn)


if __name__ == "__main__":
    main()
