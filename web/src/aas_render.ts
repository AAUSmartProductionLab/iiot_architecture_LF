// Parse BaSyx submodel JSON into friendly view models for the AAS Explorer.

type SME = any;

const byId = (elems: SME[] | undefined, id: string): SME | undefined =>
  (elems || []).find((e) => e.idShort === id);

const propVal = (e: SME | undefined): string =>
  e?.value !== undefined && e?.value !== null ? String(e.value) : "";

const mlpVal = (e: SME | undefined): string =>
  Array.isArray(e?.value) ? e.value[0]?.text ?? "" : propVal(e);

const submodel = (submodels: SME[], idShort: string): SME | undefined =>
  (submodels || []).find((s) => s.idShort === idShort);

const formsOf = (aff: SME): Record<string, string> => {
  const forms = byId(aff.value, "forms");
  return Object.fromEntries((forms?.value || []).map((f: SME) => [f.idShort, propVal(f)]));
};

export interface Nameplate {
  manufacturer: string;
  product: string;
  serial: string;
}
export function nameplate(submodels: SME[]): Nameplate | null {
  const sm = submodel(submodels, "Nameplate");
  if (!sm) return null;
  const els = sm.submodelElements;
  return {
    manufacturer: mlpVal(byId(els, "ManufacturerName")),
    product: mlpVal(byId(els, "ManufacturerProductDesignation")),
    serial: propVal(byId(els, "SerialNumber")),
  };
}

export interface Software {
  firmware: string;
  components: { name: string; version: string }[];
}
export function software(submodels: SME[]): Software | null {
  const sm = submodel(submodels, "SoftwareNameplate");
  if (!sm) return null;
  const els: SME[] = sm.submodelElements || [];
  return {
    firmware: propVal(byId(els, "FirmwareVersion")),
    components: els
      .filter((e) => e.idShort?.startsWith("SoftwareNameplateInstance"))
      .map((c) => ({ name: propVal(byId(c.value, "Name")), version: propVal(byId(c.value, "Version")) })),
  };
}

export interface Datapoint {
  name: string;
  type: string;
  unit: string;
  forms: Record<string, string>;
}
export interface Interface {
  idShort: string;
  protocol: string;
  title: string;
  base: string;
  datapoints: Datapoint[];
  actions: { name: string; forms: Record<string, string> }[];
}
export function interfaces(submodels: SME[]): Interface[] {
  const sm = submodel(submodels, "AssetInterfacesDescription");
  if (!sm) return [];
  return (sm.submodelElements || []).map((iface: SME) => {
    const ep = byId(iface.value, "EndpointMetadata");
    const im = byId(iface.value, "InteractionMetadata");
    const props = im ? byId(im.value, "properties") : undefined;
    const actions = im ? byId(im.value, "actions") : undefined;
    return {
      idShort: iface.idShort,
      protocol: iface.idShort.replace(/^Interface/, ""),
      title: propVal(byId(iface.value, "title")),
      base: ep ? propVal(byId(ep.value, "base")) : "",
      datapoints: (props?.value || []).map((aff: SME) => ({
        name: propVal(byId(aff.value, "key")) || aff.idShort,
        type: propVal(byId(aff.value, "type")),
        unit: propVal(byId(aff.value, "unit")),
        forms: formsOf(aff),
      })),
      actions: (actions?.value || []).map((a: SME) => ({
        name: propVal(byId(a.value, "key")) || a.idShort,
        forms: formsOf(a),
      })),
    };
  });
}

export interface Topology {
  archetype: string;
  nodes: { idShort: string; globalAssetId: string }[];
}
export function topology(submodels: SME[]): Topology | null {
  const sm = submodel(submodels, "HierarchicalStructures");
  if (!sm) return null;
  const els = sm.submodelElements;
  const entry = byId(els, "EntryNode");
  return {
    archetype: propVal(byId(els, "ArcheType")),
    nodes: (entry?.statements || [])
      .filter((s: SME) => s.modelType === "Entity")
      .map((n: SME) => ({ idShort: n.idShort, globalAssetId: n.globalAssetId || "" })),
  };
}

export function specificAssetIds(shell: SME): { name: string; value: string }[] {
  return (shell?.assetInformation?.specificAssetIds || []).map((a: SME) => ({
    name: a.name,
    value: a.value,
  }));
}
