import type { Device, Measurement } from "../types";

export function DeviceList({
  devices,
  measurements = [],
}: {
  devices: Device[];
  measurements?: Measurement[];
}) {
  const mIndex = new Map(measurements.map((m) => [`${m.device}|${m.datapoint}`, m]));

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
              <th>Datapoints (latest value)</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => {
              const sysId = d.gateway_serial ? `${d.gateway_serial}_${d.device_key}` : null;
              return (
                <tr key={d.device_aas_id ?? `${d.gateway_id}-${d.device_key}`}>
                  <td>{d.device_id ?? d.device_key}</td>
                  <td className="muted">{d.gateway_id}</td>
                  <td>{d.protocol ?? "—"}</td>
                  <td>
                    {d.datapoints.map((p) => {
                      const m = sysId ? mIndex.get(`${sysId}|${p.name}`) : undefined;
                      return (
                        <div key={p.name}>
                          <code>{p.name}</code>
                          {p.unit ? ` (${p.unit})` : ""}
                          {m && m.value !== null ? (
                            <strong> = {m.value}{m.unit ? " " + m.unit : ""}</strong>
                          ) : (
                            <span className="muted"> — no data</span>
                          )}
                        </div>
                      );
                    })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
