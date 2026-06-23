"""
Asset Interfaces Description (IDTA 02017) submodel builder — minimal.

Interfaces are modelled W3C Thing Description style (Interface* collection with
EndpointMetadata + InteractionMetadata.properties, each affordance carrying
protocol-specific `forms`). All static documentation — never values.

  - Gateway AID -> the gateway's REST management interface (FastAPI endpoints).
  - Device  AID -> a generic source interface for whatever protocol the device
                   uses (Modbus, OPC UA, S7/snap7, USB, …) AND the MQTT interface
                   (the topic from which the published data can be read).

The source interface is data-driven: it renders whatever `connection` fields and
per-datapoint `address` fields are supplied, so new protocols need no code here.
"""

import re

from basyx.aas import model

from . import ids

DEFAULT_REST_ENDPOINTS = [
    {"name": "manifest", "path": "/api/manifest", "method": "GET"},
    {"name": "health", "path": "/api/health", "method": "GET"},
    {"name": "configure", "path": "/api/configure", "method": "POST"},
    {"name": "connectors", "path": "/api/connectors", "method": "POST"},
]


def _pascal(text: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", str(text))
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Generic"


def _protocol_base(protocol: str, conn: dict) -> str:
    """Best-effort connection URI for the protocol (documentation only)."""
    p = (protocol or "").lower()
    host = conn.get("host", "")
    if p.startswith("modbus"):
        return f"modbus+tcp://{host}:{conn.get('port', 502)}"
    if p.startswith("opc"):
        return conn.get("endpoint_url") or f"opc.tcp://{host}:{conn.get('port', 4840)}"
    if p in ("s7", "snap7"):
        return f"s7://{host}/{conn.get('rack', 0)}/{conn.get('slot', 1)}"
    if p == "usb":
        return f"usb://{conn.get('vendor_id', '')}:{conn.get('product_id', '')}"
    return f"{p}://{host}" if host else f"{p}://"


class AssetInterfacesBuilder:
    def __init__(self, semantic_factory, element_factory):
        self.sf = semantic_factory
        self.ef = element_factory

    def _endpoint(self, base: str, content_type: str, extra: dict | None = None):
        items = [
            self.ef.create_property("base", base),
            self.ef.create_property("contentType", content_type),
        ]
        for k, v in (extra or {}).items():
            items.append(self.ef.create_property(ids.id_short(k), v))
        return self.ef.create_collection("EndpointMetadata", items)

    def _forms(self, items: list):
        return self.ef.create_collection(
            "forms",
            [self.ef.create_property(ids.id_short(k), v) for k, v in items if v is not None],
        )

    def _property_affordance(self, dp: dict, forms):
        ef = self.ef
        return ef.create_collection(
            ids.id_short(dp.get("name", "datapoint")),
            [
                ef.create_property("key", dp.get("name", "")),
                ef.create_property("title", dp.get("description") or dp.get("name", "")),
                ef.create_property("type", dp.get("datatype", "")),
                ef.create_property("unit", dp.get("unit", "")),
                forms,
            ],
            semantic_id=self.sf.WOT_PROPERTY_AFFORDANCE,
        )

    def _interface(self, id_short, title, base, content_type, endpoint_extra, props, proto_ref):
        ef, sf = self.ef, self.sf
        properties = ef.create_collection(
            "properties", props, semantic_id=sf.WOT_PROPERTY_AFFORDANCE
        )
        interaction = ef.create_collection(
            "InteractionMetadata",
            [properties],
            semantic_id=sf.INTERACTION_METADATA,
            supplemental_semantic_ids=[sf.WOT_INTERACTION_AFFORDANCE],
        )
        supplemental = [sf.WOT_THING_DESCRIPTION]
        if proto_ref is not None:
            supplemental.insert(0, proto_ref)
        return ef.create_collection(
            id_short,
            [
                ef.create_property("title", title),
                self._endpoint(base, content_type, endpoint_extra),
                interaction,
            ],
            semantic_id=sf.INTERFACE,
            supplemental_semantic_ids=supplemental,
        )

    # --- gateway: REST management interface ---------------------------------

    def build_gateway(
        self, system_id: str, *, network: dict, endpoints: list | None = None
    ) -> model.Submodel:
        sf, ef = self.sf, self.ef
        endpoints = endpoints or DEFAULT_REST_ENDPOINTS
        base = ""
        if network and network.get("ip"):
            base = f"http://{network['ip']}:{network.get('port', '')}"

        read_props, actions = [], []
        for ep in endpoints:
            affordance = ef.create_collection(
                ids.id_short(ep["name"]),
                [
                    ef.create_property("key", ep["name"]),
                    self._forms([("href", ep["path"]), ("htv_methodName", ep["method"])]),
                ],
                semantic_id=(
                    sf.WOT_PROPERTY_AFFORDANCE
                    if ep["method"] == "GET"
                    else sf.WOT_ACTION_AFFORDANCE
                ),
            )
            (read_props if ep["method"] == "GET" else actions).append(affordance)

        interaction_children = []
        if read_props:
            interaction_children.append(
                ef.create_collection(
                    "properties", read_props, semantic_id=sf.WOT_PROPERTY_AFFORDANCE
                )
            )
        if actions:
            interaction_children.append(
                ef.create_collection("actions", actions, semantic_id=sf.WOT_ACTION_AFFORDANCE)
            )
        interaction = ef.create_collection(
            "InteractionMetadata",
            interaction_children,
            semantic_id=sf.INTERACTION_METADATA,
            supplemental_semantic_ids=[sf.WOT_INTERACTION_AFFORDANCE],
        )
        rest_iface = ef.create_collection(
            "InterfaceHTTP",
            [
                ef.create_property("title", "Edge Gateway REST API"),
                self._endpoint(base, "application/json"),
                interaction,
            ],
            semantic_id=sf.INTERFACE,
            supplemental_semantic_ids=[sf.HTTP_PROTOCOL, sf.WOT_THING_DESCRIPTION],
        )
        return model.Submodel(
            id_=ids.submodel_id(system_id, "AssetInterfacesDescription"),
            id_short="AssetInterfacesDescription",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=sf.ASSET_INTERFACES_DESCRIPTION,
            submodel_element=[rest_iface],
        )

    # --- device: generic source protocol + MQTT -----------------------------

    def _source_interface(self, protocol: str, connection: dict, datapoints: list):
        base = _protocol_base(protocol, connection)
        props = []
        for dp in datapoints:
            src = dp.get("address") or {}
            items = [("href", base)] + [(k, v) for k, v in src.items()]
            props.append(self._property_affordance(dp, self._forms(items)))
        return self._interface(
            f"Interface{_pascal(protocol)}",
            f"Device source ({protocol})",
            base,
            "application/octet-stream",
            connection,
            props,
            self.sf.protocol_semantic(protocol),
        )

    def _mqtt_interface(self, datapoints: list, mqtt: dict):
        base = f"mqtt://{mqtt.get('broker_host', '')}:{mqtt.get('broker_port', '')}"
        props = []
        for dp in datapoints:
            forms = self._forms(
                [
                    ("href", dp.get("uns_topic") or dp.get("local_topic") or ""),
                    ("contentType", "application/json"),
                    ("mqtt_topic", dp.get("local_topic", "")),
                ]
            )
            props.append(self._property_affordance(dp, forms))
        return self._interface(
            "InterfaceMQTT",
            "Device data (MQTT)",
            base,
            "application/json",
            None,
            props,
            self.sf.MQTT_PROTOCOL,
        )

    def build_device(
        self, system_id: str, *, datapoints: list, mqtt: dict, protocol: str, connection: dict
    ) -> model.Submodel:
        interfaces = [
            self._source_interface(protocol, connection, datapoints),
            self._mqtt_interface(datapoints, mqtt),
        ]
        return model.Submodel(
            id_=ids.submodel_id(system_id, "AssetInterfacesDescription"),
            id_short="AssetInterfacesDescription",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.sf.ASSET_INTERFACES_DESCRIPTION,
            submodel_element=interfaces,
        )
