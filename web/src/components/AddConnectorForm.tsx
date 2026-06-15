import { useState } from "react";
import { api } from "../api";

export function AddConnectorForm({
  gatewayId,
  onDone,
}: {
  gatewayId: string;
  onDone: () => void;
}) {
  const [f, setF] = useState({
    device_id: "",
    manufacturer: "",
    model: "",
    serial_number: "",
    unit_id: "1",
    register: "40001",
    register_type: "holding",
    quantity: "2",
    dp_name: "",
    datatype: "float32",
    unit: "",
    local_topic: "",
  });
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.provision({
        gateway_id: gatewayId,
        device_id: f.device_id,
        protocol: "modbus-tcp",
        manufacturer: f.manufacturer || undefined,
        model: f.model || undefined,
        serial_number: f.serial_number || undefined,
        address: {
          unit_id: Number(f.unit_id),
          register: Number(f.register),
          register_type: f.register_type,
          quantity: Number(f.quantity),
        },
        datapoints: [
          {
            name: f.dp_name,
            datatype: f.datatype,
            unit: f.unit,
            local_topic: f.local_topic,
          },
        ],
      });
      setMsg({ kind: "ok", text: `Provisioned ${f.device_id}` });
      onDone();
    } catch (err) {
      setMsg({ kind: "err", text: String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h3>Add connector (device/service)</h3>
      <form className="row" onSubmit={submit}>
        <div className="field">
          <label>Device id</label>
          <input value={f.device_id} onChange={set("device_id")} placeholder="flow-meter-A" required />
        </div>
        <div className="field">
          <label>Manufacturer</label>
          <input value={f.manufacturer} onChange={set("manufacturer")} placeholder="Acme" />
        </div>
        <div className="field">
          <label>Model</label>
          <input value={f.model} onChange={set("model")} placeholder="FM-200" />
        </div>
        <div className="field">
          <label>Serial</label>
          <input value={f.serial_number} onChange={set("serial_number")} placeholder="FM200-123" />
        </div>
        <div className="field">
          <label>Unit id</label>
          <input value={f.unit_id} onChange={set("unit_id")} />
        </div>
        <div className="field">
          <label>Register</label>
          <input value={f.register} onChange={set("register")} />
        </div>
        <div className="field">
          <label>Register type</label>
          <select value={f.register_type} onChange={set("register_type")}>
            <option value="holding">holding</option>
            <option value="input">input</option>
          </select>
        </div>
        <div className="field">
          <label>Quantity</label>
          <input value={f.quantity} onChange={set("quantity")} />
        </div>
        <div className="field">
          <label>Datapoint name</label>
          <input value={f.dp_name} onChange={set("dp_name")} placeholder="flow_rate" required />
        </div>
        <div className="field">
          <label>Datatype</label>
          <input value={f.datatype} onChange={set("datatype")} />
        </div>
        <div className="field">
          <label>Unit</label>
          <input value={f.unit} onChange={set("unit")} placeholder="m3/h" />
        </div>
        <div className="field">
          <label>Local topic</label>
          <input value={f.local_topic} onChange={set("local_topic")} placeholder="devices/zone1/flow" />
        </div>
        <button className="primary" disabled={busy || !f.device_id || !f.dp_name}>
          {busy ? "Provisioning…" : "Provision"}
        </button>
      </form>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </>
  );
}
