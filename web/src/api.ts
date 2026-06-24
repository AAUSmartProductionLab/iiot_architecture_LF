import type { AasBundle, Device, Gateway, Measurement } from "./types";

export const BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8000";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? ` — ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

export interface ProvisionPayload {
  gateway_id: string;
  device_id: string;
  protocol: string;
  connection: Record<string, unknown>;
  datapoints: Record<string, unknown>[];
  manufacturer?: string;
  model?: string;
  serial_number?: string;
}

export const api = {
  serverInfo: () => req<{ server_ip: string }>("/api/server-info"),
  gateways: () => req<Gateway[]>("/api/gateways"),
  devices: () => req<Device[]>("/api/devices"),
  gatewayAas: (id: string) =>
    req<AasBundle>(`/api/gateways/${encodeURIComponent(id)}/aas`),
  aasById: (aasId: string) =>
    req<AasBundle>(`/api/aas?id=${encodeURIComponent(aasId)}`),
  measurementsLatest: () => req<Measurement[]>("/api/measurements/latest"),
  registerGateway: (ip: string, port: number) =>
    req("/api/gateways/register", {
      method: "POST",
      body: JSON.stringify({ ip, port }),
    }),
  configureGateway: (id: string, serverBridgeIp?: string) =>
    req(`/api/gateways/${encodeURIComponent(id)}/configure`, {
      method: "POST",
      body: JSON.stringify(
        serverBridgeIp ? { server_bridge_ip: serverBridgeIp } : {}
      ),
    }),
  provision: (payload: ProvisionPayload) =>
    req("/api/provision", { method: "POST", body: JSON.stringify(payload) }),
  deprovision: (gatewayId: string, deviceKey: string) =>
    req(
      `/api/gateways/${encodeURIComponent(gatewayId)}/connectors/${encodeURIComponent(deviceKey)}`,
      { method: "DELETE" }
    ),
};
