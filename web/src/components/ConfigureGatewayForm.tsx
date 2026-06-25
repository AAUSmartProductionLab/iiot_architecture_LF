import { useEffect, useState } from "react";
import { api } from "../api";
import { Button } from "./ui";

const DEFAULT_UNS = "uns/enterprise/site/area/line";

export function ConfigureGatewayForm({
  gatewayId,
  unsPrefix,
}: {
  gatewayId: string;
  unsPrefix?: string | null;
}) {
  const [ip, setIp] = useState("");
  const [uns, setUns] = useState(unsPrefix || DEFAULT_UNS);
  const [autofilled, setAutofilled] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // Reflect the gateway's stored UNS prefix once it loads/changes.
  useEffect(() => {
    if (unsPrefix) setUns(unsPrefix);
  }, [unsPrefix]);

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
      // Empty IP -> orchestrator uses its own IP; UNS omitted -> gateway keeps current.
      const res: any = await api.configureGateway(
        gatewayId,
        ip || undefined,
        uns.trim() || undefined
      );
      setMsg({
        kind: "ok",
        text: `Bridge set to ${res.server_ip} (UNS ${res.uns_prefix}); broker restarted: ${res.broker_restarted}`,
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
        <div className="field">
          <label>UNS path <span className="muted">(bridge destination root)</span></label>
          <input
            value={uns}
            onChange={(e) => setUns(e.target.value)}
            placeholder={DEFAULT_UNS}
          />
        </div>
        <Button disabled={busy}>
          {busy ? "Applying…" : "Apply & restart broker"}
        </Button>
      </form>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </>
  );
}
