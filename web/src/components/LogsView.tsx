import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ConnectorStatus, Device, Gateway } from "../types";
import { Button, ConnState } from "./ui";

const POLL_MS = 4000;
const TAIL = 1000; // line cap so the window stays bounded

interface Source {
  gatewayId: string;
  kind: "agent" | "broker" | "connector";
  deviceKey?: string;
  title: string;
}

function sameSource(a: Source | null, b: Source): boolean {
  return !!a && a.gatewayId === b.gatewayId && a.kind === b.kind && a.deviceKey === b.deviceKey;
}

export function LogsView({
  gateways,
  devices,
  statuses,
}: {
  gateways: Gateway[];
  devices: Device[];
  statuses: ConnectorStatus[];
}) {
  const [sel, setSel] = useState<Source | null>(null);
  const [logs, setLogs] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);
  const followRef = useRef(true); // keep pinned to the tail unless the user scrolls up

  const sIndex = new Map(statuses.map((s) => [`${s.gateway_id}|${s.device_key}`, s]));
  const selStatus =
    sel?.kind === "connector" ? sIndex.get(`${sel.gatewayId}|${sel.deviceKey}`) : undefined;

  // Poll the selected source's logs while it's open.
  useEffect(() => {
    if (!sel) return;
    let active = true;
    const load = async () => {
      setBusy(true);
      try {
        const r =
          sel.kind === "connector"
            ? await api.connectorLogs(sel.gatewayId, sel.deviceKey!, TAIL)
            : await api.gatewayLogs(sel.gatewayId, sel.kind, TAIL);
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

  // Follow the tail: scroll to the bottom on new output unless the user scrolled up.
  useEffect(() => {
    const el = preRef.current;
    if (el && followRef.current) el.scrollTop = el.scrollHeight;
  }, [logs]);

  function onScroll() {
    const el = preRef.current;
    if (el) followRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  }

  function open(src: Source) {
    followRef.current = true;
    setSel(src);
  }

  return (
    <div className="explorer">
      <div className="tree card">
        <h2>Logs</h2>
        {gateways.length === 0 && <p className="muted">No gateways.</p>}
        {gateways.map((g) => {
          const sources: Source[] = [
            { gatewayId: g.gateway_id, kind: "agent", title: "Gateway agent" },
            { gatewayId: g.gateway_id, kind: "broker", title: "Broker (HiveMQ)" },
            ...devices
              .filter((d) => d.gateway_id === g.gateway_id)
              .map((d) => ({
                gatewayId: g.gateway_id,
                kind: "connector" as const,
                deviceKey: d.device_key,
                title: d.device_id ?? d.device_key,
              })),
          ];
          return (
            <div className="tree-group" key={g.gateway_id}>
              <div className="tree-head">
                <span className={`dot ${g.online ? "on" : "off"}`} />
                {g.gateway_id}
              </div>
              {sources.map((src) => (
                <div
                  key={`${src.kind}-${src.deviceKey ?? ""}`}
                  className={`tree-item child ${sameSource(sel, src) ? "selected" : ""}`}
                  onClick={() => open(src)}
                >
                  {src.title}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="detail card">
        {!sel && (
          <p className="muted">Select a log source — the gateway agent, the broker, or a connector.</p>
        )}
        {sel && (
          <>
            <div className="section-head">
              <div>
                <h2 style={{ margin: 0 }}>{sel.title}</h2>
                <p className="muted" style={{ margin: "6px 0 0" }}>
                  {sel.gatewayId}
                </p>
              </div>
              <div className="row-actions">
                {selStatus && <ConnState state={selStatus.state} reason={selStatus.reason} />}
                <Button variant="ghost" onClick={() => open({ ...sel })} disabled={busy}>
                  {busy ? "Refreshing…" : "Refresh"}
                </Button>
              </div>
            </div>

            {selStatus?.state === "error" && selStatus.detail && (
              <div className="msg err">{selStatus.detail}</div>
            )}
            {err && <div className="msg err">{err}</div>}
            <pre ref={preRef} className="logs-pre" onScroll={onScroll}>
              {logs}
            </pre>
          </>
        )}
      </div>
    </div>
  );
}
