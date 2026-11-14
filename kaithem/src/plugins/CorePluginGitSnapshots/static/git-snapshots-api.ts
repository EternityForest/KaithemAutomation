// SPDX-License-Identifier: GPL-3.0-or-later
// Typed REST helpers for the snapshot backup UI.
//
// A "snapshot" is really an ordinary commit on the folder's main branch,
// but the server hides every trace of git's vocabulary.  The folder is
// passed as a query/form argument rather than a path segment, because it
// is an absolute filesystem path that can contain slashes.

export type RepoState = 'no_repo' | 'own_repo' | 'nested_repo';

export interface SnapshotInfo {
  commit: string;
  short: string;
  subject: string;
  author: string;
  timestamp: number;
}

export interface StatusInfo {
  state: RepoState;
  workspace: string;
  name: string;
  snapshots: SnapshotInfo[];
  head?: string;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Leave payload null and report the status below instead.
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

export function gitSnapshotsApi(workspace: string) {
  const query = '?workspace=' + encodeURIComponent(workspace);

  return {
    async status(): Promise<StatusInfo> {
      return request<StatusInfo>('/git-snapshots/api/status' + query);
    },

    async take(message: string): Promise<string> {
      const body = new URLSearchParams({ workspace, message });
      const data = await request<{ commit: string }>(
        '/git-snapshots/api/snapshot',
        { method: 'POST', body }
      );
      return data.commit;
    },

    async restore(commit: string): Promise<void> {
      const body = new URLSearchParams({ workspace, commit });
      await request('/git-snapshots/api/restore', { method: 'POST', body });
    },
  };
}

export type GitSnapshotsApi = ReturnType<typeof gitSnapshotsApi>;
