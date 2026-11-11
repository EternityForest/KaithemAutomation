// Typed REST helpers for the podman image manager.

export interface PodmanImage {
  id: string;
  names: string[];
  size: number;
  created: number;
}

export interface PruneResult {
  containers: string;
  images: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
  }
}

const API_ROOT = '/podman/api';

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

export async function listImages(): Promise<PodmanImage[]> {
  const data = await request<{ images: PodmanImage[] }>('/images');
  return data.images ?? [];
}

export async function addTag(image: string, newTag: string): Promise<void> {
  await request('/tag', {
    method: 'POST',
    body: JSON.stringify({ image, new_tag: newTag }),
  });
}

export async function pullImage(image: string): Promise<void> {
  await request('/pull', {
    method: 'POST',
    body: JSON.stringify({ image }),
  });
}

export async function removeImage(image: string): Promise<string> {
  const data = await request<{ output?: string }>('/remove', {
    method: 'POST',
    body: JSON.stringify({ image }),
  });
  return data.output ?? '';
}

export async function prune(): Promise<PruneResult> {
  const data = await request<PruneResult>('/prune', { method: 'POST' });
  return { containers: data.containers ?? '', images: data.images ?? '' };
}

export function exportUrl(image: string): string {
  return `${API_ROOT}/export?image=${encodeURIComponent(image)}`;
}

export async function importImage(file: Blob): Promise<string> {
  const response = await fetch(`${API_ROOT}/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-tar' },
    body: file,
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
  const data = payload as { output?: string } | null;
  return data?.output ?? '';
}
