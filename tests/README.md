# Tests

From the repository root, with Python 3.11 or later:

```bash
python -m pip install -r tests/requirements.txt
python -m pytest tests/unit tests/evaluation -q
python -m pytest tests/integration -q
```

Unit tests cover configuration, decoding, AAS generation, ingestion controls,
OPC UA browsing and the history API. Evaluation tests check the data verifier.

Integration tests start local simulators and exercise the real adapters. Install
`mosquitto` on PATH for MQTT checks. S7 needs port 102 available; dependent tests
skip when prerequisites are missing. Override `OPCUA_PORT` and `MODBUS_PORT` if the
default ports are occupied.

Database history tests require `HISTORY_TEST_DSN` pointing to a disposable PostgreSQL
or TimescaleDB database. They create and remove a unique schema; without that
variable, they skip. Run them with `python -m pytest tests/integration/test_history_store.py -q`.

## Simulators and data verification

- [Festo OPC UA setup](simulators/FESTO.md): five-point test fixture, wizard browsing
  and matching Node-RED flow.
- [Data verification](evaluation/README.md): check stored values and mapping controls.
- `python tests/simulators/run_simulators.py`: additional OPC UA, Modbus, S7 and
  MQTT fixtures defined in `simulators/devices.py`.

## Node-RED baseline

Use a disposable instance. The pipeline is protocol read → MQTT → metadata mapping
→ parameterized database INSERT. Configure the broker and database with `MQTT_HOST`,
`MQTT_PORT`, `PG_HOST`, `PG_PORT` and `PG_DATABASE` before generating flows.

```bash
cd tests/node-red-baseline
npm install
createdb baseline
psql -d baseline -f schema.sql
python generate_flows.py
npm start
```

Open `http://localhost:1880`, import the generated `flows/all.json` (or an individual
protocol tab), enter PostgreSQL credentials in its configuration node, and deploy.
Generated flow files and Node-RED runtime state are ignored by Git.

For the Festo simulator, import the output of `generate_festo.py` instead; see the
[Festo instructions](simulators/FESTO.md). Stop other publishers/ingestors when
switching conditions. `deploy_and_verify.py` is an optional smoke check for all
of the generic fixtures; it replaces the target Node-RED instance's flows.
