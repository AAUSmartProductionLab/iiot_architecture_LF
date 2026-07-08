import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { COMMON_DATATYPES, defaults, type Field, PROTOCOLS, schemaFor } from "../protocols";
import { Modal } from "./Modal";
import { Button } from "./ui";

const STEPS = ["Device", "Connection", "Datapoint", "Review"];

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
  const [dp, setDp] = useState({ name: "", datatype: "float32", unit: "", local_topic: "" });
  const [conn, setConn] = useState<Record<string, string>>(defaults(schema.connection));
  const [src, setSrc] = useState<Record<string, string>>(defaults(schema.datapoint));

  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  // After provisioning we poll the connector's status to give a surface-level
  // connect verdict instead of optimistically claiming success.
  const [phase, setPhase] = useState<"form" | "checking" | "done">("form");
  const [verdict, setVerdict] = useState<{ state: string; reason?: string | null } | null>(null);

  // Reset the protocol-specific fields whenever the protocol changes.
  useEffect(() => {
    setConn(defaults(schema.connection));
    setSrc(defaults(schema.datapoint));
  }, [schema]);

  // Device id is optional: when left blank it is auto-named, tied to the gateway.
  const autoId = useMemo(() => autoDeviceId(gatewayId, protocol), [gatewayId, protocol]);
  const effectiveDeviceId = ident.device_id.trim() || autoId;

  const setIdentF = (k: keyof typeof ident) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setIdent({ ...ident, [k]: e.target.value });
  const setDpF =
    (k: keyof typeof dp) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const v = e.target.value;
      const next = { ...dp, [k]: v };
      // Auto-fill local_topic when name changes (unless user already set one).
      if (k === "name" && !dp.local_topic) {
        next.local_topic = `devices/${v}`;
      }
      setDp(next);
    };

  const canNext =
    step === 1
      ? !missingRequired(schema.connection, conn)
      : step === 2
      ? !!dp.name.trim() && !missingRequired(schema.datapoint, src)
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
        datapoints: [
          {
            name: dp.name,
            datatype: dp.datatype,
            unit: dp.unit,
            local_topic: dp.local_topic,
            address: coerce(schema.datapoint, src),
          },
        ],
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
        </div>
      )}

      {step === 2 && (
        <div className="field-grid">
          <div className="field">
            <label>Datapoint name<span className="req">*</span></label>
            <input value={dp.name} onChange={setDpF("name")} placeholder="flow_rate" />
          </div>
          <div className="field">
            <label>Datatype</label>
            <select value={dp.datatype} onChange={setDpF("datatype")}>
              {(schema.datatypes.length ? schema.datatypes : COMMON_DATATYPES).map((dt) => (
                <option key={dt} value={dt}>{dt}</option>
              ))}
            </select>
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
            <dt>Datapoint</dt><dd>{dp.name}{dp.unit ? ` (${dp.unit})` : ""}</dd>
            {dp.local_topic && (<><dt>Local topic</dt><dd><code>{dp.local_topic}</code></dd></>)}
            {schema.datapoint.map((f) => (
              <DtDd key={f.key} k={f.label} v={src[f.key]} />
            ))}
          </dl>
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
