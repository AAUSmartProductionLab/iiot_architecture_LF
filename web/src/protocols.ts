// Per-protocol form schemas. Adding a protocol = adding an entry here; the
// AddConnectorForm renders the fields and the backend stores/documents them
// generically (no backend change needed for a new protocol).

export interface Field {
  key: string;
  label: string;
  default?: string;
  type?: "text" | "number";
  options?: string[];
  required?: boolean;
}

export interface ProtocolSchema {
  id: string;
  label: string;
  datatypes: string[];  // supported datatypes for this protocol
  connection: Field[];
  datapoint: Field[];
}

/** Datatypes common across all protocols. */
export const COMMON_DATATYPES = [
  "float32", "float64",
  "int16", "int32", "uint8", "uint16", "uint32",
  "real", "dint", "bytes",
  "bool", "string",
];

export const PROTOCOLS: ProtocolSchema[] = [
  {
    id: "modbus-tcp",
    label: "Modbus TCP",
    datatypes: ["float32", "float64", "int16", "int32", "uint16", "uint32"],
    connection: [
      { key: "host", label: "Host", required: true },
      { key: "port", label: "Port", default: "502", type: "number" },
      { key: "unit_id", label: "Unit ID", default: "1", type: "number" },
    ],
    datapoint: [
      { key: "register", label: "Register", default: "40001", type: "number", required: true },
      { key: "register_type", label: "Register type", default: "holding", options: ["holding", "input"] },
      { key: "quantity", label: "Quantity", default: "2", type: "number" },
    ],
  },
  {
    id: "opcua",
    label: "OPC UA",
    datatypes: ["float32", "float64", "int16", "int32", "uint8", "uint16", "uint32", "bool", "string"],
    connection: [{ key: "endpoint_url", label: "Endpoint URL", default: "opc.tcp://host:4840", required: true }],
    datapoint: [{ key: "node_id", label: "Node ID", default: "ns=2;s=", required: true }],
  },
  {
    id: "s7",
    label: "Siemens S7 (snap7)",
    datatypes: ["real", "dint", "int", "bytes", "bool"],
    connection: [
      { key: "host", label: "Host", required: true },
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
    datatypes: COMMON_DATATYPES,
    connection: [
      { key: "vendor_id", label: "Vendor ID", default: "0x0000", required: true },
      { key: "product_id", label: "Product ID", default: "0x0000", required: true },
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
