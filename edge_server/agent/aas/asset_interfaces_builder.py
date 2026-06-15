"""
Asset Interfaces Description (IDTA 02017) submodel builder — minimal.

Interfaces are modelled W3C Thing Description style (Interface* collection with
EndpointMetadata + InteractionMetadata.properties/actions, each affordance
carrying protocol-specific `forms`). All static documentation — never values.

  - Gateway AID  -> the gateway's REST management interface (FastAPI endpoints).
  - Device  AID  -> the device-specific source protocol (e.g. Modbus, with
                    register addresses) AND the MQTT interface (the topic from
                    which the published data can be read).
"""

from basyx.aas import model

from . import ids

# The gateway's REST API surface (GET -> properties, POST -> actions).
DEFAULT_REST_ENDPOINTS = [
    {"name": "manifest", "path": "/api/manifest", "method": "GET"},
    {"name": "health", "path": "/api/health", "method": "GET"},
    {"name": "configure", "path": "/api/configure", "method": "POST"},
    {"name": "connectors", "path": "/api/connectors", "method": "POST"},
]


class AssetInterfacesBuilder:
    def __init__(self, semantic_factory, element_factory):
        self.sf = semantic_factory
        self.ef = element_factory

    def _endpoint(self, base: str, content_type: str = "application/json"):
        return self.ef.create_collection(
            "EndpointMetadata",
            [
                self.ef.create_property("base", base),
                self.ef.create_property("contentType", content_type),
            ],
        )

    def _forms(self, items: list):
        return self.ef.create_collection(
            "forms", [self.ef.create_property(k, v) for k, v in items]
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
                    self._forms(
                        [("href", ep["path"]), ("htv_methodName", ep["method"])]
                    ),
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
                ef.create_collection(
                    "actions", actions, semantic_id=sf.WOT_ACTION_AFFORDANCE
                )
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
                self._endpoint(base),
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

    # --- device: source protocol + MQTT -------------------------------------

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

    def _wrap_interface(self, id_short, title, base, content_type, props, proto_ref):
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
        return ef.create_collection(
            id_short,
            [
                ef.create_property("title", title),
                self._endpoint(base, content_type),
                interaction,
            ],
            semantic_id=sf.INTERFACE,
            supplemental_semantic_ids=[proto_ref, sf.WOT_THING_DESCRIPTION],
        )

    def _modbus_interface(self, datapoints: list, address: dict):
        host = (address or {}).get("host", "")
        port = (address or {}).get("port", 502)
        base = f"modbus+tcp://{host}:{port}" if host else "modbus+tcp://"
        props = []
        for dp in datapoints:
            a = dp.get("address") or address or {}
            forms = self._forms(
                [
                    ("href", f"{base}/{a.get('unit_id', '')}"),
                    ("modbus_function", a.get("register_type", "holding")),
                    ("modbus_address", a.get("register", "")),
                    ("modbus_quantity", a.get("quantity", "")),
                ]
            )
            props.append(self._property_affordance(dp, forms))
        return self._wrap_interface(
            "InterfaceModbus",
            "Device source (Modbus)",
            base,
            "application/octet-stream",
            props,
            self.sf.MODBUS_PROTOCOL,
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
        return self._wrap_interface(
            "InterfaceMQTT",
            "Device data (MQTT)",
            base,
            "application/json",
            props,
            self.sf.MQTT_PROTOCOL,
        )

    def build_device(
        self, system_id: str, *, datapoints: list, mqtt: dict, protocol: str, address: dict
    ) -> model.Submodel:
        interfaces = []
        if protocol and protocol.startswith("modbus"):
            interfaces.append(self._modbus_interface(datapoints, address))
        interfaces.append(self._mqtt_interface(datapoints, mqtt))
        return model.Submodel(
            id_=ids.submodel_id(system_id, "AssetInterfacesDescription"),
            id_short="AssetInterfacesDescription",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.sf.ASSET_INTERFACES_DESCRIPTION,
            submodel_element=interfaces,
        )
