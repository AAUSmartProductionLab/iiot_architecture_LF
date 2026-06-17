"""Registration service — the single hub that turns inputs into AAS.

Inputs: a discovered gateway manifest + network info (register_gateway), or a Web
UI device config (provision_device, which forwards to the gateway then re-syncs).
The manifest's `configured_connectors` is the source of truth; register_gateway
idempotently rebuilds the gateway AAS (incl. topology) and each device's AAS.
"""

import logging

import httpx

from . import config
from .aas import ids
from .aas.aas_builder import AASBuilder
from .aas.asset_interfaces_builder import AssetInterfacesBuilder
from .aas.digital_nameplate_builder import DigitalNameplateBuilder
from .aas.element_factory import AASElementFactory
from .aas.hierarchical_structures_builder import HierarchicalStructuresBuilder
from .aas.semantic_ids import SemanticIdFactory
from .aas.software_nameplate_builder import SoftwareNameplateBuilder
from .basyx_client import upsert_shell, upsert_submodel

log = logging.getLogger("registration")


def _uns_topic(local_topic: str, uns_prefix: str) -> str:
    """Mirror the HiveMQ bridge remap exactly.

    The bridge filter `devices/#` -> destination `<uns_prefix>/{#}` substitutes
    the FULL local topic for {#}, so `devices/line1/temp` becomes
    `<uns_prefix>/devices/line1/temp` (the `devices/` segment is kept).
    """
    if not local_topic:
        return ""
    return f"{uns_prefix}/{local_topic}" if uns_prefix else local_topic


