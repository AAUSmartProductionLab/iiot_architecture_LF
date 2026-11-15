"""Single source of truth for the test devices.

One simulated device per protocol, modelled on the paper's deployments (Festo
line: OPC UA + Modbus TCP; robot screwing cell: S7) plus an MQTT-native power
meter. The same definitions drive the simulators, the Node-RED baseline flows
(tests/node-red-baseline/generate_flows.py) and the data verifier,
so reference flows and verification use the same addresses and metadata.

Hosts/ports can be overridden with env vars (see each entry) so the simulators
can run on a different machine than Node-RED / the gateway.
"""

import os

INTERVAL_MS = 2000  # matches the adapters' default polling interval (2.0 s)
UNS_PREFIX = os.getenv("UNS_PREFIX", "uns/enterprise/site/area/line")

SIM_HOST = os.getenv("SIM_HOST", "127.0.0.1")
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

DEVICES = {
    "opcua": {
        "device": "festo_station1",
        "endpoint": f"opc.tcp://{SIM_HOST}:{os.getenv('OPCUA_PORT', '4840')}",
        "port": int(os.getenv("OPCUA_PORT", "4840")),
        "datapoints": [
            # name, datatype, unit, node id (namespace 2 = the simulator's own)
            ("conveyor_speed", "Double", "m/s", "ns=2;s=Station1.ConveyorSpeed"),
            ("part_count", "Int32", "pcs", "ns=2;s=Station1.PartCount"),
            ("temperature", "Double", "degC", "ns=2;s=Station1.Temperature"),
            ("air_pressure", "Double", "bar", "ns=2;s=Station1.AirPressure"),
            ("running", "Boolean", "", "ns=2;s=Station1.Running"),
        ],
    },
    "modbus": {
        "device": "festo_energy",
        "host": SIM_HOST,
        "port": int(os.getenv("MODBUS_PORT", "5020")),
        "unit_id": 1,
        "datapoints": [
            # name, datatype, unit, holding-register address (0-based; float32 = 2 registers)
            ("motor_current", "float32", "A", 0),
            ("voltage", "float32", "V", 2),
            ("active_power", "float32", "kW", 4),
            ("energy", "float32", "kWh", 6),
            ("frequency", "float32", "Hz", 8),
        ],
    },
    "s7": {
        "device": "screwing_cell",
        "host": SIM_HOST,
        "port": int(os.getenv("S7_PORT", "102")),
        "rack": 0,
        "slot": 1,
        "db": 1,
        "datapoints": [
            # name, datatype, unit, start byte in DB1
            ("torque", "REAL", "Nm", 0),
            ("angle", "REAL", "deg", 4),
            ("screw_count", "DINT", "pcs", 8),
            ("cycle_time", "REAL", "s", 12),
            ("spindle_speed", "REAL", "rpm", 16),
        ],
    },
    "mqtt": {
        "device": "power_meter",
        "datapoints": [
            # name, datatype, unit, the meter's own topic (payload: bare JSON number)
            ("l1_current", "float", "A", "meter1/l1/current"),
            ("l2_current", "float", "A", "meter1/l2/current"),
            ("l3_current", "float", "A", "meter1/l3/current"),
            ("total_power", "float", "kW", "meter1/power"),
            ("power_factor", "float", "", "meter1/pf"),
        ],
    },
}


def uns_topic(name: str) -> str:
    """The UNS topic a datapoint ends up on (same mapping as the gateway bridge)."""
    return f"{UNS_PREFIX}/devices/{name}"
