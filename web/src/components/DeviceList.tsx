import type { Device } from "../types";

export function DeviceList({ devices }: { devices: Device[] }) {
  return (
    <div className="card">
      <h2>Connected devices ({devices.length})</h2>
      {devices.length === 0 ? (
        <p className="muted">No devices provisioned yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Device</th>
              <th>Gateway</th>
              <th>Protocol</th>
              <th>Datapoints</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => (
              <tr key={d.device_aas_id ?? `${d.gateway_id}-${d.device_key}`}>
                <td>{d.device_id ?? d.device_key}</td>
                <td className="muted">{d.gateway_id}</td>
                <td>{d.protocol ?? "—"}</td>
                <td>
                  {d.datapoints.map((p) => (
                    <div key={p.name}>
                      <code>{p.name}</code>
                      {p.unit ? ` (${p.unit})` : ""}
                      {p.uns_topic ? <span className="muted"> → {p.uns_topic}</span> : null}
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
