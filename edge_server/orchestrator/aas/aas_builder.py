"""
AAS shell builder — minimal.

Builds the top-level AssetAdministrationShell: asset information with
specificAssetIds (serial number + discovered network address/hostname) and
references to the submodels that were built for this asset.
"""

from basyx.aas import model

from . import ids


class AASBuilder:
    def __init__(self, semantic_factory, element_factory):
        self.sf = semantic_factory
        self.ef = element_factory

    def build(
        self,
        system_id: str,
        *,
        serial_number: str,
        submodel_names: list,
        network: dict | None = None,
    ) -> model.AssetAdministrationShell:
        sf = self.sf

        specific_asset_ids = [
            model.SpecificAssetId(
                name="serialNumber",
                value=serial_number,
                external_subject_id=sf.SERIAL_NUMBER,
            )
        ]
        if network and network.get("ip"):
            specific_asset_ids.append(
                model.SpecificAssetId(
                    name="networkAddress",
                    value=f"{network['ip']}:{network.get('port', '')}",
                    external_subject_id=sf.NETWORK_ADDRESS,
                )
            )
        if network and network.get("hostname"):
            specific_asset_ids.append(
                model.SpecificAssetId(name="hostname", value=network["hostname"])
            )

        asset_information = model.AssetInformation(
            asset_kind=model.AssetKind.INSTANCE,
            global_asset_id=ids.asset_id(system_id),
            specific_asset_id=specific_asset_ids,
        )

        submodel_refs = {
            sf.create_submodel_reference(ids.submodel_id(system_id, name))
            for name in submodel_names
        }

        return model.AssetAdministrationShell(
            id_=ids.aas_id(system_id),
            id_short=ids.id_short(f"AAS_{system_id}"),
            asset_information=asset_information,
            submodel=submodel_refs,
        )
