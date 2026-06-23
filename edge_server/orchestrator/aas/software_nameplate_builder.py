"""Software Nameplate (IDTA 02007) submodel builder — minimal.

Documents firmware/software versions: a top-level FirmwareVersion plus one
SoftwareNameplateInstance collection (Name/Version) per software component.
"""

from basyx.aas import model

from . import ids


class SoftwareNameplateBuilder:
    def __init__(self, semantic_factory, element_factory):
        self.sf = semantic_factory
        self.ef = element_factory

    def build(
        self,
        system_id: str,
        *,
        firmware_version: str | None = None,
        software_components: list | None = None,
    ) -> model.Submodel:
        ef = self.ef
        elements = []
        if firmware_version:
            elements.append(
                ef.create_property(
                    "FirmwareVersion", firmware_version, value_type=model.datatypes.String
                )
            )
        for i, comp in enumerate(software_components or []):
            elements.append(
                ef.create_collection(
                    f"SoftwareNameplateInstance_{i:02d}",
                    [
                        ef.create_property("Name", comp.get("name", "")),
                        ef.create_property("Version", comp.get("version", "")),
                    ],
                )
            )
        return model.Submodel(
            id_=ids.submodel_id(system_id, "SoftwareNameplate"),
            id_short="SoftwareNameplate",
            kind=model.ModellingKind.INSTANCE,
            semantic_id=self.sf.SOFTWARE_NAMEPLATE,
            submodel_element=elements,
        )

    @staticmethod
    def has_content(firmware_version: str | None, software_components: list | None) -> bool:
        return bool(firmware_version) or bool(software_components)
