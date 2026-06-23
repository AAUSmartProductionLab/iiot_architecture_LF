"""
Semantic ID Factory

Centralizes creation of semantic IDs and references for AAS elements.
Vendored from the reference library and trimmed to the templates this project
uses (Digital Nameplate, Asset Interfaces Description, Hierarchical Structures),
plus WoT Thing Description and MQTT protocol semantics used inside AID.

The IRIs are matched verbatim by consumers/tools; confirm against the published
IDTA PDFs before production use.
"""

from typing import List

from basyx.aas import model


class SemanticIdFactory:
    """Factory for creating semantic IDs and references."""

    # Digital Nameplate (IDTA 02006 / ZVEI)
    _DIGITAL_NAMEPLATE = "https://admin-shell.io/zvei/nameplate/2/0/Nameplate"

    # Software Nameplate (IDTA 02007)
    _SOFTWARE_NAMEPLATE = "https://admin-shell.io/idta/SoftwareNameplate/1/0/Submodel"

    # Asset Interfaces Description (IDTA 02017)
    _ASSET_INTERFACES_SUBMODEL = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Submodel"
    _ASSET_INTERFACES_INTERFACE = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/Interface"
    _ASSET_INTERFACES_INTERACTION = "https://admin-shell.io/idta/AssetInterfacesDescription/1/0/InteractionMetadata"

    # Hierarchical Structures enabling BOM (IDTA 02011)
    _HIERARCHICAL_STRUCTURES = "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel"
    _HIERARCHICAL_ARCHETYPE = "https://admin-shell.io/idta/HierarchicalStructures/ArcheType/1/0"
    _HIERARCHICAL_ENTRY_NODE = "https://admin-shell.io/idta/HierarchicalStructures/EntryNode/1/0"
    _HIERARCHICAL_NODE = "https://admin-shell.io/idta/HierarchicalStructures/Node/1/0"
    _HIERARCHICAL_RELATIONSHIP = "https://admin-shell.io/idta/HierarchicalStructures/Relationship/1/0"
    _HIERARCHICAL_SAME_AS = "https://admin-shell.io/idta/HierarchicalStructures/SameAs/1/0"

    # W3C Thing Description (used to type AID interfaces/affordances)
    _WOT_TD = "https://www.w3.org/2019/wot/td"
    _WOT_ACTION = "https://www.w3.org/2019/wot/td#ActionAffordance"
    _WOT_PROPERTY = "https://www.w3.org/2019/wot/td#PropertyAffordance"
    _WOT_INTERACTION = "https://www.w3.org/2019/wot/td#InteractionAffordance"

    # Protocols
    _MQTT_PROTOCOL = "http://www.w3.org/2011/mqtt"
    _HTTP_PROTOCOL = "http://www.w3.org/2011/http"
    _MODBUS_PROTOCOL = "https://www.w3.org/2019/wot/modbus"

    # Specific Asset IDs
    _SERIAL_NUMBER = "https://admin-shell.io/aas/3/0/SpecificAssetId/SerialNumber"
    _NETWORK_ADDRESS = "https://admin-shell.io/aas/3/0/SpecificAssetId/NetworkAddress"

    # --- ExternalReference properties ---
    @property
    def DIGITAL_NAMEPLATE(self) -> model.ExternalReference:
        return self.create_external_reference(self._DIGITAL_NAMEPLATE)

    @property
    def SOFTWARE_NAMEPLATE(self) -> model.ExternalReference:
        return self.create_external_reference(self._SOFTWARE_NAMEPLATE)

    @property
    def ASSET_INTERFACES_DESCRIPTION(self) -> model.ExternalReference:
        return self.create_external_reference(self._ASSET_INTERFACES_SUBMODEL)

    @property
    def INTERFACE(self) -> model.ExternalReference:
        return self.create_external_reference(self._ASSET_INTERFACES_INTERFACE)

    @property
    def INTERACTION_METADATA(self) -> model.ExternalReference:
        return self.create_external_reference(self._ASSET_INTERFACES_INTERACTION)

    @property
    def HIERARCHICAL_STRUCTURES(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_STRUCTURES)

    @property
    def HIERARCHICAL_ARCHETYPE(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_ARCHETYPE)

    @property
    def ENTRY_NODE(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_ENTRY_NODE)

    @property
    def HIERARCHICAL_NODE(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_NODE)

    @property
    def HIERARCHICAL_RELATIONSHIP(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_RELATIONSHIP)

    @property
    def HIERARCHICAL_SAME_AS(self) -> model.ExternalReference:
        return self.create_external_reference(self._HIERARCHICAL_SAME_AS)

    @property
    def WOT_THING_DESCRIPTION(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_TD)

    @property
    def WOT_ACTION_AFFORDANCE(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_ACTION)

    @property
    def WOT_PROPERTY_AFFORDANCE(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_PROPERTY)

    @property
    def WOT_INTERACTION_AFFORDANCE(self) -> model.ExternalReference:
        return self.create_external_reference(self._WOT_INTERACTION)

    @property
    def MQTT_PROTOCOL(self) -> model.ExternalReference:
        return self.create_external_reference(self._MQTT_PROTOCOL)

    @property
    def HTTP_PROTOCOL(self) -> model.ExternalReference:
        return self.create_external_reference(self._HTTP_PROTOCOL)

    @property
    def MODBUS_PROTOCOL(self) -> model.ExternalReference:
        return self.create_external_reference(self._MODBUS_PROTOCOL)

    @property
    def SERIAL_NUMBER(self) -> model.ExternalReference:
        return self.create_external_reference(self._SERIAL_NUMBER)

    @property
    def NETWORK_ADDRESS(self) -> model.ExternalReference:
        return self.create_external_reference(self._NETWORK_ADDRESS)

    # Map a protocol id to a binding semanticId where a standard one exists,
    # else None (the interface still carries the WoT Thing Description id).
    _PROTOCOL_IRIS = {
        "modbus": _MODBUS_PROTOCOL,
        "mqtt": _MQTT_PROTOCOL,
        "http": _HTTP_PROTOCOL,
        "opc": "https://www.w3.org/2019/wot/opcua",
    }

    def protocol_semantic(self, protocol: str):
        p = (protocol or "").lower()
        for key, iri in self._PROTOCOL_IRIS.items():
            if p.startswith(key):
                return self.create_external_reference(iri)
        return None

    # --- helpers ---
    @staticmethod
    def create_external_reference(semantic_id: str) -> model.ExternalReference:
        return model.ExternalReference(
            (model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE, value=semantic_id),)
        )

    @staticmethod
    def create_model_reference(reference_chain: List[tuple], referred_type: type) -> model.ModelReference:
        keys = tuple(
            model.Key(type_=key_type, value=value)
            for key_type, value in reference_chain
        )
        return model.ModelReference(keys, referred_type)

    @staticmethod
    def create_submodel_reference(submodel_id: str) -> model.ModelReference:
        return model.ModelReference(
            (model.Key(type_=model.KeyTypes.SUBMODEL, value=submodel_id),),
            model.Submodel,
        )
