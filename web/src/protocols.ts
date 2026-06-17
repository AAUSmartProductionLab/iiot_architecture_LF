// Per-protocol form schemas. Adding a protocol = adding an entry here; the
// AddConnectorForm renders the fields and the backend stores/documents them
// generically (no backend change needed for a new protocol).

export interface Field {
  key: string;
  label: string;
  default?: string;
  type?: "text" | "number";
  options?: string[];
}

export interface ProtocolSchema {
  id: string;
  label: string;
  connection: Field[]; // connector-level connection params
  datapoint: Field[]; // per-datapoint source addressing (sent as datapoint.address)
}

export const PROTOCOLS: ProtocolSchema[] = [
  {
    id: "modbus-tcp",
    label: "Modbus TCP",
    connection: [
      { key: "host", label: "Host" },
      { key: "port", label: "Port", default: "502", type: "number" },
      { key: "unit_id", label: "Unit ID", default: "1", type: "number" },
    ],
    datapoint: [
      { key: "register", label: "Register", default: "40001", type: "number" },
      { key: "register_type", label: "Register type", default: "holding", options: ["holding", "input"] },
      { key: "quantity", label: "Quantity", default: "2", type: "number" },
    ],
  },
  {
    id: "opcua",
    label: "OPC UA",
    connection: [{ key: "endpoint_url", label: "Endpoint URL", default: "opc.tcp://host:4840" }],
    datapoint: [{ key: "node_id", label: "Node ID", default: "ns=2;s=" }],
  },
  {
    id: "s7",
    label: "Siemens S7 (snap7)",
    connection: [
      { key: "host", label: "Host" },
      { key: "rack", label: "Rack", default: "0", type: "number" },
      { key: "slot", label: "Slot", default: "1", type: "number" },
    ],
    datapoint: [
      { key: "area", label: "Area", default: "DB", options: ["DB", "MK", "PE", "PA"] },
      { key: "db_number", label: "DB number", default: "1", type: "number" },
      { key: "start", label: "Start byte", default: "0", type: "number" },
      { key: "size", label: "Size (bytes)", default: "4", type: "number" },
    ],
  },
  {
    id: "usb",
    label: "USB HID",
    connection: [
      { key: "vendor_id", label: "Vendor ID", default: "0x0000" },
      { key: "product_id", label: "Product ID", default: "0x0000" },
    ],
    datapoint: [
      { key: "report_id", label: "Report ID", default: "0", type: "number" },
      { key: "offset", label: "Byte offset", default: "0", type: "number" },
      { key: "length", label: "Length", default: "2", type: "number" },
    ],
  },
];

export function schemaFor(id: string): ProtocolSchema {
  return PROTOCOLS.find((p) => p.id === id) ?? PROTOCOLS[0];
}

export function defaults(fields: Field[]): Record<string, string> {
  return Object.fromEntries(fields.map((f) => [f.key, f.default ?? ""]));
}
