// Typed REST helpers and message shapes for the conversation chat UI.
//
// These mirror the Pydantic models the server writes to LDJSON, so the
// browser and the server agree on one shape.  State arrives over the
// WebSocket; every mutating action goes through this REST API.

export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost: number | null;
}

export interface ToolCallInfo {
  id: string;
  name: string;
  arguments: string;
}

export interface ChatMessageInfo {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  reasoning: string;
  name: string | null;
  tool_call_id: string | null;
  tool_calls: ToolCallInfo[];
}

export interface ChatEntryInfo {
  type: 'message';
  id: string;
  timestamp: number;
  thread: string;
  message: ChatMessageInfo;
  author: string;
  model: string;
  usage: UsageInfo | null;
}

export interface ActionEntryInfo {
  type: 'action';
  id: string;
  timestamp: number;
  thread: string;
  name: string;
  arguments: Record<string, unknown>;
  status: 'running' | 'ok' | 'error';
  result: string;
  duration: number;
}

export interface ThreadHeaderInfo {
  type: 'thread';
  id: string;
  timestamp: number;
  slug: string;
  title: string;
}

export type EntryInfo = ChatEntryInfo | ActionEntryInfo | ThreadHeaderInfo;

export interface ThreadInfo {
  slug: string;
  title: string;
  message_count: number;
  updated: number;
}

export interface ConversationSnapshot {
  id: string;
  title: string;
  model: string;
  status: string;
  threads: ThreadInfo[];
}

/** Events pushed from the server over the conversation WebSocket. */
export type ServerEvent =
  | { type: 'snapshot'; snapshot: ConversationSnapshot }
  | { type: 'status'; status: string }
  | { type: 'threads'; threads: ThreadInfo[] }
  | { type: 'entry'; entry: EntryInfo }
  | { type: 'delta'; thread: string; kind: string; text: string }
  | { type: 'action'; action: ActionEntryInfo }
  | { type: 'error'; thread: string; error: string; message: string }
  | { type: 'entries'; thread: string; entries: EntryInfo[] }
  | { type: 'pong' };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(path, {
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

export function conversationApi(conversationId: string) {
  const root = `/conversations/api/${encodeURIComponent(conversationId)}`;
  const threadRoot = (slug: string) =>
    `${root}/threads/${encodeURIComponent(slug)}`;

  return {
    async snapshot(): Promise<ConversationSnapshot> {
      const data = await request<{ snapshot: ConversationSnapshot }>(
        root,
        {}
      );
      return data.snapshot;
    },

    async createThread(title: string): Promise<ThreadInfo> {
      const data = await request<{ thread: ThreadInfo }>(
        `${root}/threads`,
        { method: 'POST', body: JSON.stringify({ title }) }
      );
      return data.thread;
    },

    async entries(slug: string): Promise<EntryInfo[]> {
      const data = await request<{ entries: EntryInfo[] }>(
        threadRoot(slug),
        {}
      );
      return data.entries;
    },

    async send(slug: string, text: string): Promise<void> {
      await request(threadRoot(slug) + '/messages', {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
    },

    async interrupt(): Promise<void> {
      await request(`${root}/interrupt`, { method: 'POST' });
    },
  };
}

export type ConversationApi = ReturnType<typeof conversationApi>;
