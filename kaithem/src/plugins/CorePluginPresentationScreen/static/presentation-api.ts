// Shared types and REST helpers for presentation screens.
//
// Every page (admin, editor, viewer) talks to the same endpoints, so the
// URL building and error handling live here instead of being duplicated.

/**
 * One screen-wide playback state.  The server is the single source of truth:
 * the admin page replaces it wholesale, and viewers only mirror it.
 *
 * ``slide`` is a zero-based index.  A viewer showing a longer deck than the
 * state implies clamps to its own last slide.
 */
export type PresentationState =
  | { type: 'none' }
  | { type: 'pptx'; file: string; slide: number };

export interface PresentationStateResponse {
  state: PresentationState;
  default_state: PresentationState;
}

/**
 * A named, saved state.  ``meta`` is book-keeping that never becomes part
 * of the played state; it survives overwriting the bookmark's state.
 */
export interface PresentationBookmark {
  name: string;
  state: PresentationState;
  meta: Record<string, unknown>;
}

export interface ViewerMessage {
  action: 'state' | 'pong';
  state?: PresentationState;
}

export function stoppedState(): PresentationState {
  return { type: 'none' };
}

/** Coerce whatever the server sent into a well-formed state. */
export function normalizeState(raw: unknown): PresentationState {
  if (!raw || typeof raw !== 'object') {
    return stoppedState();
  }
  const value = raw as { type?: unknown; file?: unknown; slide?: unknown };
  if (
    value.type !== 'pptx' ||
    typeof value.file !== 'string' ||
    !value.file
  ) {
    return stoppedState();
  }
  const slide =
    typeof value.slide === 'number' && Number.isFinite(value.slide)
      ? Math.max(0, Math.floor(value.slide))
      : 0;
  return { type: 'pptx', file: value.file, slide };
}

export interface PresentationFileInfo {
  name: string;
  size: number;
  mtime: number;
}

export interface PresentationConfig {
  title: string;
  view_permission: string;
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

export async function getState(
  ref: ScreenRef
): Promise<PresentationStateResponse> {
  const data = await fetchJson<{
    state: unknown;
    default_state: unknown;
  }>(apiUrl(ref, 'state'));
  return {
    state: normalizeState(data.state),
    default_state: normalizeState(data.default_state),
  };
}

/** Replace the server's whole playback state and notify every viewer. */
export async function setState(
  ref: ScreenRef,
  state: PresentationState
): Promise<void> {
  await fetchJson(apiUrl(ref, 'state'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state),
  });
}

/** Store the current state in the resource as its start state. */
export async function setDefaultState(
  ref: ScreenRef
): Promise<PresentationState> {
  const data = await fetchJson<{ default_state: unknown }>(
    apiUrl(ref, 'state-default'),
    { method: 'POST' }
  );
  return normalizeState(data.default_state);
}

/** The shortcut code carried in a bookmark's meta, or an empty string. */
export function bookmarkShortcut(
  meta: Record<string, unknown>
): string {
  const shortcut = meta['shortcut'];
  return typeof shortcut === 'string' ? shortcut : '';
}

function normalizeBookmark(
  name: string,
  raw: unknown
): PresentationBookmark {
  const value = (raw ?? {}) as { state?: unknown; meta?: unknown };
  const meta =
    value.meta && typeof value.meta === 'object'
      ? (value.meta as Record<string, unknown>)
      : {};
  return { name, state: normalizeState(value.state), meta };
}

export async function listBookmarks(
  ref: ScreenRef
): Promise<PresentationBookmark[]> {
  const data = await fetchJson<{ bookmarks?: Record<string, unknown> }>(
    apiUrl(ref, 'bookmarks')
  );
  return Object.entries(data.bookmarks ?? {})
    .map(([name, raw]) => normalizeBookmark(name, raw))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Save the current state under ``name``; existing meta is preserved. */
export async function saveBookmark(
  ref: ScreenRef,
  name: string
): Promise<PresentationBookmark> {
  const data = await fetchJson<{ bookmark: unknown }>(
    apiUrl(ref, 'bookmarks', `/${encodeURIComponent(name)}/save`),
    { method: 'POST' }
  );
  return normalizeBookmark(name, data.bookmark);
}

/** Play the state stored in a bookmark (its meta is not part of it). */
export async function gotoBookmark(
  ref: ScreenRef,
  name: string
): Promise<void> {
  await fetchJson(
    apiUrl(ref, 'bookmarks', `/${encodeURIComponent(name)}/goto`),
    { method: 'POST' }
  );
}

/** Replace a bookmark's meta, re-running its server change handlers. */
export async function setBookmarkMeta(
  ref: ScreenRef,
  name: string,
  meta: Record<string, unknown>
): Promise<PresentationBookmark> {
  const data = await fetchJson<{ bookmark: unknown }>(
    apiUrl(ref, 'bookmarks', `/${encodeURIComponent(name)}/meta`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ meta }),
    }
  );
  return normalizeBookmark(name, data.bookmark);
}

export async function deleteBookmark(
  ref: ScreenRef,
  name: string
): Promise<void> {
  await fetchJson(
    apiUrl(ref, 'bookmarks', `/${encodeURIComponent(name)}/delete`),
    { method: 'POST' }
  );
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
