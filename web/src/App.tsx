import { useCallback, useEffect, useState } from "react";
import { api, BASE } from "./api";
import type { Device, Gateway, Measurement } from "./types";
import { GatewayList } from "./components/GatewayList";
import { GatewayDetail } from "./components/GatewayDetail";
import { RegisterGatewayForm } from "./components/RegisterGatewayForm";
import { DeviceList } from "./components/DeviceList";
import { AasExplorer } from "./components/AasExplorer";

const POLL_MS = 4000;

type View = "gateways" | "devices" | "aas";
type Theme = "dark" | "light";

const NAV: { id: View; label: string }[] = [
  { id: "gateways", label: "Gateways" },
  { id: "devices", label: "Devices" },
  { id: "aas", label: "Asset Shells" },
];

export default function App() {
  const [view, setView] = useState<View>("gateways");
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem("theme") as Theme) || "dark");
  const [gateways, setGateways] = useState<Gateway[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const refresh = useCallback(async () => {
    try {
      const [gw, dv, ms] = await Promise.all([api.gateways(), api.devices(), api.measurementsLatest()]);
      setGateways(gw);
      setDevices(dv);
      setMeasurements(ms);
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
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">IIoT Control Board</div>
        <nav>
          {NAV.map((n) => (
            <button key={n.id} className={view === n.id ? "active" : ""} onClick={() => setView(n.id)}>
              {n.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <button className="theme-toggle" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            {theme === "dark" ? "☀ Light" : "🌙 Dark"}
          </button>
          <div className="muted small">
            orchestrator
            <br />
            <code>{BASE}</code>
          </div>
        </div>
      </aside>

      <main className="main">
        {error && <div className="msg err">Cannot reach orchestrator: {error}</div>}

        {view === "gateways" && (
          <>
            <GatewayList gateways={gateways} selectedId={selectedId} onSelect={setSelectedId} />
            {selected && <GatewayDetail gateway={selected} onChanged={refresh} />}
            <RegisterGatewayForm onDone={refresh} />
          </>
        )}

        {view === "devices" && <DeviceList devices={devices} measurements={measurements} />}

        {view === "aas" && (
          <AasExplorer gateways={gateways} devices={devices} measurements={measurements} />
        )}
      </main>
    </div>
  );
}
