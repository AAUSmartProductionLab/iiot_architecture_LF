import { useState } from "react";
import { api } from "../api";
import type { ConnectorStatus, Device, Measurement } from "../types";
import { Modal } from "./Modal";
import { Badge, Button, ConnState } from "./ui";

export function DeviceList({
  devices,
  measurements = [],
  statuses = [],
  onChanged,
}: {
  devices: Device[];
  measurements?: Measurement[];
  statuses?: ConnectorStatus[];
  onChanged?: () => void;
}) {
  const mIndex = new Map(measurements.map((m) => [`${m.device}|${m.datapoint}`, m]));
  const sIndex = new Map(statuses.map((s) => [`${s.gateway_id}|${s.device_key}`, s]));
  const [pending, setPending] = useState<Device | null>(null);

  return (
    <div className="card">
      <div className="section-head">
        <h2>Connected devices ({devices.length})</h2>
      </div>

      {devices.length === 0 ? (
        <p className="muted">No devices provisioned yet.</p>
      ) : (
        <div className="card-grid">
          {devices.map((d) => {
            const sysId = d.gateway_serial ? `${d.gateway_serial}_${d.device_key}` : null;
            const status = sIndex.get(`${d.gateway_id}|${d.device_key}`);
            return (
              <div className="device-card" key={d.device_aas_id ?? `${d.gateway_id}-${d.device_key}`}>
                <div className="dc-head">
                  <div>
                    <div className="dc-title">{d.device_id ?? d.device_key}</div>
                    <div className="dc-sub muted">{d.gateway_id}</div>
                  </div>
                  <Badge tone="accent">{d.protocol ?? "—"}</Badge>
                </div>
                <div className="row-actions">
                  <ConnState state={status?.state} reason={status?.reason} />
                </div>

                <div className="dc-points">
                  {d.datapoints.length === 0 && <span className="muted">no datapoints</span>}
                  {d.datapoints.map((p) => {
                    const m = sysId ? mIndex.get(`${sysId}|${p.name}`) : undefined;
                    return (
                      <div className="dc-point" key={p.name}>
                        <code>{p.name}{p.unit ? ` (${p.unit})` : ""}</code>
                        {m && m.value !== null ? (
                          <strong>{m.value}{m.unit ? ` ${m.unit}` : ""}</strong>
                        ) : (
                          <span className="muted">no data</span>
                        )}
                      </div>
                    );
                  })}
                </div>

                <div className="dc-foot">
                  <Button variant="danger" onClick={() => setPending(d)}>
                    Delete
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <DeleteDialog
        device={pending}
        onClose={() => setPending(null)}
        onDeleted={() => {
          setPending(null);
          onChanged?.();
        }}
      />
    </div>
  );
}

function DeleteDialog({
  device,
  onClose,
  onDeleted,
}: {
  device: Device | null;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    if (!device) return;
    setBusy(true);
    setErr(null);
    try {
      await api.deprovision(device.gateway_id, device.device_key);
      onDeleted();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  const footer = (
    <>
      <Button variant="ghost" onClick={onClose} disabled={busy}>
        Cancel
      </Button>
      <Button variant="danger" onClick={confirm} disabled={busy}>
        {busy ? "Deleting…" : "Delete connector"}
      </Button>
    </>
  );

  return (
    <Modal title="Delete connector" open={!!device} onClose={onClose} footer={footer} width={460}>
      {device && (
        <p>
          Remove <strong>{device.device_id ?? device.device_key}</strong> from{" "}
          <code>{device.gateway_id}</code>? This stops its adapter and deletes its
          Asset Administration Shell.
        </p>
      )}
      {err && <div className="msg err">{err}</div>}
    </Modal>
  );
}
