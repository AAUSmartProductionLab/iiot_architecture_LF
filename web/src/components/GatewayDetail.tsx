import type { Gateway } from "../types";
import { AasViewer } from "./AasViewer";
import { AddConnectorForm } from "./AddConnectorForm";
import { ConfigureGatewayForm } from "./ConfigureGatewayForm";

export function GatewayDetail({
  gateway,
  onChanged,
}: {
  gateway: Gateway;
  onChanged: () => void;
}) {
  return (
    <div className="card">
      <h2>
        <span className={`dot ${gateway.online ? "on" : "off"}`} />
        {gateway.gateway_id}
      </h2>
      <p className="muted">
        serial {gateway.serial_number ?? "—"} · {gateway.ip ? `${gateway.ip}:${gateway.port}` : "no address"} ·{" "}
        {gateway.device_count} device(s)
      </p>

      <ConfigureGatewayForm gatewayId={gateway.gateway_id} />
      <AddConnectorForm gatewayId={gateway.gateway_id} onDone={onChanged} />
      <AasViewer gatewayId={gateway.gateway_id} />
    </div>
  );
}
