import type { Device, Gateway } from "../types";
import { Badge } from "./ui";

/** Human-readable southbound endpoint from a connector's connection params. */
function southbound(protocol: string | null, conn: Record<string, unknown> = {}): string {
  const s = (k: string) => (conn[k] != null ? String(conn[k]) : "");
  switch (protocol) {
    case "modbus-tcp":
      return s("host") ? `${s("host")}:${s("port") || "502"}` : "—";
    case "s7":
      return s("host") ? `${s("host")} (rack ${s("rack") || "0"}/slot ${s("slot") || "1"})` : "—";
    case "opcua":
      return s("endpoint_url") || "—";
    case "usb":
      return s("vendor_id") || s("product_id") ? `${s("vendor_id")}:${s("product_id")}` : "—";
    default: {
      const parts = Object.entries(conn).map(([k, v]) => `${k}=${v}`);
      return parts.length ? parts.join(", ") : "—";
    }
  }
}

export function TopologyGraph({
  gateway,
  devices,
  archetype,
}: {
  gateway: Gateway;
  devices: Device[];
  archetype?: string;
}) {
  const serverIp = gateway.bridge?.server_ip || null;
  const unsPrefix = gateway.bridge?.uns_prefix || "";
  const bridged = !!gateway.bridge?.configured && !!serverIp;
  const broker =
    gateway.mqtt?.local_broker_host != null
      ? `${gateway.mqtt.local_broker_host}:${gateway.mqtt.local_broker_port ?? 1883}`
      : "local broker";

  return (
    <section>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>Network topology</h3>
        {archetype && <Badge>{archetype}</Badge>}
      </div>

      <div className="topo">
        {/* Northbound: edge server / UNS broker */}
        <div className="topo-node server">
          <div className="topo-title">Edge server · UNS</div>
          <div className="topo-meta">{serverIp || "not configured"}</div>
          {unsPrefix && <div className="topo-meta muted"><code>{unsPrefix}/#</code></div>}
        </div>

        <div className={`topo-link ${bridged ? "" : "dim"}`}>
          <span className="topo-link-label">↑ MQTT bridge {bridged ? "" : "(not configured)"}</span>
        </div>

        {/* The gateway itself */}
        <div className="topo-node gateway">
          <div className="topo-title">
            <span className={`dot ${gateway.online ? "on" : "off"}`} />
            {gateway.gateway_id}
          </div>
          <div className="topo-meta">{gateway.ip ? `${gateway.ip}:${gateway.port}` : "no address"}</div>
          <div className="topo-meta muted">broker {broker}</div>
        </div>

        <div className="topo-link">
          <span className="topo-link-label">↓ local MQTT</span>
        </div>

        {/* Southbound: attached devices/services */}
        {devices.length === 0 ? (
          <div className="muted" style={{ textAlign: "center" }}>no attached services</div>
        ) : (
          <div className="topo-devices">
            {devices.map((d) => (
              <div className="topo-node device" key={d.device_aas_id ?? `${d.gateway_id}-${d.device_key}`}>
                <div className="topo-title">
                  {d.device_id ?? d.device_key}
                  <Badge tone="accent">{d.protocol ?? "—"}</Badge>
                </div>
                <div className="topo-meta">{southbound(d.protocol, d.connection)}</div>
                <div className="topo-meta muted">
                  {d.datapoints.length} datapoint{d.datapoints.length === 1 ? "" : "s"}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
