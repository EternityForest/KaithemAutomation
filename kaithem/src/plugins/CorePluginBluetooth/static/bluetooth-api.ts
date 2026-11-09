// Typed REST helpers for the Bluetooth console.

export interface BluetoothAdapter {
  path: string;
  address: string | null;
  address_type: string | null;
  name: string | null;
  alias: string | null;
  class: number | null;
  powered: boolean;
  discovering: boolean;
  discovering_owned: boolean;
  discoverable: boolean;
  discoverable_timeout: number | null;
  pairable: boolean;
  pairable_timeout: number | null;
  roles: string[];
  uuids: string[];
  le_advertising: boolean;
  advertising: boolean;
  active_instances: number | null;
  supported_instances: number | null;
}

export interface BluetoothDeviceConfig {
  auto_connect: boolean;
  alerts: boolean;
  name: string | null;
}

export interface BluetoothDevice {
  path: string;
  adapter: string | null;
  address: string;
  name: string | null;
  alias: string | null;
  paired: boolean;
  bonded: boolean;
  trusted: boolean;
  connected: boolean;
  blocked: boolean;
  rssi: number | null;
  tx_power: number | null;
  battery: number | null;
  address_type: string | null;
  icon: string | null;
  class: number | null;
  services_resolved: boolean;
  uuids: string[];
  config: BluetoothDeviceConfig;
  // False for configured devices that BlueZ does not currently report.
  seen: boolean;
}

export interface BluetoothSnapshot {
  available: boolean;
  error: string | null;
  agent_registered: boolean;
  agent_error: string | null;
  adapters: BluetoothAdapter[];
  adapter: BluetoothAdapter | null;
  devices: BluetoothDevice[];
  revision: number;
  updated: number;
}

export interface AgentRequest {
  id: string;
  kind:
    | 'pin'
    | 'passkey'
    | 'confirm'
    | 'authorize'
    | 'authorize_service'
    | 'display_pin'
    | 'display_passkey';
  device_path: string;
  address: string | null;
  name: string | null;
  passkey: number | null;
  pin: string | null;
  uuid: string | null;
  entered: number | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string
  ) {
    super(message);
  }
}

const API_ROOT = '/bluetooth/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Leave payload null and report the status below.
  }
  if (!response.ok) {
    const data = payload as { error?: string; message?: string } | null;
    throw new ApiError(
      data?.message || data?.error || response.statusText,
      response.status,
      data?.error || 'error'
    );
  }
  return payload as T;
}

function snapshotFrom(payload: {
  snapshot: BluetoothSnapshot;
}): BluetoothSnapshot {
  return payload.snapshot;
}

export async function fetchSnapshot(): Promise<{
  snapshot: BluetoothSnapshot;
  agent_requests: AgentRequest[];
}> {
  return request('/snapshot');
}

export async function refreshSnapshot(): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>('/refresh', {
      method: 'POST',
    })
  );
}

export async function setDiscovering(
  discovering: boolean,
  adapter?: string
): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>('/discovering', {
      method: 'POST',
      body: JSON.stringify(
        adapter === undefined ? { discovering } : { discovering, adapter }
      ),
    })
  );
}

export type AdapterPropertyValue = boolean | string | number;

export async function setAdapterProperties(
  identifier: string,
  values: Record<string, AdapterPropertyValue>
): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>(
      `/adapters/${encodeURIComponent(identifier)}/properties`,
      { method: 'POST', body: JSON.stringify(values) }
    )
  );
}

export async function pairDevice(address: string): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>(
      `/devices/${encodeURIComponent(address)}/pair`,
      { method: 'POST' }
    )
  );
}

export async function connectDevice(
  address: string
): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>(
      `/devices/${encodeURIComponent(address)}/connect`,
      { method: 'POST' }
    )
  );
}

export async function disconnectDevice(
  address: string
): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>(
      `/devices/${encodeURIComponent(address)}/disconnect`,
      { method: 'POST' }
    )
  );
}

export async function setTrusted(
  address: string,
  trusted: boolean
): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>(
      `/devices/${encodeURIComponent(address)}/trust`,
      { method: 'POST', body: JSON.stringify({ trusted }) }
    )
  );
}

export async function forgetDevice(
  address: string
): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>(
      `/devices/${encodeURIComponent(address)}/forget`,
      { method: 'POST' }
    )
  );
}

export interface DeviceConfigResult {
  config: BluetoothDeviceConfig;
  snapshot: BluetoothSnapshot;
}

export async function fetchDeviceConfig(
  address: string
): Promise<BluetoothDeviceConfig> {
  const payload = await request<{ config: BluetoothDeviceConfig }>(
    `/devices/${encodeURIComponent(address)}/config`
  );
  return payload.config;
}

export async function setDeviceConfig(
  address: string,
  values: Partial<BluetoothDeviceConfig>
): Promise<DeviceConfigResult> {
  return request<DeviceConfigResult>(
    `/devices/${encodeURIComponent(address)}/config`,
    { method: 'POST', body: JSON.stringify(values) }
  );
}

export async function deleteDeviceConfig(
  address: string
): Promise<BluetoothSnapshot> {
  return snapshotFrom(
    await request<{ snapshot: BluetoothSnapshot }>(
      `/devices/${encodeURIComponent(address)}/config`,
      { method: 'DELETE' }
    )
  );
}
