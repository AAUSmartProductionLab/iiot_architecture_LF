import { useEffect, useState } from "react";
import { api } from "../api";
import type { ConnectorStatus, Device } from "../types";
import { Button, ConnState } from "./ui";

const POLL_MS = 4000;

export function LogsView({
  devices,
  statuses,
}: {
  devices: Device[];
  statuses: ConnectorStatus[];
}) {
  const [sel, setSel] = useState<Device | null>(null);
  const [logs, setLogs] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sIndex = new Map(statuses.map((s) => [`${s.gateway_id}|${s.device_key}`, s]));
  const selStatus = sel ? sIndex.get(`${sel.gateway_id}|${sel.device_key}`) : undefined;

  // Poll the selected connector's logs while it's open.
  useEffect(() => {
    if (!sel) return;
    let active = true;
    const load = async () => {
      setBusy(true);
      try {
        const r = await api.connectorLogs(sel.gateway_id, sel.device_key, 400);
        if (active) {
          setLogs(r.logs || "(no output yet)");
          setErr(null);
        }
      } catch (e) {
        if (active) setErr(String(e));
      } finally {
        if (active) setBusy(false);
      }
    };
    load();
    const t = setInterval(load, POLL_MS);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [sel]);

  return (
    <div className="explorer">
      <div className="tree card">
        <h2>Connectors</h2>
        {devices.length === 0 && <p className="muted">No connectors provisioned.</p>}
        {devices.map((d) => {
          const on = sel?.gateway_id === d.gateway_id && sel?.device_key === d.device_key;
          const st = sIndex.get(`${d.gateway_id}|${d.device_key}`);
          return (
            <div
              key={`${d.gateway_id}-${d.device_key}`}
              className={`tree-item ${on ? "selected" : ""}`}
              onClick={() => setSel(d)}
            >
              <div>{d.device_id ?? d.device_key}</div>
              <div className="muted small">
                {d.gateway_id} · {st?.state ?? "—"}
              </div>
            </div>
          );
        })}
      </div>

      <div className="detail card">
        {!sel && <p className="muted">Select a connector to view its adapter logs.</p>}
        {sel && (
          <>
            <div className="section-head">
              <div>
                <h2 style={{ margin: 0 }}>{sel.device_id ?? sel.device_key}</h2>
                <p className="muted" style={{ margin: "6px 0 0" }}>
                  {sel.gateway_id} · {sel.protocol ?? "—"}
                </p>
              </div>
              <div className="row-actions">
                <ConnState state={selStatus?.state} reason={selStatus?.reason} />
                <Button variant="ghost" onClick={() => setSel({ ...sel })} disabled={busy}>
                  {busy ? "Refreshing…" : "Refresh"}
                </Button>
              </div>
            </div>

            {selStatus?.state === "error" && selStatus.detail && (
              <div className="msg err">{selStatus.detail}</div>
            )}
            {err && <div className="msg err">{err}</div>}
            <pre className="logs-pre">{logs}</pre>
          </>
        )}
      </div>
    </div>
  );
}
