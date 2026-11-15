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
  /** Short help text shown under the input. */
  hint?: string;
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
    // The register count is derived from the datatype (float32/int32 = 2, float64 = 4, ...).
    datatypes: ["float32", "float64", "int16", "uint16", "int32", "uint32", "int64", "uint64", "bool"],
    connection: [
      { key: "host", label: "Host", required: true },
      { key: "port", label: "Port", default: "502", type: "number" },
      { key: "unit_id", label: "Unit ID", default: "1", type: "number" },
    ],
    datapoint: [
      {
        key: "register", label: "Register address", default: "0", type: "number", required: true,
        hint: "0-based. Modicon 40001 = holding 0, 30001 = input 0",
      },
      {
        key: "register_type", label: "Register type", default: "holding",
        options: ["holding", "input", "coil", "discrete"],
        hint: "coil / discrete hold bits: use datatype bool",
      },
      {
        key: "word_order", label: "Word order", default: "big", options: ["big", "little"],
        hint: "little = word-swapped 32/64-bit values (common on meters)",
      },
    ],
  },
  {
    id: "opcua",
    label: "OPC UA",
    datatypes: ["float32", "float64", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64", "bool", "string"],
    connection: [{ key: "endpoint_url", label: "Endpoint URL", default: "opc.tcp://host:4840", required: true }],
    datapoint: [{ key: "node_id", label: "Node ID", default: "ns=2;s=", required: true }],
  },
  {
    id: "s7",
    label: "Siemens S7 (snap7)",
    datatypes: ["real", "lreal", "int", "uint", "dint", "udint", "sint", "usint", "word", "dword", "bool", "bytes"],
    connection: [
      { key: "host", label: "Host", required: true },
      { key: "rack", label: "Rack", default: "0", type: "number" },
      { key: "slot", label: "Slot", default: "1", type: "number" },
    ],
    datapoint: [
      { key: "area", label: "Area", default: "DB", options: ["DB", "MK", "PE", "PA"], hint: "DB, markers (M), inputs (I/PE), outputs (Q/PA)" },
      { key: "db_number", label: "DB number", default: "1", type: "number", hint: "Only used for area DB" },
      { key: "start", label: "Start byte", default: "0", type: "number" },
      { key: "bit", label: "Bit", default: "0", type: "number", hint: "0-7, only used for bool" },
      { key: "size", label: "Size (bytes)", default: "0", type: "number", hint: "Only used for bytes; other types have a fixed size" },
    ],
  },
];

export function schemaFor(id: string): ProtocolSchema {
  return PROTOCOLS.find((p) => p.id === id) ?? PROTOCOLS[0];
}

export function defaults(fields: Field[]): Record<string, string> {
  return Object.fromEntries(fields.map((f) => [f.key, f.default ?? ""]));
}
