import type { Gateway } from "../types";
import { AddConnectorForm } from "./AddConnectorForm";
import { ConfigureGatewayForm } from "./ConfigureGatewayForm";
import { StatusDot } from "./ui";

export function GatewayDetail({
  gateway,
  onChanged,
}: {
  gateway: Gateway;
  onChanged: () => void;
}) {
  return (
    <div className="card">
      <div className="section-head">
        <div>
          <h2>
            <span className={`dot ${gateway.online ? "on" : "off"}`} />
            {gateway.gateway_id}
          </h2>
          <p className="muted" style={{ margin: "6px 0 0" }}>
            serial {gateway.serial_number ?? "—"} ·{" "}
            {gateway.ip ? `${gateway.ip}:${gateway.port}` : "no address"} ·{" "}
            {gateway.device_count} device(s)
          </p>
        </div>
        <div className="row-actions">
          <StatusDot online={gateway.online} />
          <AddConnectorForm gatewayId={gateway.gateway_id} onDone={onChanged} />
        </div>
      </div>

      <ConfigureGatewayForm
        gatewayId={gateway.gateway_id}
        unsPrefix={gateway.bridge?.uns_prefix}
      />
    </div>
  );
}
