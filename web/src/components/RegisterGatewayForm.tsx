import { useState } from "react";
import { api } from "../api";

export function RegisterGatewayForm({ onDone }: { onDone: () => void }) {
  const [ip, setIp] = useState("");
  const [port, setPort] = useState("8000");
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.registerGateway(ip, Number(port));
      setMsg({ kind: "ok", text: `Registered ${ip}:${port}` });
      setIp("");
      onDone();
    } catch (err) {
      setMsg({ kind: "err", text: String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Register gateway manually</h2>
      <p className="muted">
        Use when mDNS auto-discovery isn't available (e.g. containers on Windows/Mac).
      </p>
      <form className="row" onSubmit={submit}>
        <div className="field">
          <label>IP / host</label>
          <input value={ip} onChange={(e) => setIp(e.target.value)} placeholder="192.168.0.50" required />
        </div>
        <div className="field">
          <label>Port</label>
          <input value={port} onChange={(e) => setPort(e.target.value)} />
        </div>
        <button className="primary" disabled={busy || !ip}>
          {busy ? "Registering…" : "Register"}
        </button>
      </form>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </div>
  );
}
