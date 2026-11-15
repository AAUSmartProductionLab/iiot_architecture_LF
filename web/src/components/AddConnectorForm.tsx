import { useEffect, useMemo, useState } from "react";
import { api, type OpcuaNode } from "../api";
import { OpcuaBrowser } from "./OpcuaBrowser";
import { COMMON_DATATYPES, defaults, type Field, PROTOCOLS, schemaFor } from "../protocols";
import { Modal } from "./Modal";
import { Button } from "./ui";

const STEPS = ["Device", "Connection", "Datapoints", "Review"];

/** Matches the adapter's default (config_model._BaseConnector.interval = 2.0 s). */
const DEFAULT_INTERVAL_MS = 2000;
/** Lower bound to protect resource-constrained PLCs from being polled too hard. */
const MIN_INTERVAL_MS = 50;

/** One datapoint row in the wizard. `address` holds the protocol-specific fields. */
interface DpDraft {
  uid: number;
  name: string;
  datatype: string;
  unit: string;
  local_topic: string;
  /** True once the user typed a topic themselves, so renaming stops auto-filling it. */
  topicEdited: boolean;
  address: Record<string, string>;
}

let nextUid = 1;

function newDatapoint(datatype: string, address: Record<string, string>): DpDraft {
  return { uid: nextUid++, name: "", datatype, unit: "", local_topic: "", topicEdited: false, address: { ...address } };
}

/** Validation message for one datapoint, or null when it is complete. */
function datapointProblem(dp: DpDraft, fields: Field[], all: DpDraft[]): string | null {
  const name = dp.name.trim();
  if (!name) return "name is required";
  if (all.some((o) => o.uid !== dp.uid && o.name.trim() === name)) return `duplicate name "${name}"`;
  const topic = dp.local_topic.trim();
  if (topic && all.some((o) => o.uid !== dp.uid && o.local_topic.trim() === topic))
    return `duplicate topic "${topic}"`;
  const missing = fields.find((f) => f.required && !(dp.address[f.key] ?? "").trim());
  if (missing) return `${missing.label} is required`;
  return null;
}

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
      <label>
        {field.label}
        {field.required && <span className="req">*</span>}
      </label>
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
      {field.hint && <span className="hint">{field.hint}</span>}
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

/** True if any required field in the set is still blank. */
function missingRequired(fields: Field[], values: Record<string, string>): boolean {
  return fields.some((f) => f.required && !(values[f.key] ?? "").trim());
}

/** Auto device id tied to the gateway, e.g. "gw_901b0e_s7_a1b2c3".
 *  Must start with a letter (AAS id_short / AASd-002), hence the "gw_" prefix. */
function autoDeviceId(gatewayId: string, protocol: string): string {
  const gwToken = (gatewayId.split("-").pop() || gatewayId).replace(/[^A-Za-z0-9]/g, "");
  const proto = protocol.replace(/[^A-Za-z0-9]/g, "");
  const rand = Math.random().toString(36).slice(2, 8);
  return `gw_${gwToken}_${proto}_${rand}`;
}

/** Button that opens the add-connector wizard. */
export function AddConnectorForm({
  gatewayId,
  onDone,
}: {
  gatewayId: string;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>+ Add connector</Button>
      {open && (
        <ConnectorWizard
          gatewayId={gatewayId}
          onClose={() => setOpen(false)}
          onDone={onDone}
        />
      )}
    </>
  );
}

