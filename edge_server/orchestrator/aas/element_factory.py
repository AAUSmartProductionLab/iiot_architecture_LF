"""Helpers for creating the AAS SubmodelElements this project uses.

Adapted from the reference AAS-generation library, trimmed to the element types
actually produced here (Property, SubmodelElementCollection, MultiLanguageProperty,
ReferenceElement, RelationshipElement, Entity).
"""

from typing import Any, List, Optional

from basyx.aas import model


class AASElementFactory:
    @staticmethod
    def create_property(
        id_short: str,
        value: Any,
        value_type: type = None,
        semantic_id: Optional[model.ExternalReference] = None,
        description: Optional[str] = None,
    ) -> model.Property:
        """Create a Property (value type auto-detected when not given)."""
        if value_type is None:
            if isinstance(value, bool):
                value_type = model.datatypes.Boolean
            elif isinstance(value, int):
                value_type = model.datatypes.Int
            elif isinstance(value, float):
                value_type = model.datatypes.Double
            else:
                value_type = model.datatypes.String
                value = str(value)

        kwargs = {"id_short": id_short, "value_type": value_type, "value": value}
        if semantic_id:
            kwargs["semantic_id"] = semantic_id
        if description:
            kwargs["description"] = model.MultiLanguageTextType({"en": description})
        return model.Property(**kwargs)

    @staticmethod
    def create_collection(
        id_short: str,
        elements: List[model.SubmodelElement],
        semantic_id: Optional[model.ExternalReference] = None,
        supplemental_semantic_ids: Optional[List[model.ExternalReference]] = None,
    ) -> model.SubmodelElementCollection:
        kwargs = {"id_short": id_short, "value": elements}
        if semantic_id:
            kwargs["semantic_id"] = semantic_id
        if supplemental_semantic_ids:
            kwargs["supplemental_semantic_id"] = supplemental_semantic_ids
        return model.SubmodelElementCollection(**kwargs)

    @staticmethod
    def create_multi_language_property(
        id_short: str,
        text: str,
        language: str = "en",
        semantic_id: Optional[model.ExternalReference] = None,
    ) -> model.MultiLanguageProperty:
        kwargs = {
            "id_short": id_short,
            "value": model.MultiLanguageTextType({language: text}),
        }
        if semantic_id:
            kwargs["semantic_id"] = semantic_id
        return model.MultiLanguageProperty(**kwargs)

    @staticmethod
    def create_reference_element(
        id_short: str,
        reference: model.ModelReference,
        semantic_id: Optional[model.ExternalReference] = None,
    ) -> model.ReferenceElement:
        kwargs = {"id_short": id_short, "value": reference}
        if semantic_id:
            kwargs["semantic_id"] = semantic_id
        return model.ReferenceElement(**kwargs)

    @staticmethod
    def create_relationship(
        id_short: Optional[str],
        first: model.ModelReference,
        second: model.ModelReference,
        semantic_id: Optional[model.ExternalReference] = None,
    ) -> model.RelationshipElement:
        kwargs = {"id_short": id_short, "first": first, "second": second}
        if semantic_id:
            kwargs["semantic_id"] = semantic_id
        return model.RelationshipElement(**kwargs)

    @staticmethod
    def create_entity(
        id_short: str,
        entity_type: model.EntityType,
        global_asset_id: Optional[str] = None,
        statements: Optional[List[model.SubmodelElement]] = None,
        semantic_id: Optional[model.ExternalReference] = None,
    ) -> model.Entity:
        kwargs = {"id_short": id_short, "entity_type": entity_type}
        if global_asset_id:
            kwargs["global_asset_id"] = global_asset_id
        if statements:
            kwargs["statement"] = statements
        if semantic_id:
            kwargs["semantic_id"] = semantic_id
        return model.Entity(**kwargs)
