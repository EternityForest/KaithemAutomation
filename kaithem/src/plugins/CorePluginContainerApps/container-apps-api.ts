// Typed REST helpers for the container app admin pages.
//
// Two management surfaces share these helpers: the `app` development
// view and the `instance` admin view.  Both are served by
// /containerapps/api.

export interface BaseSnapshot {
  module: string;
  resource: string;
  title: string;
  status: string;
  error: string | null;
  built: boolean;
  kind: string | null;
  build_image: string | null;
  run_image: string | null;
  log: string[];
  environment: Record<string, string>;
}

export interface AppSnapshot extends BaseSnapshot {
  type: 'app';
  dev: boolean;
  empty: boolean;
  scripts: string[];
  dev_url: string;
}

export interface InstanceSnapshot extends BaseSnapshot {
  type: 'instance';
  name: string;
  running: boolean;
  app: string;
  url: string;
}

export type ContainerAppSnapshot = AppSnapshot | InstanceSnapshot;

export type AppAction =
  | 'build'
  | 'dev'
  | 'stop-dev'
  | 'reload'
  | 'clean'
  | 'delete-runtime'
  | 'copy-template'
  | 'run-script';

export type InstanceAction = 'start' | 'stop' | 'reload' | 'delete-runtime';

export type SurfaceKind = 'app' | 'instance';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
  }
}

const API_ROOT = '/containerapps/api';

function resourcePath(
  kind: SurfaceKind,
  module: string,
  resource: string
): string {
  return `/${kind}/${encodeURIComponent(module)}/${encodeURIComponent(resource)}`;
}

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
    const data = payload as { error?: string } | null;
    throw new ApiError(data?.error || response.statusText, response.status);
  }
  return payload as T;
}

export async function getApp(
  module: string,
  resource: string
): Promise<AppSnapshot> {
  return request<AppSnapshot>(resourcePath('app', module, resource));
}

export async function runAppAction(
  module: string,
  resource: string,
  action: AppAction,
  body?: Record<string, unknown>
): Promise<AppSnapshot> {
  return request<AppSnapshot>(
    `${resourcePath('app', module, resource)}/${action}`,
    {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }
  );
}

export async function getInstance(
  module: string,
  resource: string
): Promise<InstanceSnapshot> {
  return request<InstanceSnapshot>(resourcePath('instance', module, resource));
}

export async function runInstanceAction(
  module: string,
  resource: string,
  action: InstanceAction
): Promise<InstanceSnapshot> {
  return request<InstanceSnapshot>(
    `${resourcePath('instance', module, resource)}/${action}`,
    { method: 'POST' }
  );
}

export function websocketUrl(
  kind: SurfaceKind,
  module: string,
  resource: string
): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return (
    `${protocol}//${location.host}/containerapps/ws` +
    resourcePath(kind, module, resource)
  );
}
