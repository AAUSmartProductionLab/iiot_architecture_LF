import { useState } from "react";
import { api } from "../api";
import { Modal } from "./Modal";
import { Button } from "./ui";

export function RegisterGatewayForm({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [ip, setIp] = useState("");
  const [port, setPort] = useState("8000");
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function close() {
    setOpen(false);
    setMsg(null);
  }

  async function submit() {
    setBusy(true);
    setMsg(null);
    try {
      await api.registerGateway(ip, Number(port));
      setIp("");
      onDone();
      close();
    } catch (err) {
      setMsg({ kind: "err", text: String(err) });
    } finally {
      setBusy(false);
    }
  }

  const footer = (
    <>
      <Button variant="ghost" onClick={close} disabled={busy}>
        Cancel
      </Button>
      <Button onClick={submit} disabled={busy || !ip}>
        {busy ? "Registering…" : "Register"}
      </Button>
    </>
  );

  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        + Register manually
      </Button>
      <Modal title="Register gateway manually" open={open} onClose={close} footer={footer} width={460}>
        <p className="muted" style={{ marginTop: 0 }}>
          Use when mDNS auto-discovery isn't available (e.g. containers on Windows/Mac).
        </p>
        <div className="field-grid">
          <div className="field">
            <label>IP / host</label>
            <input value={ip} onChange={(e) => setIp(e.target.value)} placeholder="192.168.0.50" />
          </div>
          <div className="field">
            <label>Port</label>
            <input value={port} onChange={(e) => setPort(e.target.value)} />
          </div>
        </div>
        {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
      </Modal>
    </>
  );
}
