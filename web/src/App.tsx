import { useCallback, useEffect, useState } from "react";
import { api, BASE } from "./api";
import type { Device, Gateway } from "./types";
import { GatewayList } from "./components/GatewayList";
import { GatewayDetail } from "./components/GatewayDetail";
import { RegisterGatewayForm } from "./components/RegisterGatewayForm";
import { DeviceList } from "./components/DeviceList";

const POLL_MS = 4000;

type View = "gateways" | "devices";

export default function App() {
  const [view, setView] = useState<View>("gateways");
  const [gateways, setGateways] = useState<Gateway[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [gw, dv] = await Promise.all([api.gateways(), api.devices()]);
      setGateways(gw);
      setDevices(dv);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const selected = gateways.find((g) => g.gateway_id === selectedId) ?? null;

  return (
    <div className="app">
      <header>
        <h1>IIoT Control Board</h1>
        <div className="sub">
          orchestrator: <code>{BASE}</code> · auto-refresh {POLL_MS / 1000}s
        </div>
      </header>

      <div className="nav">
        <button className={view === "gateways" ? "active" : ""} onClick={() => setView("gateways")}>
          Gateways
        </button>
        <button className={view === "devices" ? "active" : ""} onClick={() => setView("devices")}>
          Devices
        </button>
      </div>

      {error && <div className="msg err">Cannot reach orchestrator: {error}</div>}

      {view === "gateways" && (
        <>
          <GatewayList gateways={gateways} selectedId={selectedId} onSelect={setSelectedId} />
          {selected && <GatewayDetail gateway={selected} onChanged={refresh} />}
          <RegisterGatewayForm onDone={refresh} />
        </>
      )}

      {view === "devices" && <DeviceList devices={devices} />}
    </div>
  );
}
