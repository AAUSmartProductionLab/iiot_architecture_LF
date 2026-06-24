export interface BridgeInfo {
  configured?: boolean;
  server_ip?: string | null;
  uns_prefix?: string | null;
}

export interface MqttInfo {
  local_broker_host?: string;
  local_broker_port?: number;
  local_base_topic?: string;
}

export interface Gateway {
  gateway_id: string;
  serial_number: string | null;
  ip: string | null;
  port: number | null;
  hostname: string | null;
  online: boolean;
  last_seen: number | null;
  device_count: number;
  bridge?: BridgeInfo | null;
  mqtt?: MqttInfo | null;
}

export interface Datapoint {
  name: string;
  datatype?: string;
  unit?: string;
  local_topic?: string;
  uns_topic?: string;
  description?: string;
}

export interface Device {
  gateway_id: string;
  gateway_serial: string | null;
  device_key: string;
  device_id: string | null;
  protocol: string | null;
  connection?: Record<string, unknown>;
  datapoints: Datapoint[];
  device_aas_id: string | null;
}

export interface AasBundle {
  shell: any;
  submodels: any[];
}

export interface ConnectorStatus {
  gateway_id: string;
  device_key: string;
  state: "connected" | "error" | "starting" | "stopped" | string;
  container?: string;
  reason?: string | null;
  detail?: string | null;
}

export interface Measurement {
  device: string;
  datapoint: string;
  value: number | null;
  unit: string | null;
  time: string | null;
  topic: string | null;
}
