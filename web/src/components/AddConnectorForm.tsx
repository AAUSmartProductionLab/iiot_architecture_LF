import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { defaults, type Field, PROTOCOLS, schemaFor } from "../protocols";

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: Field;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="field">
      <label>{field.label}</label>
      {field.options ? (
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          {field.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : (
        <input
          type={field.type === "number" ? "number" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}

function coerce(fields: Field[], values: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.key];
    if (v === "" || v === undefined) continue;
    out[f.key] = f.type === "number" ? Number(v) : v;
  }
  return out;
}

export function AddConnectorForm({
  gatewayId,
  onDone,
}: {
  gatewayId: string;
  onDone: () => void;
}) {
  const [protocol, setProtocol] = useState(PROTOCOLS[0].id);
  const schema = useMemo(() => schemaFor(protocol), [protocol]);

  const [ident, setIdent] = useState({ device_id: "", manufacturer: "", model: "", serial_number: "" });
  const [dp, setDp] = useState({ name: "", datatype: "float32", unit: "", local_topic: "" });
  const [conn, setConn] = useState<Record<string, string>>(defaults(schema.connection));
  const [src, setSrc] = useState<Record<string, string>>(defaults(schema.datapoint));

  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // Reset the protocol-specific fields whenever the protocol changes.
  useEffect(() => {
    setConn(defaults(schema.connection));
    setSrc(defaults(schema.datapoint));
  }, [schema]);

  const setIdentF = (k: keyof typeof ident) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setIdent({ ...ident, [k]: e.target.value });
  const setDpF = (k: keyof typeof dp) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDp({ ...dp, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.provision({
        gateway_id: gatewayId,
        device_id: ident.device_id,
        protocol,
        manufacturer: ident.manufacturer || undefined,
        model: ident.model || undefined,
        serial_number: ident.serial_number || undefined,
        connection: coerce(schema.connection, conn),
        datapoints: [
          {
            name: dp.name,
            datatype: dp.datatype,
            unit: dp.unit,
            local_topic: dp.local_topic,
            address: coerce(schema.datapoint, src),
          },
        ],
      });
      setMsg({ kind: "ok", text: `Provisioned ${ident.device_id} (${protocol})` });
      onDone();
    } catch (err) {
      setMsg({ kind: "err", text: String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h3>Add connector (device / service)</h3>
      <form className="row" onSubmit={submit}>
        <div className="field">
          <label>Protocol</label>
          <select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
            {PROTOCOLS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Device id</label>
          <input value={ident.device_id} onChange={setIdentF("device_id")} placeholder="flow-meter-A" required />
        </div>
        <div className="field">
          <label>Manufacturer</label>
          <input value={ident.manufacturer} onChange={setIdentF("manufacturer")} />
        </div>
        <div className="field">
          <label>Model</label>
          <input value={ident.model} onChange={setIdentF("model")} />
        </div>
        <div className="field">
          <label>Serial</label>
          <input value={ident.serial_number} onChange={setIdentF("serial_number")} />
        </div>

        {/* Connection params (protocol-specific) */}
        {schema.connection.map((f) => (
          <FieldInput key={f.key} field={f} value={conn[f.key] ?? ""} onChange={(v) => setConn({ ...conn, [f.key]: v })} />
        ))}

        {/* Datapoint: common + protocol-specific source addressing */}
        <div className="field">
          <label>Datapoint name</label>
          <input value={dp.name} onChange={setDpF("name")} placeholder="flow_rate" required />
        </div>
        <div className="field">
          <label>Datatype</label>
          <input value={dp.datatype} onChange={setDpF("datatype")} />
        </div>
        <div className="field">
          <label>Unit</label>
          <input value={dp.unit} onChange={setDpF("unit")} placeholder="m3/h" />
        </div>
        <div className="field">
          <label>Local topic</label>
          <input value={dp.local_topic} onChange={setDpF("local_topic")} placeholder="devices/zone1/flow" />
        </div>
        {schema.datapoint.map((f) => (
          <FieldInput key={f.key} field={f} value={src[f.key] ?? ""} onChange={(v) => setSrc({ ...src, [f.key]: v })} />
        ))}

        <button className="primary" disabled={busy || !ident.device_id || !dp.name}>
          {busy ? "Provisioning…" : "Provision"}
        </button>
      </form>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </>
  );
}
