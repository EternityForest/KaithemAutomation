// SPDX-License-Identifier: GPL-3.0-or-later
// A small Debug Adapter Protocol client.
//
// The adapter is reached over a websocket that carries raw DAP messages:
// one JSON object per frame, with no Content-Length framing.  Requests
// are correlated with their responses by ``seq``/``request_seq``; events
// are forwarded to a listener.  This is intentionally minimal: it only
// implements what the editor's debugger sidebar needs.

/** A source reference in a stack frame or breakpoint. */
export interface DapSource {
  name?: string;
  path?: string;
  sourceReference?: number;
}

/** One frame of a thread's call stack. */
export interface DapStackFrame {
  id: number;
  name: string;
  line: number;
  column: number;
  source?: DapSource;
}

/** A thread the adapter knows about. */
export interface DapThread {
  id: number;
  name: string;
}

/** A breakpoint the adapter has verified (or rejected). */
export interface DapBreakpoint {
  id?: number;
  verified: boolean;
  line?: number;
  source?: DapSource;
}

/** Connection state reported to the UI. */
export type DapStatus = 'connecting' | 'connected' | 'disconnected';

/** The event names the editor cares about. */
export interface DapEventBody {
  reason?: string;
  threadId?: number;
  allThreadsStopped?: boolean;
  category?: string;
  output?: string;
  exitCode?: number;
}

export interface DebuggerCallbacks {
  onEvent: (event: string, body: DapEventBody) => void;
  onStatus: (status: DapStatus) => void;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof globalThis.setTimeout>;
}

//: How long a single request may wait for its response before the client
//: gives up, so a hung adapter cannot wedge the UI.
const REQUEST_TIMEOUT_MS = 15_000;

export class DebuggerClient {
  private socket: WebSocket;
  private opened: Promise<void>;
  private seq = 0;
  private closed = false;
  private pending = new Map<number, PendingRequest>();

  constructor(
    url: string,
    private callbacks: DebuggerCallbacks
  ) {
    this.callbacks.onStatus('connecting');
    this.socket = new WebSocket(url);
    this.opened = new Promise<void>((resolve, reject) => {
      this.socket.addEventListener('open', () => {
        this.callbacks.onStatus('connected');
        resolve();
      });
      this.socket.addEventListener('error', () => {
        reject(new Error('DAP socket error'));
      });
    });
    this.socket.addEventListener('close', () => this._onClose());
    this.socket.addEventListener('message', (ev) => this._onMessage(ev.data));
  }

  /** Send a request and resolve with its response body. */
  async send<T = Record<string, unknown>>(
    command: string,
    args?: unknown
  ): Promise<T> {
    await this.opened;
    if (this.closed) throw new Error('DAP connection is closed');
    const seq = ++this.seq;
    const message = { seq, type: 'request', command, arguments: args };
    return new Promise<T>((resolve, reject) => {
      const timer = globalThis.setTimeout(() => {
        this.pending.delete(seq);
        reject(new Error('DAP request timed out: ' + command));
      }, REQUEST_TIMEOUT_MS);
      this.pending.set(seq, {
        resolve: resolve as (value: unknown) => void,
        reject,
        timer,
      });
      this.socket.send(JSON.stringify(message));
    });
  }

  /** Complete the initialize handshake. */
  initialize(): Promise<Record<string, unknown>> {
    return this.send('initialize', {
      clientID: 'kaithem-text-editor',
      adapterID: 'kaithem',
      linesStartAt1: true,
      columnsStartAt1: true,
      pathFormat: 'path',
    });
  }

  disconnect(): void {
    this.closed = true;
    this.socket.close();
  }

  private _onClose(): void {
    this.closed = true;
    this.callbacks.onStatus('disconnected');
    for (const request of this.pending.values()) {
      globalThis.clearTimeout(request.timer);
      request.reject(new Error('DAP connection closed'));
    }
    this.pending.clear();
  }

  private _onMessage(data: unknown): void {
    if (typeof data !== 'string') return;
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }
    if (msg.type === 'response') {
      const request = this.pending.get(msg.request_seq as number);
      if (!request) return;
      this.pending.delete(msg.request_seq as number);
      globalThis.clearTimeout(request.timer);
      if (msg.success) request.resolve(msg.body ?? {});
      else request.reject(new Error((msg.message as string) || 'DAP error'));
    } else if (msg.type === 'event') {
      this.callbacks.onEvent(
        msg.event as string,
        (msg.body ?? {}) as DapEventBody
      );
    }
  }
}
