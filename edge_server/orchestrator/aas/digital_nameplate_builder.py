"""Digital Nameplate (IDTA 02006) submodel builder — minimal."""

from basyx.aas import model

from . import ids


class DigitalNameplateBuilder:
    def __init__(self, semantic_factory, element_factory):
        self.sf = semantic_factory
        self.ef = element_factory

    def build(
        self,
        system_id: str,
        *,
        manufacturer: str,
        product_designation: str,
        serial_number: str,
    ) -> model.Submodel:
        ef = self.ef
        elements = [
            ef.create_multi_language_property(
                "ManufacturerName", manufacturer or "Unknown"
            ),
            ef.create_multi_language_property(
                "ManufacturerProductDesignation", product_designation or "Unknown"
            ),
            ef.create_property(
                "SerialNumber", serial_number, value_type=model.datatypes.String
            ),
        ]
        return model.Submodel(
            id_=ids.submodel_id(system_id, "Nameplate"),
            id_short="Nameplate",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.sf.DIGITAL_NAMEPLATE,
            submodel_element=elements,
        )
