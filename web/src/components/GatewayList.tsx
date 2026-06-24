import type { ReactNode } from "react";
import type { Gateway } from "../types";

interface Props {
  gateways: Gateway[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  action?: ReactNode;
}

export function GatewayList({ gateways, selectedId, onSelect, action }: Props) {
  return (
    <div className="card">
      <div className="section-head">
        <h2>Discovered gateways ({gateways.length})</h2>
        {action && <div className="row-actions">{action}</div>}
      </div>
      {gateways.length === 0 ? (
        <p className="muted">
          No gateways yet. They appear automatically via mDNS, or register one manually below.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Gateway</th>
              <th>Serial</th>
              <th>Address</th>
              <th>Devices</th>
            </tr>
          </thead>
          <tbody>
            {gateways.map((g) => (
              <tr
                key={g.gateway_id}
                className={`clickable ${selectedId === g.gateway_id ? "selected" : ""}`}
                onClick={() => onSelect(g.gateway_id)}
              >
                <td>
                  <span className={`dot ${g.online ? "on" : "off"}`} />
                  {g.online ? "online" : "offline"}
                </td>
                <td>{g.gateway_id}</td>
                <td>{g.serial_number ?? "—"}</td>
                <td className="muted">
                  {g.ip ? `${g.ip}:${g.port}` : "—"}
                </td>
                <td>{g.device_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
