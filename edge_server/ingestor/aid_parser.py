"""
Extract data-plane points from a device Asset Interfaces Description submodel.

Returns one entry per MQTT datapoint:
    {device, datapoint, uns_topic, datatype, unit}

The AID is W3C-Thing-Description style: InterfaceMQTT -> InteractionMetadata ->
properties -> one collection per datapoint with key/type/unit + forms.href
(the UNS topic). Non-AID / non-MQTT submodels yield [].
"""


def _child(coll: dict, id_short: str):
    for e in (coll or {}).get("value", []):
        if e.get("idShort") == id_short:
            return e
    return None


def _prop(coll: dict, id_short: str):
    e = _child(coll, id_short)
    return e.get("value") if e else None


def _device_from_id(sm_id: str) -> str:
    # .../submodels/instances/<system_id>/AssetInterfacesDescription
    if "/instances/" in sm_id:
        return sm_id.split("/instances/")[-1].rsplit("/", 1)[0]
    return sm_id


def parse_aid(submodel: dict) -> list[dict]:
    if not submodel or submodel.get("idShort") != "AssetInterfacesDescription":
        return []
    device = _device_from_id(submodel.get("id", ""))
    out = []
    for iface in submodel.get("submodelElements", []):
        if iface.get("idShort") != "InterfaceMQTT":
            continue
        interaction = _child(iface, "InteractionMetadata")
        properties = _child(interaction, "properties") if interaction else None
        if not properties:
            continue
        for aff in properties.get("value", []):
            forms = _child(aff, "forms")
            href = _prop(forms, "href") if forms else None
            if not href:
                continue
            out.append(
                {
                    "device": device,
                    "datapoint": _prop(aff, "key") or aff.get("idShort"),
                    "uns_topic": href,
                    "datatype": _prop(aff, "type"),
                    "unit": _prop(aff, "unit"),
                }
            )
    return out
