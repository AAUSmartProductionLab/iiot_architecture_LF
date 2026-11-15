# Reproduce the Festo OPC UA test setup

This synthetic CECC-LK interface exposes nine nodes: conveyor direction, carrier
availability, stopper release, RFID read/write flags, carrier ID, product ID and
manual-job start/finish. It makes no connection to real equipment. NodeIds are
listed in `festo_module.py`; its namespace URI and process behavior are synthetic.
The product ID's UInt32 type is inferred from the PLC's `udi` naming convention.

From the repository root, with Python 3.11 or later:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r tests/simulators/requirements.txt
python tests/simulators/festo_module.py --host 0.0.0.0 --port 14840
```

Wait for READY. Default automatic mode changes test signals every 3 seconds.
Use `--manual` to preserve control writes; it models carrier availability as the
inverse of stopper release, but does not emulate a full PLC or RFID hardware.
Stop with Ctrl+C. Use a lab network: this endpoint uses anonymous access and no
OPC UA transport security. Allow gateway access to TCP port 14840.

## Connect through the wizard

Deploy the edge server and gateway using the repository README. Use separate hosts
for the default Compose stacks; their ports and container names overlap. Configure
the gateway MQTT bridge, then Add connector:

1. Select OPC UA and use device ID `festo_trial`.
2. Set endpoint to `opc.tcp://SIMULATOR_LAN_IP:14840`, polling interval 1000 ms.
   Use an address reachable from the gateway, not localhost or 0.0.0.0.
3. On Datapoints, click **Browse tags**, then **Open** beside FestoTrialModule.
4. Add conveyor_right, carrier_available, carrier_id, product_id and job_finished.
5. Review the filled NodeIds, types, names and topics; leave units empty, then provision.

Browse runs on the selected gateway. It only browses references and reads type
metadata; it does not write process values or provision anything. Open enters a
node's children; Up returns to its parent. Filter applies to the current page.
Pages contain up to 100 references; navigation is bounded to 5,100 references per
folder and requests to 15 seconds. Very large/slow folders may need manual NodeIds.
Arrays and unrecognized types are left for manual configuration. Units are not
inferred. Browsing supports anonymous unsecured endpoints, matching the current
wizard's connection settings; username/certificate setup is not implemented.

Rebuild the **gateway-agent**, **orchestrator** and **dashboard** after upgrading:
the gateway now installs asyncua for browsing. Restarting old images is insufficient.
For host Python installations, reinstall `edge_gateway/requirements.txt`.

## Reference files and Node-RED comparison

Export a five-point configuration without starting a server:

```bash
python tests/simulators/festo_module.py --host SIMULATOR_LAN_IP --port 14840 --export /tmp/festo-connector.json
python tests/node-red-baseline/generate_festo.py --endpoint opc.tcp://SIMULATOR_LAN_IP:14840 --output /tmp/festo-flows.json
```

Use any writable output path on Windows. The connector export needs a `gateway_id`
field before POST to the orchestrator's `/api/provision` endpoint.

The Node-RED generator reads PG_HOST, PG_PORT, PG_DATABASE, MQTT_HOST and MQTT_PORT;
set them BEFORE generating. Install packages and run Node-RED using `tests/README.md`.
Import the exported flow in a disposable instance, enter database credentials in
its PostgreSQL config node, and deploy. No credentials are exported. Use the same
measurements table/schema as the architecture. Stop other publishers/ingestors
between comparison conditions to avoid duplicate writes.

Use `tests/evaluation/verify_contract.py --protocol festo` with the condition and
start timestamp described in the [verification guide](../evaluation/README.md).
The generic `deploy_and_verify.py` targets different fixtures. Check these five topics:
`uns/enterprise/site/area/line/devices/festo_trial/<name>`, where name is one of the
five selected points above. Confirm fresh rows, correct names, empty units, three
JSON booleans and two integers. Automatic carrier_id is 100–199, product_id 1000–1099.
FULL uses a gateway-qualified device identity; the baseline uses `festo_trial`.
Observe at least two changes and compare to the simulator's direct OPC UA readings.

The reference Node-RED path publishes directly to the central broker. This supports
a configuration-effort comparison, not an equal-topology runtime benchmark.

## Automated checks

```bash
python -m pip install -r tests/requirements.txt -r tests/simulators/requirements.txt
python -m pytest tests/integration/test_festo.py tests/integration/test_opcua_browse_live.py -q
```

The real-adapter test needs Mosquitto on PATH. Tests use ephemeral local ports and
clean up their own processes. These are software correctness checks, not usability
or deployment results.
