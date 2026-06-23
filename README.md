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

## Run — edge server

```bash
cd edge_server
docker compose build

# Linux (orchestrator on host network for mDNS):
docker compose -f docker-compose.yaml -f docker-compose.host.yml up -d

# Windows/macOS (containers can't get LAN mDNS → run the orchestrator on the host):
docker compose up -d timescale hivemq aas-environment aas-gui dashboard timescale-ingestor
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn orchestrator.main:app --app-dir . --host 0.0.0.0 --port 8000
```

Dashboard → http://localhost:5173 · AAS viewer → http://localhost:8082

## Run — edge gateway

```bash
cd edge_gateway
docker compose --profile build build
docker compose -f docker-compose.yaml -f docker-compose.host.yml up -d

# Optional: S7 PLC simulator for testing without real hardware (joins the
# gateway network; start it after the stack is up):
docker compose -f docker-compose.sim.yml up -d --build
```

The gateway-agent restarts HiveMQ every `BRIDGE_RESTART_HOURS` (default 4) to
keep the bridge extension's trial alive.

## Use it

In the dashboard: the gateway appears under **Gateways** (auto-discovered; or **Register gateway**
manually) → **Configure MQTT bridge** (server IP pre-filled) → **Add connector** (pick protocol,
fill fields, provision). **Devices** shows latest values; **Asset Shells** renders the full AAS.

## Stop

```bash
cd edge_gateway && docker compose -f docker-compose.sim.yml down   # if started
cd edge_gateway && docker compose -f docker-compose.yaml -f docker-compose.host.yml down
cd edge_server && docker compose down        # add -v to wipe data volumes
```