function ConnectorWizard({
  gatewayId,
  onClose,
  onDone,
}: {
  gatewayId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState(0);
  const [protocol, setProtocol] = useState(PROTOCOLS[0].id);
  const schema = useMemo(() => schemaFor(protocol), [protocol]);

  const [ident, setIdent] = useState({ device_id: "", manufacturer: "", model: "", serial_number: "" });
  const [conn, setConn] = useState<Record<string, string>>(defaults(schema.connection));
  // Polling interval in ms (the adapter polls every datapoint once per interval).
  const [intervalMs, setIntervalMs] = useState(String(DEFAULT_INTERVAL_MS));
  const intervalNum = Number(intervalMs);
  const intervalOk = intervalMs.trim() !== "" && Number.isFinite(intervalNum) && intervalNum >= MIN_INTERVAL_MS;
  const datatypes = schema.datatypes.length ? schema.datatypes : COMMON_DATATYPES;
  const [dps, setDps] = useState<DpDraft[]>(() => [newDatapoint(datatypes[0], defaults(schema.datapoint))]);

  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  // After provisioning we poll the connector's status to give a surface-level
  // connect verdict instead of optimistically claiming success.
  const [phase, setPhase] = useState<"form" | "checking" | "done">("form");
  const [verdict, setVerdict] = useState<{ state: string; reason?: string | null } | null>(null);

  // Reset the protocol-specific fields whenever the protocol changes.
  useEffect(() => {
    setConn(defaults(schema.connection));
    const dts = schema.datatypes.length ? schema.datatypes : COMMON_DATATYPES;
    setDps([newDatapoint(dts[0], defaults(schema.datapoint))]);
  }, [schema]);

  // Device id is optional: when left blank it is auto-named, tied to the gateway.
  const autoId = useMemo(() => autoDeviceId(gatewayId, protocol), [gatewayId, protocol]);
  const effectiveDeviceId = ident.device_id.trim() || autoId;

  const setIdentF = (k: keyof typeof ident) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setIdent({ ...ident, [k]: e.target.value });
  const updateDp = (uid: number, patch: Partial<DpDraft>) =>
    setDps((list) =>
      list.map((d) => {
        if (d.uid !== uid) return d;
        const next = { ...d, ...patch };
        // Auto-fill local_topic from the name until the user edits the topic.
        if (patch.name !== undefined && !d.topicEdited) {
          next.local_topic = patch.name.trim() ? `devices/${patch.name.trim()}` : "";
        }
        return next;
      })
    );
  const updateAddr = (uid: number, key: string, v: string) =>
    setDps((list) => list.map((d) => (d.uid === uid ? { ...d, address: { ...d.address, [key]: v } } : d)));
  // A new datapoint starts from the previous one's datatype and address, since
  // consecutive datapoints on a device usually differ only in register/offset/node.
  const addDp = () =>
    setDps((list) => {
      const last = list[list.length - 1];
      return [...list, newDatapoint(last?.datatype ?? datatypes[0], last?.address ?? defaults(schema.datapoint))];
    });
  const removeDp = (uid: number) => setDps((list) => (list.length > 1 ? list.filter((d) => d.uid !== uid) : list));

  const addBrowsed = (node: OpcuaNode) => setDps(list => {
    if (!node.datatype || list.some(d => d.address.node_id === node.node_id)) return list;
    const base = node.name.replace(/[^A-Za-z0-9_]/g, "_") || "datapoint";
    let name = base;
    let suffix = 2;
    while (list.some(d => d.name === name)) name = `${base}_${suffix++}`;
    const dp = newDatapoint(node.datatype, { node_id: node.node_id });
    dp.name = name;
    dp.local_topic = `devices/${effectiveDeviceId}/${name}`;
    dp.topicEdited = true;
    const blank = list.findIndex(d => !d.name && !d.local_topic && (!d.address.node_id || d.address.node_id === "ns=2;s="));
    return blank >= 0 ? list.map((d, i) => i === blank ? dp : d) : [...list, dp];
  });

  const problems = dps.map((d) => datapointProblem(d, schema.datapoint, dps));

  const canNext =
    step === 1
      ? !missingRequired(schema.connection, conn) && intervalOk
      : step === 2
      ? problems.every((p) => p === null)
      : true;
  const isLast = step === STEPS.length - 1;

  async function submit() {
    setBusy(true);
    setMsg(null);
    try {
      const res = (await api.provision({
        gateway_id: gatewayId,
        device_id: effectiveDeviceId,
        protocol,
        manufacturer: ident.manufacturer || undefined,
        model: ident.model || undefined,
        serial_number: ident.serial_number || undefined,
        connection: coerce(schema.connection, conn),
        interval: intervalNum / 1000, // backend/adapter use seconds
        datapoints: dps.map((d) => ({
          name: d.name.trim(),
          datatype: d.datatype,
          unit: d.unit.trim(),
          local_topic: d.local_topic.trim(),
          address: coerce(schema.datapoint, d.address),
        })),
      })) as { connector?: { device_key?: string } };
      onDone();
      setPhase("checking");
      await pollConnection(res?.connector?.device_key ?? effectiveDeviceId);
    } catch (err) {
      setMsg({ kind: "err", text: String(err) });
      setBusy(false);
    }
  }

  // Poll the connector's live status for a few seconds for a connect verdict.
  async function pollConnection(deviceKey: string) {
    for (let i = 0; i < 8; i++) {
      await new Promise((r) => setTimeout(r, 1500));
      try {
        const all = await api.connectorStatus();
        const s = all.find((x) => x.gateway_id === gatewayId && x.device_key === deviceKey);
        if (s && (s.state === "connected" || s.state === "error")) {
          setVerdict({ state: s.state, reason: s.reason });
          setPhase("done");
          setBusy(false);
          return;
        }
      } catch {
        /* keep polling; transient errors are fine */
      }
    }
    setVerdict({ state: "pending" });
    setPhase("done");
    setBusy(false);
  }

  const footer =
    phase === "form" ? (
      <>
        <Button variant="ghost" onClick={step === 0 ? onClose : () => setStep(step - 1)} disabled={busy}>
          {step === 0 ? "Cancel" : "Back"}
        </Button>
        {isLast ? (
          <Button onClick={submit} disabled={busy}>
            {busy ? "Provisioning…" : "Provision"}
          </Button>
        ) : (
          <Button onClick={() => setStep(step + 1)} disabled={!canNext}>
            Next
          </Button>
        )}
      </>
    ) : (
      <Button onClick={onClose} disabled={phase === "checking"}>
        {phase === "checking" ? "Testing…" : "Close"}
      </Button>
    );

  if (phase !== "form") {
    return (
      <Modal title="Add connector" open onClose={onClose} footer={footer} width={620}>
        <ConnectionResult phase={phase} verdict={verdict} deviceId={effectiveDeviceId} />
      </Modal>
    );
  }

  return (
    <Modal title="Add connector" open onClose={onClose} footer={footer} width={620}>
      <div className="steps">
        {STEPS.map((s, i) => (
          <div key={s} className={`step ${i === step ? "active" : i < step ? "done" : ""}`}>
            <span className="step-no">Step {i + 1}</span>
            <span>{s}</span>
          </div>
        ))}
      </div>

      {step === 0 && (
        <div className="field-grid">
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
            <input value={ident.device_id} onChange={setIdentF("device_id")} placeholder={autoId} />
            <span className="hint">Optional — auto-named <code>{autoId}</code> if left blank</span>
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
        </div>
      )}

      {step === 1 && (
        <div className="field-grid">
          {schema.connection.map((f) => (
            <FieldInput key={f.key} field={f} value={conn[f.key] ?? ""} onChange={(v) => setConn({ ...conn, [f.key]: v })} />
          ))}
          <div className="field">
            <label>Polling interval (ms)</label>
            <input
              type="number"
              min={MIN_INTERVAL_MS}
              step={50}
              value={intervalMs}
              onChange={(e) => setIntervalMs(e.target.value)}
            />
            <span className={intervalOk ? "hint" : "hint dp-problem"}>
              {intervalOk
                ? "How often every datapoint is read. Shorter catches faster changes but loads the PLC more."
                : `Must be at least ${MIN_INTERVAL_MS} ms`}
            </span>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="dp-list">
          {protocol === "opcua" && <OpcuaBrowser key={`${gatewayId}:${conn.endpoint_url}`}
            gatewayId={gatewayId} endpoint={conn.endpoint_url}
            selected={new Set(dps.map(d => d.address.node_id))} onAdd={addBrowsed} />}
          {dps.map((d, i) => (
            <div className="dp-card" key={d.uid}>
              <div className="dp-card-head">
                <span className="step-no">Datapoint {i + 1}</span>
                {/* Don't nag about a blank name on a fresh row; flag everything else. */}
                {problems[i] && d.name.trim() && <span className="dp-problem">{problems[i]}</span>}
                {dps.length > 1 && (
                  <Button variant="ghost" className="dp-remove" onClick={() => removeDp(d.uid)}>
                    Remove
                  </Button>
                )}
              </div>
              <div className="field-grid">
                <div className="field">
                  <label>Name<span className="req">*</span></label>
                  <input
                    value={d.name}
                    onChange={(e) => updateDp(d.uid, { name: e.target.value })}
                    placeholder="flow_rate"
                    autoFocus={i === dps.length - 1 && i > 0}
                  />
                </div>
                <div className="field">
                  <label>Datatype</label>
                  <select value={d.datatype} onChange={(e) => updateDp(d.uid, { datatype: e.target.value })}>
                    {datatypes.map((dt) => (
                      <option key={dt} value={dt}>{dt}</option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>Unit</label>
                  <input value={d.unit} onChange={(e) => updateDp(d.uid, { unit: e.target.value })} placeholder="m3/h" />
                </div>
                <div className="field">
                  <label>Local topic</label>
                  <input
                    value={d.local_topic}
                    onChange={(e) => updateDp(d.uid, { local_topic: e.target.value, topicEdited: true })}
                    placeholder="devices/zone1/flow"
                  />
                </div>
                {schema.datapoint.map((f) => (
                  <FieldInput key={f.key} field={f} value={d.address[f.key] ?? ""} onChange={(v) => updateAddr(d.uid, f.key, v)} />
                ))}
              </div>
            </div>
          ))}
          <Button variant="ghost" onClick={addDp}>
            + Add datapoint
          </Button>
        </div>
      )}

      {step === 3 && (
        <div className="wizard-review">
          <dl className="kv">
            <dt>Protocol</dt><dd>{schema.label}</dd>
            <dt>Device id</dt>
            <dd>
              {effectiveDeviceId}
              {!ident.device_id.trim() && <span className="muted"> (auto)</span>}
            </dd>
            {ident.manufacturer && (<><dt>Manufacturer</dt><dd>{ident.manufacturer}</dd></>)}
            {ident.model && (<><dt>Model</dt><dd>{ident.model}</dd></>)}
            {ident.serial_number && (<><dt>Serial</dt><dd>{ident.serial_number}</dd></>)}
            {schema.connection.map((f) => (
              <DtDd key={f.key} k={f.label} v={conn[f.key]} />
            ))}
            <dt>Polling interval</dt><dd>{intervalNum} ms</dd>
          </dl>
          <table className="dp-review">
            <thead>
              <tr>
                <th>Datapoint</th>
                <th>Type</th>
                <th>Unit</th>
                <th>Local topic</th>
                <th>Address</th>
              </tr>
            </thead>
            <tbody>
              {dps.map((d) => (
                <tr key={d.uid}>
                  <td>{d.name}</td>
                  <td>{d.datatype}</td>
                  <td>{d.unit || "—"}</td>
                  <td><code>{d.local_topic || "—"}</code></td>
                  <td>
                    {schema.datapoint
                      .filter((f) => d.address[f.key])
                      .map((f) => `${f.label}: ${d.address[f.key]}`)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </Modal>
  );
}

function DtDd({ k, v }: { k: string; v: string }) {
  if (!v) return null;
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}

function ConnectionResult({
  phase,
  verdict,
  deviceId,
}: {
  phase: "checking" | "done";
  verdict: { state: string; reason?: string | null } | null;
  deviceId: string;
}) {
  if (phase === "checking") {
    return (
      <p>
        Provisioned <strong>{deviceId}</strong>. Testing connection to the endpoint…
      </p>
    );
  }
  if (verdict?.state === "connected") {
    return (
      <div className="msg ok">
        Connected ✓ — <strong>{deviceId}</strong> reached its endpoint.
      </div>
    );
  }
  if (verdict?.state === "error") {
    return (
      <div className="msg err">
        Provisioned, but failed to connect: <strong>{verdict.reason || "unknown error"}</strong>. See
        the Logs tab for details.
      </div>
    );
  }
  return (
    <div className="msg">
      Provisioned <strong>{deviceId}</strong>. Connection status isn't available yet — check the Logs
      tab.
    </div>
  );
}
