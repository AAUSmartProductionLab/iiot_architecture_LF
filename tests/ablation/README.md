# Ablation study

Measures how long one operator needs to store the Festo module's five signals in
TimescaleDB with correct metadata, as framework features are removed one at a time.

| Level | Removed | The operator |
| --- | --- | --- |
| L0 | nothing | selects the discovered gateway, configures the bridge, browses tags, provisions |
| L1 | auto-discovery | registers the gateway by IP first |
| L2 | + tag browsing | types NodeIds, types and names from the [device sheet](materials/device_sheet.md) |
| L3 | + automatic mapping | also writes the `topic_map` rows in SQL and restarts the ingestor |
| L4 | the whole framework | builds OPC UA -> MQTT -> PostgreSQL in Node-RED by hand |

The task cards are in [materials/tasks.md](materials/tasks.md). The runner prints
them with this lab's values when a trial starts, and `study.py cards` writes the
filled-in set to [materials/task_cards.md](materials/task_cards.md) to keep open
during trials. Lab settings are in [config.json](config.json).

## Before the first trial

From the root of the development checkout (the one containing `tests/ablation` and
the `.venv` used for the tests), not the server install folder:

```powershell
.\.venv\Scripts\python.exe tests\ablation\study.py check
```

Every line must say OK. The study tool starts and stops the orchestrator itself,
so do not run `run-orchestrator.ps1` during the study.

## One trial

```powershell
.\.venv\Scripts\python.exe tests\ablation\study.py trial L2
```

1. The tool resets everything (about 40 s) and prints the task card and a trial ID.
2. Start the screen recording, then press Enter. The clock starts.
3. Do the task. Type `m tags found` (or any text) for milestones, `n <text>` for
   notes, `s` for status, `q` to give up.
4. The clock stops by itself once all five signals are stored correctly. The
   results go to `results/trials/<trial ID>/`.

Run at least three rounds of all levels and alternate the order (L0 to L4, then
L4 to L0) to balance learning effects.

## Recorded automatically

- Time to the first stored row and to valid data; milestones and notes.
- Dashboard actions from the orchestrator log: gateway registrations, bridge
  configurations, browse and provisioning calls, deletions, API errors.
- L3: whether the ingestor was restarted. L2 and L3: a warning if Browse was used.
- L4: Node-RED deploys, errors, number of nodes, lines of function code and the
  final `flows.json`.
- The gateway's final connector configuration, `topic_map` and every row stored
  during the trial (`rows.csv`).

Record the screen yourself, named with the trial ID, and count from the video
anything else you need, such as clicks, documentation lookups or mistakes.

## Pilot runs and the report

```powershell
.\.venv\Scripts\python.exe tests\ablation\study.py pilot L3   # the same task via the API
.\.venv\Scripts\python.exe tests\ablation\study.py report     # results/trials.csv, results/summary.md
```

Pilot times measure system latency (bridge restart, adapter start-up), not human
effort; the report lists them separately from operator trials.

After the study, `study.py prepare L0` leaves the system in normal operation with
the orchestrator running in the background. Running `redeploy.ps1` in the server's
`edge_server` folder stops it.

## Festo simulator on the gateway

The simulator runs on the gateway device as the container `festo-sim` (host
network, port 4840). To recreate it there:

```bash
docker build -t iiot/festo-sim -f - ~/iiot_architecture_LF/tests/simulators <<'EOF'
FROM python:3.11-slim
RUN pip install --no-cache-dir "asyncua>=1.1,<3"
WORKDIR /app
COPY festo_module.py .
CMD ["python", "-u", "festo_module.py", "--host", "0.0.0.0", "--port", "4840"]
EOF
docker run -d --name festo-sim --restart unless-stopped --network host iiot/festo-sim
```

## Validity notes

- The operator built the framework and knows the signals, so times are an expert
  best case. Report action counts alongside times.
- The simulator's Browse view is one flat folder with readable names. A real
  CODESYS tree is deeper and uses PLC symbol names, so browsing it takes longer.
- The Node-RED palette (OPC UA and PostgreSQL nodes) is preinstalled; installing it
  is not timed. Node-RED runs on the server PC and publishes straight to the server
  broker, so L4 compares configuration effort, not runtime behaviour.
- The wizard sets the topic `devices/<device>/<name>` for browsed tags but
  `devices/<name>` for typed ones. Success is judged on stored metadata, not topics.
