import { useState } from "react";
import { api } from "../api";
import type { AasBundle } from "../types";

export function AasViewer({ gatewayId }: { gatewayId: string }) {
  const [bundle, setBundle] = useState<AasBundle | null>(null);
  const [raw, setRaw] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setErr(null);
    try {
      setBundle(await api.gatewayAas(gatewayId));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h3>
        Asset Administration Shell{" "}
        <button className="ghost" onClick={load} disabled={busy}>
          {busy ? "Loading…" : bundle ? "Refresh" : "Load AAS"}
        </button>
        {bundle && (
          <button className="ghost" onClick={() => setRaw(!raw)} style={{ marginLeft: 6 }}>
            {raw ? "Summary" : "Raw JSON"}
          </button>
        )}
      </h3>
      {err && <div className="msg err">{err}</div>}
      {bundle && !raw && (
        <table>
          <thead>
            <tr>
              <th>Submodel</th>
              <th>semanticId</th>
              <th>Elements</th>
            </tr>
          </thead>
          <tbody>
            {bundle.submodels.map((sm) => (
              <tr key={sm.id}>
                <td>{sm.idShort}</td>
                <td className="muted">
                  <code>{sm.semanticId?.keys?.[0]?.value ?? "—"}</code>
                </td>
                <td>{(sm.submodelElements ?? []).map((e: any) => e.idShort).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {bundle && raw && <pre>{JSON.stringify(bundle, null, 2)}</pre>}
    </>
  );
}
