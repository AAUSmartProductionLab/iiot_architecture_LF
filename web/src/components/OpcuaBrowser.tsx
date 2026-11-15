import { useEffect, useRef, useState } from "react";
import { api, type OpcuaNode, type OpcuaPage } from "../api";
import { Button } from "./ui";

export function OpcuaBrowser({ gatewayId, endpoint, selected, onAdd }: {
  gatewayId: string; endpoint: string; selected: Set<string>; onAdd: (node: OpcuaNode) => void;
}) {
  const [path, setPath] = useState([{ id: "i=85", name: "Objects" }]);
  const [page, setPage] = useState<OpcuaPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);

  async function load(nextPath = path, nextOffset = 0) {
    const id = ++request.current;
    setLoading(true); setError(""); setPage(null);
    try {
      const result = await api.browseOpcua(gatewayId, endpoint, nextPath[nextPath.length - 1].id, nextOffset);
      if (id !== request.current) return;
      setPath(nextPath); setOffset(nextOffset); setPage(result); setFilter("");
    } catch (err) {
      if (id === request.current) setError(String(err));
    } finally {
      if (id === request.current) setLoading(false);
    }
  }

  return <div className="dp-card">
    <strong>Browse OPC UA tags</strong>
    <p className="hint">Browse through this gateway using anonymous read access. Add scalar variables, then review their names, units and topics below.</p>
    <Button variant="ghost" onClick={() => load()} disabled={loading}>
      {loading ? "Browsing…" : page ? "Refresh folder" : "Browse tags"}
    </Button>
    {path.length > 1 && <Button variant="ghost" disabled={loading} onClick={() => load(path.slice(0, -1))}>Up</Button>}
    <p>{path.map(p => p.name).join(" / ")}</p>
    {error && <div role="alert" className="msg err">{error}</div>}
    {page && <>
      <label>Filter this page <input value={filter} onChange={e => setFilter(e.target.value)} /></label>
      <div style={{ maxHeight: 300, overflow: "auto" }}>
        {page.nodes.filter(n => `${n.name} ${n.node_id}`.toLowerCase().includes(filter.toLowerCase())).map(n =>
          <div key={n.node_id} style={{ borderBottom: "1px solid #8884", padding: "8px 0" }}>
            <strong>{n.name}</strong> <span className="hint">{n.type_label || n.node_class}</span>
            <div style={{ overflowWrap: "anywhere" }}><code style={{ wordBreak: "break-all" }}>{n.node_id}</code></div>
            <Button variant="ghost" disabled={loading} onClick={() => load([...path, { id: n.node_id, name: n.name }])}>Open</Button>
            {n.node_class === "Variable" && <Button variant="ghost"
              disabled={!n.selectable || selected.has(n.node_id)} onClick={() => onAdd(n)}>
              {selected.has(n.node_id) ? "Added" : "Add datapoint"}
            </Button>}
          </div>)}
        {page.nodes.length === 0 && <p>No child objects or variables.</p>}
      </div>
      {offset > 0 && <Button variant="ghost" disabled={loading} onClick={() => load(path, Math.max(0, offset - 100))}>Previous page</Button>}
      {page.next_offset !== null && <Button variant="ghost" disabled={loading} onClick={() => load(path, page.next_offset!)}>Next page</Button>}
      {page.limit_reached && <p>Browse limit reached. Enter further NodeIds manually.</p>}
      <p className="hint">Arrays and unknown types require manual configuration. Units are not inferred. Browsing does not write values.</p>
    </>}
  </div>;
}
