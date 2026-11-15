"""Generate the Node-RED baseline flows from tests/simulators/devices.py.

The baseline is what an integrator would build by hand in Node-RED to get the
same result as the IIoT architecture: every datapoint of every test device
stored in the same `measurements` table, with device, datapoint and unit, under
the same UNS topics. It has no AAS, no discovery and no provisioning wizard.

Layout (one Node-RED instance, one tab per role; on a real site the gateway
tabs run on the gateway and the server tab on the edge server):

  Gateway – OPC UA  : inject (poll) -> OpcUa-Item x N -> OpcUa-Client (read) -> function (node id -> UNS) -> mqtt out
  Gateway – Modbus  : modbus-read x N -> function (decode float32 -> UNS) -> mqtt out
  Gateway – S7      : s7 in (all variables, on change) -> function (-> UNS) -> mqtt out
  Server – ingestion: mqtt in (uns/#, meter1/#) -> function (topic -> device/datapoint/unit) -> postgresql (INSERT)

The function bodies are written the way a competent Node-RED user would write
them (minimal, no error handling beyond skipping unknown topics), so the
baseline effort is not inflated.

    python generate_flows.py            # writes flows/*.json
    python generate_flows.py --stdout   # all tabs as one JSON array

The same structures are used by count_actions.py to count configuration effort.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "simulators"))
from devices import DEVICES, INTERVAL_MS, MQTT_HOST, MQTT_PORT, UNS_PREFIX  # noqa: E402

PG = {
    "host": os.getenv("PG_HOST", "127.0.0.1"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "database": os.getenv("PG_DATABASE", "baseline"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "admin"),
}

UNS_DEVICES = f"{UNS_PREFIX}/devices/"
INSERT_SQL = (
    "INSERT INTO measurements (time, topic, device, datapoint, value, unit) "
    "VALUES (to_timestamp($1), $2, $3, $4, $5::jsonb, $6);"
)


class Flow:
    """Collects nodes with deterministic ids and a simple grid layout."""

    def __init__(self, tab_id: str, label: str):
        self.tab = {"id": tab_id, "type": "tab", "label": label, "disabled": False, "info": ""}
        self.nodes: list[dict] = []
        self._n = 0

    def add(self, node_type: str, x: int, y: int, wires=None, **props) -> dict:
        self._n += 1
        node = {"id": f"{self.tab['id']}.{self._n}", "type": node_type, "z": self.tab["id"], "x": x, "y": y, **props}
        if wires is not None:
            node["wires"] = wires
        self.nodes.append(node)
        return node

    def config(self, node_type: str, cid: str, **props) -> dict:
        node = {"id": cid, "type": node_type, **props}
        self.nodes.append(node)
        return node

    def json(self) -> list[dict]:
        return [self.tab, *self.nodes]


def mqtt_broker_config(cid: str, name: str) -> dict:
    return {
        "id": cid, "type": "mqtt-broker", "name": name, "broker": MQTT_HOST, "port": str(MQTT_PORT),
        "clientid": "", "autoConnect": True, "usetls": False, "protocolVersion": "4", "keepalive": "60",
        "cleansession": True, "autoUnsubscribe": True,
        "birthTopic": "", "birthQos": "0", "birthRetain": "false", "birthPayload": "", "birthMsg": {},
        "closeTopic": "", "closeQos": "0", "closeRetain": "false", "closePayload": "", "closeMsg": {},
        "willTopic": "", "willQos": "0", "willRetain": "false", "willPayload": "", "willMsg": {},
        "userProps": "", "sessionExpiry": "",
    }


def function_node(flow: Flow, name: str, code: str, x: int, y: int, wires) -> dict:
    return flow.add(
        "function", x, y, wires=wires, name=name, func=code, outputs=1, timeout=0, noerr=0,
        initialize="", finalize="", libs=[],
    )


def mqtt_out(flow: Flow, broker_id: str, x: int, y: int) -> dict:
    return flow.add(
        "mqtt out", x, y, name="", topic="", qos="", retain="", respTopic="", contentType="",
        userProps="", correl="", expiry="", broker=broker_id,
    )


# --- gateway: OPC UA ----------------------------------------------------------

def opcua_tab() -> Flow:
    spec = DEVICES["opcua"]
    f = Flow("gw_opcua", "Gateway – OPC UA")
    f.nodes.append(mqtt_broker_config("cfg.mqtt.gw_opcua", "edge server"))
    f.config(
        "OpcUa-Endpoint", "cfg.opcua", name=spec["device"], endpoint=spec["endpoint"], secpol="None",
        secmode="None", none=True, login=False, usercert=False, usercertificate="", userprivatekey="",
    )
    out = mqtt_out(f, "cfg.mqtt.gw_opcua", 900, 60)
    lines = ",\n".join(f'    "{node_id}": "{name}"' for name, _dt, _u, node_id in spec["datapoints"])
    code = (
        "// OPC UA node id -> datapoint name\n"
        f"const names = {{\n{lines}\n}};\n"
        "const name = names[msg.topic];\n"
        "if (!name) return null;\n"
        f'msg.topic = "{UNS_DEVICES}" + name;\n'
        "msg.payload = { value: msg.payload, ts: Date.now() / 1000 };\n"
        "return msg;"
    )
    fn = function_node(f, "to UNS", code, 700, 60, [[out["id"]]])
    client = f.add(
        "OpcUa-Client", 500, 60, wires=[[fn["id"]], [], []], name="", endpoint="cfg.opcua", action="read",
        deadbandtype="a", deadbandvalue=1, time=10, timeUnit="s", certificate="n", localfile="",
        localkeyfile="", securitymode="None", securitypolicy="None", useTransport=False, maxChunkCount=1,
        maxMessageSize=8192, receiveBufferSize=8192, sendBufferSize=8192, setstatusandtime=False,
        keepsessionalive=False, applicationName="", applicationUri="",
    )
    items = []
    for i, (name, dtype, _unit, node_id) in enumerate(spec["datapoints"]):
        items.append(f.add("OpcUa-Item", 300, 60 + 50 * i, wires=[[client["id"]]],
                           item=node_id, datatype=dtype, value="", name=name))
    f.add(
        "inject", 100, 60, wires=[[it["id"] for it in items]], name=f"every {INTERVAL_MS // 1000} s",
        props=[{"p": "payload"}], repeat=str(INTERVAL_MS / 1000), crontab="", once=True, onceDelay="1",
        topic="", payload="", payloadType="date",
    )
    return f


# --- gateway: Modbus --------------------------------------------------------

def modbus_tab() -> Flow:
    spec = DEVICES["modbus"]
    f = Flow("gw_modbus", "Gateway – Modbus")
    f.nodes.append(mqtt_broker_config("cfg.mqtt.gw_modbus", "edge server"))
    f.config(
        "modbus-client", "cfg.modbus", name=spec["device"], clienttype="tcp", bufferCommands=True,
        stateLogEnabled=False, queueLogEnabled=False, failureLogEnabled=True, tcpHost=spec["host"],
        tcpPort=str(spec["port"]), tcpType="DEFAULT", serialPort="/dev/ttyUSB", serialType="RTU-BUFFERD",
        serialBaudrate="9600", serialDatabits="8", serialStopbits="1", serialParity="none",
        serialConnectionDelay="100", serialAsciiResponseStartDelimiter="0x3A", unit_id=str(spec["unit_id"]),
        commandDelay="1", clientTimeout="1000", reconnectOnTimeout=True, reconnectTimeout="2000",
        parallelUnitIdsAllowed=True, showErrors=False, showWarnings=True, showLogs=True,
    )
    out = mqtt_out(f, "cfg.mqtt.gw_modbus", 700, 60)
    code = (
        "// two 16-bit registers (big-endian) -> float32\n"
        "const buf = Buffer.alloc(4);\n"
        "buf.writeUInt16BE(msg.payload[0], 0);\n"
        "buf.writeUInt16BE(msg.payload[1], 2);\n"
        f'msg.topic = "{UNS_DEVICES}" + msg.topic;\n'
        "msg.payload = { value: buf.readFloatBE(0), ts: Date.now() / 1000 };\n"
        "return msg;"
    )
    fn = function_node(f, "decode float32", code, 500, 60, [[out["id"]]])
    for i, (name, _dtype, _unit, register) in enumerate(spec["datapoints"]):
        f.add(
            "modbus-read", 250, 60 + 60 * i, wires=[[fn["id"]], []], name=name, topic=name,
            showStatusActivities=False, logIOActivities=False, showErrors=False, showWarnings=True,
            unitid="", dataType="HoldingRegister", adr=str(register), quantity="2",
            rate=str(INTERVAL_MS), rateUnit="ms", delayOnStart=False, startDelayTime="",
            server="cfg.modbus", useIOFile=False, ioFile="", useIOForPayload=False, emptyMsgOnFail=False,
        )
    return f


# --- gateway: S7 --------------------------------------------------------------

def s7_tab() -> Flow:
    spec = DEVICES["s7"]
    f = Flow("gw_s7", "Gateway – S7")
    f.nodes.append(mqtt_broker_config("cfg.mqtt.gw_s7", "edge server"))
    vartable = [
        {"name": name, "addr": f"DB{spec['db']},{dtype}{start}"}
        for name, dtype, _unit, start in spec["datapoints"]
    ]
    f.config(
        "s7 endpoint", "cfg.s7", name=spec["device"], transport="iso-on-tcp", address=spec["host"],
        port=str(spec["port"]), rack=str(spec["rack"]), slot=str(spec["slot"]), localtsaphi="01",
        localtsaplo="00", remotetsaphi="01", remotetsaplo="00", connmode="rack-slot", adapter="",
        busaddr="2", cycletime=str(INTERVAL_MS), timeout="2000", vartable=vartable,
    )
    out = mqtt_out(f, "cfg.mqtt.gw_s7", 650, 60)
    code = (
        "// variable name (from the endpoint's variable table) -> UNS\n"
        f'msg.topic = "{UNS_DEVICES}" + msg.topic;\n'
        "msg.payload = { value: msg.payload, ts: Date.now() / 1000 };\n"
        "return msg;"
    )
    fn = function_node(f, "to UNS", code, 450, 60, [[out["id"]]])
    f.add("s7 in", 200, 60, wires=[[fn["id"]]], name="", endpoint="cfg.s7", mode="all-split", variable="", diff=True)
    return f


# --- server: ingestion ----------------------------------------------------------

def server_tab() -> Flow:
    f = Flow("srv_ingest", "Server – ingestion")
    f.nodes.append(mqtt_broker_config("cfg.mqtt.srv", "local broker"))
    pg = f.config(
        "postgreSQLConfig", "cfg.pg", name="", host=PG["host"], hostFieldType="str", port=PG["port"],
        portFieldType="num", database=PG["database"], databaseFieldType="str", ssl="false",
        sslFieldType="bool", applicationName="", applicationNameType="str", max="10", maxFieldType="num",
        idle="1000", idleFieldType="num", connectionTimeout="10000", connectionTimeoutFieldType="num",
        userFieldType="str", userEnv="", passwordFieldType="str", passwordEnv="",
    )
    pg["credentials"] = {"user": PG["user"], "password": PG["password"]}
    db = f.add("postgresql", 700, 80, wires=[], name="insert", query=INSERT_SQL, postgreSQLConfig="cfg.pg",
               split=False, rowsPerMsg=1, outputs=0)

    rows = []
    for proto in ("opcua", "modbus", "s7"):
        spec = DEVICES[proto]
        for name, _dt, unit, _addr in spec["datapoints"]:
            rows.append((f"{UNS_DEVICES}{name}", spec["device"], name, unit))
    meter = DEVICES["mqtt"]
    for name, _dt, unit, topic in meter["datapoints"]:
        rows.append((topic, meter["device"], name, unit))
    lines = ",\n".join(f'    "{t}": ["{d}", "{n}", "{u}"]' for t, d, n, u in rows)
    code = (
        "// topic -> [device, datapoint, unit]; one line per datapoint\n"
        f"const map = {{\n{lines}\n}};\n"
        "const m = map[msg.topic];\n"
        "if (!m) return null;\n"
        "const p = msg.payload;\n"
        'const value = (p !== null && typeof p === "object" && "value" in p) ? p.value : p;\n'
        "const ts = (p && p.ts) ? p.ts : Date.now() / 1000;\n"
        "msg.params = [ts, msg.topic, m[0], m[1], JSON.stringify(value), m[2]];\n"
        "return msg;"
    )
    fn = function_node(f, "add metadata", code, 450, 80, [[db["id"]]])
    for i, topic in enumerate([f"{UNS_PREFIX}/#", "meter1/#"]):
        f.add("mqtt in", 180, 60 + 50 * i, wires=[[fn["id"]]], name="", topic=topic, qos="0",
              datatype="auto-detect", broker="cfg.mqtt.srv", nl=False, rap=True, rh=0, inputs=0)
    return f


TABS = {"opcua": opcua_tab, "modbus": modbus_tab, "s7": s7_tab, "server": server_tab}


def all_flows() -> list[dict]:
    out = []
    for build in TABS.values():
        out.extend(build().json())
    return out


def main() -> None:
    if "--stdout" in sys.argv:
        print(json.dumps(all_flows(), indent=2, ensure_ascii=False))
        return
    flows_dir = HERE / "flows"
    flows_dir.mkdir(exist_ok=True)
    for key, build in TABS.items():
        nodes = build().json()
        for n in nodes:  # never write the DB password into an importable file
            n.pop("credentials", None)
        (flows_dir / f"{key}.json").write_text(json.dumps(nodes, indent=2, ensure_ascii=False) + "\n")
    combined = [n for n in all_flows()]
    for n in combined:
        n.pop("credentials", None)
    (flows_dir / "all.json").write_text(json.dumps(combined, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(TABS) + 1} files to {flows_dir}")


if __name__ == "__main__":
    main()
