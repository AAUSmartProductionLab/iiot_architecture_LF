import { useEffect, useState } from "react";
import { api } from "../api";
import type { AasBundle, Device, Gateway, Measurement } from "../types";
import * as aas from "../aas_render";
import { Button } from "./ui";
import { TopologyGraph } from "./TopologyGraph";

type Selection =
  | { kind: "gateway"; gateway: Gateway }
  | { kind: "device"; device: Device };

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString();
}

export function AasExplorer({
  gateways,
  devices,
  measurements,
}: {
  gateways: Gateway[];
  devices: Device[];
  measurements: Measurement[];
}) {
  const [sel, setSel] = useState<Selection | null>(null);
  const [bundle, setBundle] = useState<AasBundle | null>(null);
  const [raw, setRaw] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // latest value lookup: device system_id + datapoint -> measurement
  const mIndex = new Map(measurements.map((m) => [`${m.device}|${m.datapoint}`, m]));

  useEffect(() => {
    if (!sel) return;
    setLoading(true);
    setErr(null);
    setRaw(false);
    const p =
      sel.kind === "gateway"
        ? api.gatewayAas(sel.gateway.gateway_id)
        : sel.device.device_aas_id
        ? api.aasById(sel.device.device_aas_id)
        : Promise.reject(new Error("no device AAS id"));
    p.then(setBundle)
      .catch((e) => {
        setErr(String(e));
        setBundle(null);
      })
      .finally(() => setLoading(false));
  }, [sel]);

  return (
    <div className="explorer">
      <div className="tree card">
        <h2>Asset shells</h2>
        {gateways.map((g) => {
          const gw = sel?.kind === "gateway" && sel.gateway.gateway_id === g.gateway_id;
          const gwDevices = devices.filter((d) => d.gateway_id === g.gateway_id);
          return (
            <div key={g.gateway_id} className="tree-group">
              <div className={`tree-item ${gw ? "selected" : ""}`} onClick={() => setSel({ kind: "gateway", gateway: g })}>
                <span className={`dot ${g.online ? "on" : "off"}`} />
                {g.gateway_id}
              </div>
              {gwDevices.map((d) => {
                const on = sel?.kind === "device" && sel.device.device_aas_id === d.device_aas_id;
                return (
                  <div
                    key={d.device_aas_id ?? d.device_key}
                    className={`tree-item child ${on ? "selected" : ""}`}
                    onClick={() => setSel({ kind: "device", device: d })}
                  >
                    {d.device_id ?? d.device_key} <span className="muted">({d.protocol})</span>
                  </div>
                );
              })}
            </div>
          );
        })}
        {gateways.length === 0 && <p className="muted">No assets yet.</p>}
      </div>

      <div className="detail card">
        {!sel && <p className="muted">Select a gateway or device to inspect its Asset Administration Shell.</p>}
        {sel && (
          <>
            <h2>{sel.kind === "gateway" ? sel.gateway.gateway_id : sel.device.device_id ?? sel.device.device_key}</h2>
            <Lifecycle sel={sel} />
            {loading && <p className="muted">Loading AAS…</p>}
            {err && <div className="msg err">{err}</div>}
            {bundle && (
              <>
                <Button variant="ghost" onClick={() => setRaw(!raw)} style={{ marginBottom: 10 }}>
                  {raw ? "Rendered view" : "Raw JSON"}
                </Button>
                {raw ? (
                  <pre>{JSON.stringify(bundle, null, 2)}</pre>
                ) : (
                  <>
                    {sel.kind === "gateway" && (
                      <TopologyGraph
                        gateway={sel.gateway}
                        devices={devices.filter((d) => d.gateway_id === sel.gateway.gateway_id)}
                        archetype={aas.topology(bundle.submodels)?.archetype}
                      />
                    )}
                    <Rendered bundle={bundle} mIndex={mIndex} sel={sel} />
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Lifecycle({ sel }: { sel: Selection }) {
  if (sel.kind === "gateway") {
    const g = sel.gateway;
    return (
      <div className="lifecycle">
        <span className={`pill ${g.online ? "ok" : "bad"}`}>{g.online ? "online" : "offline"}</span>
        <span className="muted">serial {g.serial_number ?? "—"}</span>
        <span className="muted">{g.ip ? `${g.ip}:${g.port}` : "no address"}</span>
        <span className="muted">{g.hostname ?? ""}</span>
        <span className="muted">last seen {fmtTime(g.last_seen ? new Date(g.last_seen * 1000).toISOString() : null)}</span>
        <span className="muted">{g.device_count} device(s)</span>
      </div>
    );
  }
  return (
    <div className="lifecycle">
      <span className="muted">on gateway {sel.device.gateway_id}</span>
      <span className="muted">protocol {sel.device.protocol}</span>
    </div>
  );
}

function Rendered({
  bundle,
  mIndex,
  sel,
}: {
  bundle: AasBundle;
  mIndex: Map<string, Measurement>;
  sel: Selection;
}) {
  const np = aas.nameplate(bundle.submodels);
  const sw = aas.software(bundle.submodels);
  const ifaces = aas.interfaces(bundle.submodels);
  const sysId =
    sel.kind === "device" && sel.device.gateway_serial
      ? `${sel.device.gateway_serial}_${sel.device.device_key}`
      : null;

  return (
    <>
      {np && (
        <section>
          <h3>Digital Nameplate</h3>
          <dl className="kv">
            <dt>Manufacturer</dt><dd>{np.manufacturer || "—"}</dd>
            <dt>Product</dt><dd>{np.product || "—"}</dd>
            <dt>Serial</dt><dd>{np.serial || "—"}</dd>
          </dl>
        </section>
      )}
      {sw && (
        <section>
          <h3>Software</h3>
          <dl className="kv">
            <dt>Firmware</dt><dd>{sw.firmware || "—"}</dd>
            {sw.components.map((c) => (
              <DtDd key={c.name} k={c.name} v={c.version} />
            ))}
          </dl>
        </section>
      )}
      {ifaces.map((iface) => (
        <section key={iface.idShort}>
          <h3>Interface: {iface.protocol}</h3>
          <div className="muted" style={{ marginBottom: 6 }}>{iface.title} · <code>{iface.base}</code></div>
          {iface.datapoints.length > 0 && (
            <table>
              <thead>
                <tr><th>Datapoint</th><th>Type</th><th>Unit</th><th>Address / topic</th><th>Latest</th></tr>
              </thead>
              <tbody>
                {iface.datapoints.map((dp) => {
                  const m = sysId ? mIndex.get(`${sysId}|${dp.name}`) : undefined;
                  const addr = dp.forms.href || "";
                  return (
                    <tr key={dp.name}>
                      <td><code>{dp.name}</code></td>
                      <td>{dp.type || "—"}</td>
                      <td>{dp.unit || "—"}</td>
                      <td className="muted">{addr || "—"}</td>
                      <td>{m && m.value !== null ? `${m.value}${m.unit ? " " + m.unit : ""}` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {iface.actions.length > 0 && (
            <div className="muted">actions: {iface.actions.map((a) => a.name).join(", ")}</div>
          )}
        </section>
      ))}
    </>
  );
}

function DtDd({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v || "—"}</dd>
    </>
  );
}
