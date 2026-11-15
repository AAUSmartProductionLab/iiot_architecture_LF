# Task cards

`study.py trial <level>` prints the Common section and the level's section, with
this lab's values filled in. `study.py cards` writes all of them, filled in, to
`materials/task_cards.md`.

## Common

Goal: store the Festo module's five signals in TimescaleDB with their metadata.

| Datapoint name | Signal |
| --- | --- |
| conveyor_right | Conveyor running to the right |
| carrier_available | Carrier present at the stopper |
| carrier_id | Carrier ID read from the RFID tag |
| product_id | Product number from the MES data |
| job_finished | Manual job finished at the workplace |

Settings, the same in every level:

| Setting | Value |
| --- | --- |
| Device id | `{device_id}` (an automatic name also counts) |
| OPC UA endpoint | `{endpoint}`, anonymous, no security |
| Polling interval | 1000 ms (the wizard's default is 2000) |
| Units | empty |

Done when all five signals are stored under one device, each latest row with the
datapoint name above, an empty unit and a JSON boolean or integer value. In
L0-L3 the device is the gateway-qualified identity `{serial}_<device id>`, for
example `{expected_device}`; in L4 it is the name you write, `{device_id}`. The
clock then stops by itself.

Optional terminal commands during a trial: `m <text>` records a milestone (for
example `m tags found`), `n <text>` a note, `s` shows the status, `q` gives up.

## L0 Full framework

Dashboard: {dashboard} (reload the page first).

1. Select the discovered gateway.
2. **Configure MQTT bridge**: keep the pre-filled broker IP and UNS path, and save.
3. **Add connector**: protocol OPC UA, then the device id, endpoint and polling
   interval from the settings table.
4. Datapoints: click **Browse tags**, **Open** FestoTrialModule and add the five
   signals named in the table. Leave the units empty.
5. **Provision**.

## L1 No auto-discovery

As L0, but the gateway is not discovered: use **Register manually** with IP
`{gateway_ip}` and port 8000, then do L0 steps 2 to 5.

## L2 No tag browsing

As L1, but do not use **Browse tags**. Add each of the five datapoints by hand:
name from the table above, data type and NodeId from
`tests/ablation/materials/device_sheet.md`.

## L3 No automatic mapping

As L2, but automatic mapping from the device AIDs is off: rows are stored without
device, datapoint and unit until you map their topics yourself.

1. Register the gateway, configure the bridge and provision the connector as in L2.
2. Find each signal's topic on the server broker: `{uns_prefix}/` followed by the
   datapoint's local topic.
3. Insert one `topic_map` row per signal: topic, device `{serial}_<device id>`
   (for example `{expected_device}`), datapoint name, data type, unit `''`. For
   example, open SQL with `docker exec -it timescale psql -U postgres`.
4. Reload the mapping: `docker restart timescale-ingestor`.

## L4 Node-RED baseline

No framework: the orchestrator and ingestor are stopped and the gateway is idle.
Use Node-RED at {node_red}. The workspace is empty; the OPC UA and PostgreSQL
nodes are installed. Find the signals in `tests/ablation/materials/device_sheet.md`.

1. Read the five signals from `{endpoint}` every 1000 ms.
2. Publish each value to the MQTT broker `{server_ip}:1883` on
   `{uns_prefix}/devices/{device_id}/<datapoint name>`. Use `{server_ip}`, not
   localhost: localhost:1883 on this PC is a different broker.
3. Subscribe to those topics and insert each message into PostgreSQL
   `localhost:5432`, database `postgres`, user `postgres`, password `admin`:
   table `measurements (time timestamptz, topic text, device text, datapoint text,
   value jsonb, unit text)` with device `{expected_device}` and unit `''`.