class RegistrationService:
    def __init__(self) -> None:
        sf = SemanticIdFactory()
        ef = AASElementFactory
        self.nameplate = DigitalNameplateBuilder(sf, ef)
        self.software = SoftwareNameplateBuilder(sf, ef)
        self.aid = AssetInterfacesBuilder(sf, ef)
        self.hs = HierarchicalStructuresBuilder(sf, ef)
        self.shell = AASBuilder(sf, ef)

    @staticmethod
    def _gateway_mqtt(manifest: dict) -> dict:
        m = manifest.get("mqtt", {})
        b = manifest.get("bridge", {})
        return {
            "broker_host": m.get("local_broker_host", ""),
            "broker_port": m.get("local_broker_port", ""),
            "base_topic": m.get("local_base_topic", ""),
            "uns_prefix": b.get("uns_prefix", ""),
        }

    def _enrich_datapoints(self, datapoints: list, mqtt: dict) -> list:
        out = []
        for dp in datapoints or []:
            dp = dict(dp)
            dp.setdefault(
                "uns_topic",
                _uns_topic(dp.get("local_topic", ""), mqtt["uns_prefix"]),
            )
            out.append(dp)
        return out

    def _build_device(self, gateway_serial: str, connector: dict, mqtt: dict):
        gsys = ids.gateway_system_id(gateway_serial)
        device_key = connector.get("device_key") or connector.get("device_id")
        dsys = ids.device_system_id(gateway_serial, device_key)
        datapoints = self._enrich_datapoints(connector.get("datapoints", []), mqtt)

        # Optional real-world identity supplied via the Web UI / provision payload.
        serial_number = connector.get("serial_number") or device_key
        product_designation = (
            connector.get("model") or connector.get("device_id") or device_key
        )

        nameplate = self.nameplate.build(
            dsys,
            manufacturer=connector.get("manufacturer", "Unknown"),
            product_designation=product_designation,
            serial_number=serial_number,
        )
        aid = self.aid.build_device(
            dsys,
            datapoints=datapoints,
            mqtt=mqtt,
            protocol=connector.get("protocol", ""),
            connection=connector.get("connection", {}),
        )
        hs = self.hs.build_device(
            dsys,
            device_global_asset_id=ids.asset_id(dsys),
            gateway_system_id=gsys,
            gateway_global_asset_id=ids.asset_id(gsys),
        )
        submodels = [nameplate, aid, hs]
        submodel_names = ["Nameplate", "AssetInterfacesDescription", "HierarchicalStructures"]

        # Software Nameplate only if the device actually reports SW/firmware.
        fw = connector.get("firmware_version")
        sw = connector.get("software_components")
        if self.software.has_content(fw, sw):
            submodels.append(
                self.software.build(dsys, firmware_version=fw, software_components=sw)
            )
            submodel_names.append("SoftwareNameplate")

        shell = self.shell.build(
            dsys,
            serial_number=serial_number,
            submodel_names=submodel_names,
            network=None,
        )
        return submodels, shell

    async def register_gateway(self, manifest: dict, network: dict | None = None) -> dict:
        """Build + upsert the gateway AAS and each connected device's AAS."""
        serial = manifest["serial_number"]
        gsys = ids.gateway_system_id(serial)
        mqtt = self._gateway_mqtt(manifest)
        connectors = manifest.get("configured_connectors", [])

        devices_for_hs = []
        device_objs = []
        for c in connectors:
            device_key = c.get("device_key") or c.get("device_id")
            dsys = ids.device_system_id(serial, device_key)
            devices_for_hs.append(
                {
                    "id_short": ids.id_short(device_key),
                    "global_asset_id": ids.asset_id(dsys),
                    "system_id": dsys,
                }
            )
            device_objs.append(self._build_device(serial, c, mqtt))

        nameplate = self.nameplate.build(
            gsys,
            manufacturer=manifest.get("manufacturer", ""),
            product_designation=manifest.get("hardware_model", ""),
            serial_number=serial,
        )
        software = self.software.build(
            gsys,
            firmware_version=manifest.get("firmware_version"),
            software_components=manifest.get("software_components"),
        )
        aid = self.aid.build_gateway(gsys, network=network or {})
        hs = self.hs.build_gateway(
            gsys, gateway_global_asset_id=ids.asset_id(gsys), devices=devices_for_hs
        )
        shell = self.shell.build(
            gsys,
            serial_number=serial,
            submodel_names=[
                "Nameplate",
                "SoftwareNameplate",
                "AssetInterfacesDescription",
                "HierarchicalStructures",
            ],
            network=network,
        )

        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            for sm in (nameplate, software, aid, hs):
                await upsert_submodel(client, sm)
            await upsert_shell(client, shell)
            for sms, dshell in device_objs:
                for sm in sms:
                    await upsert_submodel(client, sm)
                await upsert_shell(client, dshell)

        log.info("registered gateway serial=%s (%d devices)", serial, len(connectors))
        return {
            "gateway_aas_id": ids.aas_id(gsys),
            "device_aas_ids": [
                ids.aas_id(ids.device_system_id(serial, c.get("device_key") or c.get("device_id")))
                for c in connectors
            ],
        }

    async def provision_device(self, gateway_record: dict, device_config: dict) -> dict:
        """Forward a Web UI device config to the gateway, then re-sync the AAS.

        gateway_record: the in-memory registry record (ip/port/manifest/...).
        device_config:  simple shape {device_id, protocol, address, datapoints[]}.
        """
        ip, port = gateway_record.get("ip"), gateway_record.get("port")
        if not ip or not port:
            raise ValueError("gateway has no reachable address")

        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
            r = await client.post(f"http://{ip}:{port}/api/connectors", json=device_config)
            r.raise_for_status()
            # Re-fetch the manifest so configured_connectors is authoritative.
            m = await client.get(f"http://{ip}:{port}/api/manifest")
            m.raise_for_status()
            manifest = m.json()

        network = {
            "ip": ip,
            "port": port,
            "hostname": gateway_record.get("hostname"),
            "gateway_id": gateway_record.get("gateway_id"),
        }
        result = await self.register_gateway(manifest, network)
        # Keep the registry's cached manifest in sync (so /api/devices is current).
        gateway_record["manifest"] = manifest
        gateway_record["device_count"] = len(manifest.get("configured_connectors", []))
        result["connector"] = r.json()
        return result


registration_service = RegistrationService()
