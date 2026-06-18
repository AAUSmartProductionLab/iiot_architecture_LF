# iiot_architecture_LF

Free and open-source IIoT architecture for teaching companies how to ingest and use
data from production systems.

It auto-discovers **edge gateways** on the LAN, adapts industrial protocols
(Modbus, S7/snap7, OPC UA, USB, …) to **MQTT**, builds **Asset Administration Shells
(AAS)** in Eclipse BaSyx describing each gateway and device (no live values in the
AAS — pure semantics), and ingests the live MQTT data into **TimescaleDB**, all
driven from a **React control board**.

---

## Architecture

```
            EDGE GATEWAY  (e.g. ap2030, Linux)              EDGE SERVER (Linux or Windows)
  ┌───────────────────────────────────────────┐      ┌──────────────────────────────────────────┐
  device ──(Modbus/S7/OPC UA/USB)── adapter ──▶ HiveMQ ─bridge▶ HiveMQ ──▶ timescale-ingestor ──▶ TimescaleDB
        (one adapter container per connector,   (devices/#)   (uns/#)         ▲
         launched by the gateway-agent via                                     │ sm-repository/# events
         the Docker socket)                                                    │
            gateway-agent ──mDNS advertise──────────────▶ orchestrator ──▶ Eclipse BaSyx (AAS)
            (manifest / configure / connectors)          (discovery, AAS sync, dashboard API)
                                                                  ▲
                                                          React dashboard (browser)
```

- **Data plane:** adapter → gateway broker (`devices/#`) → MQTT **bridge** → server broker
  (`uns/...`) → ingestor → TimescaleDB. Live values never touch the AAS.
- **Semantic plane:** orchestrator builds the AAS (Digital Nameplate, Software Nameplate,
  Asset Interfaces Description, Hierarchical Structures) in BaSyx on discovery/provision.
- **Config-event plane:** BaSyx emits submodel events; the ingestor uses them to learn each
  topic's device/datapoint/unit so it can store the data meaningfully.

### Ports

| Service | Port | Host |
|---------|------|------|
| Orchestrator API | 8000 | edge server |
| BaSyx AAS environment | 8081 | edge server |
| BaSyx AAS web UI (aas-gui) | 8082 | edge server |
| React dashboard (Vite dev) | 5173 | edge server |
| TimescaleDB | 5432 | edge server |
| HiveMQ (MQTT) | 1883 | each host |
| HiveMQ control center | 8080 | each host |
| Gateway agent API | 8000 | edge gateway |

---

## Prerequisites

- **Docker + Docker Compose v2** on both machines.
- Both machines on the **same LAN/subnet** (mDNS discovery + the MQTT bridge need this).
- Edge server only, **if running on Windows/Mac**: **Python 3.11** (the orchestrator must run on
  the host for LAN mDNS — see below).

---

## Run — Edge server

The server stack is `edge_server/docker-compose.yaml`: TimescaleDB, HiveMQ, BaSyx
(`aas-environment` + `aas-gui`), the **orchestrator**, the **dashboard**, and the
**timescale-ingestor**.

The **orchestrator** needs the host network stack to receive LAN mDNS, so it differs by OS.

### Linux (fully containerized — recommended)

```bash
cd edge_server
docker compose build
# host-net override puts the orchestrator on the host network for mDNS:
docker compose -f docker-compose.yaml -f docker-compose.host.yml up -d
```

### Windows / macOS (Docker Desktop)

Docker Desktop containers can't receive LAN mDNS, so run the data services as containers
and the orchestrator as host Python:

```bash
cd edge_server
docker compose up -d timescale hivemq aas-environment aas-gui dashboard timescale-ingestor

# orchestrator on the host (LAN mDNS works here):
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn orchestrator.main:app --app-dir . --host 0.0.0.0 --port 8000
```

Open the dashboard at **http://localhost:5173** and the AAS viewer at **http://localhost:8082**.

> The dashboard calls the orchestrator at `VITE_API_BASE` (default `http://localhost:8000`).
> To open the board from another machine, set `VITE_API_BASE=http://<server-ip>:8000` on the
> `dashboard` service.

---

## Run — Edge gateway (e.g. ap2030, Linux)

The gateway stack is `edge_gateway/docker-compose.yaml`: HiveMQ (with the bridge extension),
the **gateway-agent**, a build-only **connector-adapter** image, and an optional **S7 simulator**.

```bash
cd edge_gateway
# build gateway-agent, the connector-adapter image, and the S7 simulator:
docker compose --profile build --profile sim build

# run with host networking (mDNS) + the S7 simulator:
docker compose -f docker-compose.yaml -f docker-compose.host.yml --profile sim up -d
```

- Omit `--profile sim` when connecting to **real** field devices instead of the simulator.
- The gateway gets a stable auto identity (persisted in the `gateway_identity` volume); override
  with `GATEWAY_ID` / `SERIAL_NUMBER` env if desired.
- The gateway-agent restarts its HiveMQ broker every `BRIDGE_RESTART_HOURS` (default 4) to keep the
  HiveMQ Enterprise Bridge Extension's 5-hour trial alive (no license needed). Add a HiveMQ license
  for production.

---

## Use it

1. Open **http://localhost:5173** (edge server). The gateway appears under **Gateways**
   (auto-discovered via mDNS). If discovery is unavailable (e.g. both on one Windows box),
   use **Register gateway** with the gateway's IP/port.
2. Select the gateway → **Configure MQTT bridge** (the edge server IP is pre-filled) → Apply.
   This points the gateway broker's bridge at the server and restarts it.
3. **Add connector**: pick a protocol (Modbus / OPC UA / S7 / USB), fill the per-protocol fields,
   and Provision. The gateway-agent launches an adapter container that reads the device and
   publishes to MQTT; the orchestrator creates the device's AAS.
4. **Devices** shows each datapoint with its latest ingested value. **Asset Shells** renders the
   full AAS (nameplate, software, interfaces with source/UNS topics, topology) + lifecycle.

---

## Stop / tear down

```bash
# edge gateway
cd edge_gateway && docker compose -f docker-compose.yaml -f docker-compose.host.yml --profile sim down
# edge server
cd edge_server && docker compose down            # add -v to also wipe volumes (BaSyx/Timescale/HiveMQ data)
```

(If you ran the orchestrator as host Python on Windows, stop that process too.)
