import { useEffect, useState } from "react";
import { api } from "../api";
import { Button } from "./ui";

export function ConfigureGatewayForm({ gatewayId }: { gatewayId: string }) {
  const [ip, setIp] = useState("");
  const [autofilled, setAutofilled] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // The bridge target is the edge server itself, so prefill its IP.
  useEffect(() => {
    api
      .serverInfo()
      .then((info) => {
        setIp(info.server_ip);
        setAutofilled(true);
      })
      .catch(() => setAutofilled(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      // Empty -> orchestrator uses its own IP; otherwise send the edited value.
      const res: any = await api.configureGateway(gatewayId, ip || undefined);
      setMsg({
        kind: "ok",
        text: `Bridge set to ${res.server_ip}; broker restarted: ${res.broker_restarted}`,
      });
    } catch (err) {
      setMsg({ kind: "err", text: String(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h3>Configure MQTT bridge</h3>
      <form className="row" onSubmit={submit}>
        <div className="field">
          <label>Edge server broker IP {autofilled && <span className="muted">(auto)</span>}</label>
          <input value={ip} onChange={(e) => setIp(e.target.value)} placeholder="auto-detected" />
        </div>
        <Button disabled={busy}>
          {busy ? "Applying…" : "Apply & restart broker"}
        </Button>
      </form>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </>
  );
}
