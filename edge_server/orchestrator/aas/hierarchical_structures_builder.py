"""
Hierarchical Structures enabling BOM (IDTA 02011) submodel builder — minimal.

Bidirectional topology:
  - Gateway (OneDown): EntryNode = gateway; one child Node per device, each with
    a HasPart relationship and a SameAs reference into the device's own
    HierarchicalStructures EntryNode (enables 'jump' navigation in aas-gui).
  - Device (OneUp): EntryNode = device; a Node for the parent gateway with a
    SameAs reference back to the gateway EntryNode, plus an IsPartOf relationship.
"""

from basyx.aas import model

from . import ids


class HierarchicalStructuresBuilder:
    def __init__(self, semantic_factory, element_factory):
        self.sf = semantic_factory
        self.ef = element_factory

    def _same_as(self, target_hs_submodel_id: str):
        """ReferenceElement pointing at the EntryNode of another HS submodel."""
        ref = self.sf.create_model_reference(
            [
                (model.KeyTypes.SUBMODEL, target_hs_submodel_id),
                (model.KeyTypes.ENTITY, "EntryNode"),
            ],
            model.Entity,
        )
        return self.ef.create_reference_element(
            id_short="SameAs",
            reference=ref,
            semantic_id=self.sf.HIERARCHICAL_SAME_AS,
        )

    def _relationship(self, id_short: str, sm_id: str, child_id_short: str):
        """HasPart/IsPartOf relationship: EntryNode -> child Node (AASd-125)."""
        first = self.sf.create_model_reference(
            [(model.KeyTypes.SUBMODEL, sm_id), (model.KeyTypes.ENTITY, "EntryNode")],
            model.Entity,
        )
        second = self.sf.create_model_reference(
            [
                (model.KeyTypes.SUBMODEL, sm_id),
                (model.KeyTypes.ENTITY, "EntryNode"),
                (model.KeyTypes.ENTITY, child_id_short),
            ],
            model.Entity,
        )
        return self.ef.create_relationship(
            id_short=id_short,
            first=first,
            second=second,
            semantic_id=self.sf.HIERARCHICAL_RELATIONSHIP,
        )

    def build_gateway(
        self,
        system_id: str,
        *,
        gateway_global_asset_id: str,
        devices: list,
    ) -> model.Submodel:
        """devices: list of {"id_short", "global_asset_id", "system_id"}."""
        sf, ef = self.sf, self.ef
        sm_id = ids.submodel_id(system_id, "HierarchicalStructures")

        archetype = ef.create_property(
            "ArcheType", "OneDown",
            value_type=model.datatypes.String,
            semantic_id=sf.HIERARCHICAL_ARCHETYPE,
        )

        statements = []
        for dev in devices:
            node_id_short = ids.id_short(dev["id_short"])
            device_hs_id = ids.submodel_id(dev["system_id"], "HierarchicalStructures")
            statements.append(
                ef.create_entity(
                    id_short=node_id_short,
                    entity_type=model.EntityType.SELF_MANAGED_ENTITY,
                    global_asset_id=dev.get("global_asset_id"),
                    statements=[self._same_as(device_hs_id)],
                    semantic_id=sf.HIERARCHICAL_NODE,
                )
            )
            statements.append(
                self._relationship(f"HasPart_{node_id_short}", sm_id, node_id_short)
            )

        entry = ef.create_entity(
            id_short="EntryNode",
            entity_type=model.EntityType.SELF_MANAGED_ENTITY,
            global_asset_id=gateway_global_asset_id,
            statements=statements or None,
            semantic_id=sf.ENTRY_NODE,
        )
        return model.Submodel(
            id_=sm_id,
            id_short="HierarchicalStructures",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=sf.HIERARCHICAL_STRUCTURES,
            submodel_element=[archetype, entry],
        )

    def build_device(
        self,
        system_id: str,
        *,
        device_global_asset_id: str,
        gateway_system_id: str,
        gateway_global_asset_id: str,
    ) -> model.Submodel:
        sf, ef = self.sf, self.ef
        sm_id = ids.submodel_id(system_id, "HierarchicalStructures")
        gateway_hs_id = ids.submodel_id(gateway_system_id, "HierarchicalStructures")
        gw_node_id_short = ids.id_short(gateway_system_id)

        archetype = ef.create_property(
            "ArcheType", "OneUp",
            value_type=model.datatypes.String,
            semantic_id=sf.HIERARCHICAL_ARCHETYPE,
        )

        gateway_node = ef.create_entity(
            id_short=gw_node_id_short,
            entity_type=model.EntityType.SELF_MANAGED_ENTITY,
            global_asset_id=gateway_global_asset_id,
            statements=[self._same_as(gateway_hs_id)],
            semantic_id=sf.HIERARCHICAL_NODE,
        )
        relationship = self._relationship(
            f"IsPartOf_{gw_node_id_short}", sm_id, gw_node_id_short
        )

        entry = ef.create_entity(
            id_short="EntryNode",
            entity_type=model.EntityType.SELF_MANAGED_ENTITY,
            global_asset_id=device_global_asset_id,
            statements=[gateway_node, relationship],
            semantic_id=sf.ENTRY_NODE,
        )
        return model.Submodel(
            id_=sm_id,
            id_short="HierarchicalStructures",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=sf.HIERARCHICAL_STRUCTURES,
            submodel_element=[archetype, entry],
        )
