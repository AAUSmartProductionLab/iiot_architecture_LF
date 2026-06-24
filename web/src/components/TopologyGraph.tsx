import { useLayoutEffect, useRef, useState } from "react";
import type { Device, Gateway } from "../types";
import { Badge } from "./ui";

const CELL_W = 220; // horizontal slot per device
const ROW_H = 108; // vertical slot per device row
const FAN_TOP = 38; // gap between the broker origin and the first device row

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
  const ref = useRef<HTMLDivElement>(null);
  const [avail, setAvail] = useState(0);

  // Track the available width so the fan-out can spread devices across it and
  // re-flow (with staggered rows) as the panel resizes.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setAvail(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const serverIp = gateway.bridge?.server_ip || null;
  const unsPrefix = gateway.bridge?.uns_prefix || "";
  const bridged = !!gateway.bridge?.configured && !!serverIp;
  const broker =
    gateway.mqtt?.local_broker_host != null
      ? `${gateway.mqtt.local_broker_host}:${gateway.mqtt.local_broker_port ?? 1883}`
      : "local broker";

  // Lay devices into as many columns as fit; few devices => one spread-out row.
  // When it wraps, shrink columns until the half-cell stagger still fits the
  // width, so a staggered layout never spills into a scrollbar.
  const n = devices.length;
  const width = avail || CELL_W;
  let cols = Math.max(1, Math.min(n || 1, Math.floor(width / CELL_W) || 1));
  while (cols > 1) {
    const willStagger = Math.ceil(n / cols) > 1;
    if (cols * CELL_W + (willStagger ? CELL_W / 2 : 0) <= width) break;
    cols--;
  }
  const rows = Math.max(1, Math.ceil(n / cols));
  const staggered = rows > 1;
  const contentW = cols * CELL_W + (staggered ? CELL_W / 2 : 0);
  const originX = contentW / 2; // broker fan-out point, centered under the gateway
  const svgH = FAN_TOP + rows * ROW_H;

  const placed = devices.map((d, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    // Odd rows shift half a slot so their nodes (and lines) sit in the gaps above.
    const x = col * CELL_W + CELL_W / 2 + (row % 2 === 1 ? CELL_W / 2 : 0);
    const y = FAN_TOP + row * ROW_H;
    return { d, x, y };
  });

  return (
    <section>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>Network topology</h3>
        {archetype && <Badge>{archetype}</Badge>}
      </div>

      <div className="topo" ref={ref}>
        {/* Northbound: edge server / UNS broker */}
        <div className="topo-node server">
          <div className="topo-title">Edge server · UNS</div>
          <div className="topo-meta">{serverIp || "not configured"}</div>
          {unsPrefix && (
            <div className="topo-meta muted">
              <code>{unsPrefix}/#</code>
            </div>
          )}
        </div>

        <div className={`topo-link ${bridged ? "" : "dim"}`}>
          <span className="topo-link-label">↑ MQTT bridge {bridged ? "" : "(not configured)"}</span>
        </div>

        {/* The gateway / broker */}
        <div className="topo-node gateway">
          <div className="topo-title">
            <span className={`dot ${gateway.online ? "on" : "off"}`} />
            {gateway.gateway_id}
          </div>
          <div className="topo-meta">{gateway.ip ? `${gateway.ip}:${gateway.port}` : "no address"}</div>
          <div className="topo-meta muted">broker {broker}</div>
        </div>

        {/* Southbound: fan a line from the broker to each attached service */}
        {n === 0 ? (
          <div className="muted" style={{ textAlign: "center", paddingTop: 14 }}>
            no attached services
          </div>
        ) : (
          <>
            <div className="topo-fan-cap muted">local MQTT</div>
            <div className="topo-fan-scroll">
              <div className="topo-fan" style={{ width: contentW, height: svgH }}>
                <svg className="topo-svg" width={contentW} height={svgH}>
                  {placed.map(({ x, y }, i) => (
                    <line key={i} className="topo-edge" x1={originX} y1={0} x2={x} y2={y} />
                  ))}
                  <circle className="topo-edge-dot" cx={originX} cy={0} r={3.5} />
                </svg>
                {placed.map(({ d, x, y }) => (
                  <div
                    key={d.device_aas_id ?? `${d.gateway_id}-${d.device_key}`}
                    className="topo-node device"
                    style={{ left: x, top: y, width: CELL_W - 26 }}
                  >
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
            </div>
          </>
        )}
      </div>
    </section>
  );
}
