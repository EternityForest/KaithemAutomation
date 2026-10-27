// Shared types and REST helpers for presentation screens.
//
// Every page (admin, editor, viewer) talks to the same endpoints, so the
// URL building and error handling live here instead of being duplicated.

export type ViewerAction = 'load' | 'stop' | 'next' | 'prev' | 'goto';

export interface ViewerCommand {
  action: ViewerAction | 'ready' | 'pong';
  file?: string;
  slide?: number;
}

export interface PresentationFileInfo {
  name: string;
  size: number;
  mtime: number;
}

export interface PresentationConfig {
  title: string;
  view_requires_admin: boolean;
}

export interface PresentationStatus {
  connected: number;
}

export interface ScreenRef {
  module: string;
  resource: string;
}

const API_ROOT = '/presentation-screen/api';

export const PPTX_MIME =
  'application/vnd.openxmlformats-officedocument.presentationml.presentation';

/** Read the ``module`` and ``resource`` URL parameters. */
export function screenRefFromUrl(search = globalThis.location.search): ScreenRef {
  const params = new URLSearchParams(search);
  const module = params.get('module');
  const resource = params.get('resource');
  if (!module || !resource) {
    throw new Error('URL must include module and resource parameters');
  }
  return { module, resource };
}

function refPath(ref: ScreenRef): string {
  return `${encodeURIComponent(ref.module)}/${encodeURIComponent(ref.resource)}`;
}

function apiUrl(ref: ScreenRef, verb: string, suffix: string = ''): string {
  return `${API_ROOT}/${verb}/${refPath(ref)}${suffix}`;
}

async function fetchJson<T>(
  url: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body && typeof body.error === 'string') {
        detail = body.error;
      }
    } catch {
      // Non-JSON error body: keep the status text.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function listFiles(
  ref: ScreenRef
): Promise<PresentationFileInfo[]> {
  const data = await fetchJson<{ files: PresentationFileInfo[] }>(
    apiUrl(ref, 'files')
  );
  return data.files;
}

export async function getConfig(
  ref: ScreenRef
): Promise<PresentationConfig> {
  return fetchJson<PresentationConfig>(apiUrl(ref, 'config'));
}

export async function setConfig(
  ref: ScreenRef,
  config: Partial<PresentationConfig>
): Promise<void> {
  await fetchJson(apiUrl(ref, 'config'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export async function getStatus(
  ref: ScreenRef
): Promise<PresentationStatus> {
  return fetchJson<PresentationStatus>(apiUrl(ref, 'status'));
}

export async function sendCommand(
  ref: ScreenRef,
  command: ViewerCommand
): Promise<void> {
  await fetchJson(apiUrl(ref, 'command'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
  });
}

export async function saveFile(
  ref: ScreenRef,
  filename: string,
  bytes: Uint8Array
): Promise<void> {
  await fetchJson(
    apiUrl(ref, 'save', `/${encodeURIComponent(filename)}`),
    {
      method: 'POST',
      headers: { 'Content-Type': PPTX_MIME },
      // fetch's BodyInit typings predate typed-array buffers.
      body: bytes as unknown as BodyInit,
    }
  );
}

export async function deleteFile(
  ref: ScreenRef,
  filename: string
): Promise<void> {
  await fetchJson(apiUrl(ref, 'delete', `/${encodeURIComponent(filename)}`), {
    method: 'POST',
  });
}

export function fileUrl(ref: ScreenRef, filename: string): string {
  return apiUrl(ref, 'file', `/${encodeURIComponent(filename)}`);
}

export function viewerUrl(ref: ScreenRef): string {
  return (
    `/presentation-screen/viewer/${encodeURIComponent(ref.module)}` +
    `/${encodeURIComponent(ref.resource)}`
  );
}

export function editorUrl(ref: ScreenRef, filename?: string): string {
  const params = new URLSearchParams({
    module: ref.module,
    resource: ref.resource,
  });
  if (filename) {
    params.set('file', filename);
  }
  return `/presentation-screen/editor/${encodeURIComponent(ref.module)}` +
    `/${encodeURIComponent(ref.resource)}?${params.toString()}`;
}

export function adminUrl(ref: ScreenRef): string {
  return (
    `/presentation-screen/admin/${encodeURIComponent(ref.module)}` +
    `/${encodeURIComponent(ref.resource)}`
  );
}

/** Ensure a name is a bare ``.pptx`` filename before sending it to the API. */
export function validatePptxFilename(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) {
    throw new Error('Enter a filename');
  }
  if (trimmed.includes('/') || trimmed.includes('\\')) {
    throw new Error('Filename must not contain a path');
  }
  if (!trimmed.toLowerCase().endsWith('.pptx')) {
    throw new Error('Filename must end with .pptx');
  }
  return trimmed;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KiB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
