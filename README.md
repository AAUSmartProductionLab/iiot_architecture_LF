# iiot_architecture_LF

Free and open-source IIoT architecture: auto-discover **edge gateways**, adapt industrial
protocols (Modbus, S7/snap7, OPC UA, USB) to **MQTT**, describe everything as **Asset
Administration Shells** in Eclipse BaSyx, and ingest the live data into **TimescaleDB** — all
driven from a **React control board**.

## Architecture

```
EDGE GATEWAY (Linux)                          EDGE SERVER
────────────────────                          ───────────
device → adapter ─┐
                  ├→ HiveMQ ══bridge══════════→ HiveMQ → ingestor → TimescaleDB
gateway-agent ────┘     (devices/#)              (uns/#)
     │ mDNS + manifest
     └──────────────────────────────────────→ orchestrator ⇄ BaSyx (AAS)
                                                    ↑
                                              React dashboard
```

- **Data plane:** adapter → gateway broker → MQTT bridge → server broker → ingestor → TimescaleDB.
- **Semantic plane:** orchestrator builds each gateway/device AAS in BaSyx. *No live values in the AAS.*
- **Config plane:** BaSyx submodel events tell the ingestor each topic's device/datapoint/unit.

**Ports:** orchestrator `8000`, BaSyx `8081`, aas-gui `8082`, dashboard `5173`, TimescaleDB `5432`,
MQTT `1883`.

## Prerequisites

- Docker + Docker Compose v2 on both machines, on the **same LAN** (mDNS + bridge need it).
- A **Windows/macOS** edge server also needs **Python 3.11** (the orchestrator runs on the host for mDNS).

## Quick start (scripts)

Each role ships an `install.sh` (clone + build + start) and a `redeploy.sh`
(rebuild + restart an existing checkout). Both default to **host networking** so
mDNS auto-discovery works on Linux.

### Edge server

```bash
# one-liner: clone into ~/iiot_architecture_LF, build, start
curl -fsSL https://raw.githubusercontent.com/AAUSmartProductionLab/iiot_architecture_LF/main/edge_server/install.sh | bash

# from a checkout: rebuild + restart (data volumes preserved)
cd edge_server && ./redeploy.sh
```

Dashboard → http://localhost:5173 · AAS viewer → http://localhost:8082

### Edge gateway

```bash
curl -fsSL https://raw.githubusercontent.com/AAUSmartProductionLab/iiot_architecture_LF/main/edge_gateway/install.sh | bash

cd edge_gateway && ./redeploy.sh          # rebuild + restart
cd edge_gateway && ./redeploy.sh --sim    # also (re)build + restart the S7 simulator
```

The gateway `redeploy.sh` rebuilds the images, removes stale per-connector adapter
containers, seeds the bridge `config.xml` from its template if missing, clears the
HiveMQ `DISABLED` marker, and restarts the stack in order (broker → agent).

### Script options

| Option | Where | Effect |
| --- | --- | --- |
| `USE_HOST_NET=0` | both, env var | Bridge networking instead of host. Use on **Windows/macOS** Docker Desktop (host mode binds the VM, not the LAN). No mDNS → register gateways with the dashboard's **Register manually** button. |
| `--sim` | gateway `redeploy.sh` | Rebuild + restart the S7 PLC simulator (its own compose project; started after the gateway so it can join `gateway-net`). |
| `BRANCH` / `TARGET_DIR` / `REPO_URL` | `install.sh`, env vars | Pin a branch, change the install location, or use a fork. |

Examples: `USE_HOST_NET=0 ./redeploy.sh` · `curl -fsSL <url> | USE_HOST_NET=0 bash`

The gateway-agent restarts HiveMQ every `BRIDGE_RESTART_HOURS` (default 4) to keep
the bridge extension's trial alive.

## Use it

In the dashboard: the gateway appears under **Gateways** (auto-discovered, or
**Register manually**) → **Configure MQTT bridge** (server IP pre-filled) → **Add
connector** (a wizard: pick protocol, fill fields, provision — it then reports
whether the connector actually connected). **Devices** shows latest values and
each connector's connection status; **AAS** renders the full Asset Administration
Shell plus a network-topology view; **Logs** streams the gateway agent, the
broker, and per-connector container logs.

## Manual / advanced

Without the scripts — or to run the orchestrator on the host (Windows/macOS dev,
where containers can't get LAN mDNS):

```bash
# edge server — containerized
cd edge_server && docker compose build
docker compose -f docker-compose.yaml -f docker-compose.host.yml up -d   # Linux (mDNS)
docker compose up -d                                                     # Windows/macOS (no mDNS)

# edge server — orchestrator on the host (Windows/macOS)
docker compose up -d timescale hivemq aas-environment aas-gui dashboard timescale-ingestor
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn orchestrator.main:app --app-dir . --host 0.0.0.0 --port 8000

# edge gateway — containerized
cd edge_gateway && docker compose --profile build build
docker compose -f docker-compose.yaml -f docker-compose.host.yml up -d
docker compose -p s7-sim -f docker-compose.sim.yml up -d --build   # optional S7 simulator
```

## Stop

```bash
cd edge_gateway && docker compose -p s7-sim -f docker-compose.sim.yml down            # if started
cd edge_gateway && docker compose -f docker-compose.yaml -f docker-compose.host.yml down
cd edge_server  && docker compose -f docker-compose.yaml -f docker-compose.host.yml down   # add -v to wipe data
```
