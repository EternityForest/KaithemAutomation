// Conversation chat UI.
//
// Everything that changes arrives over /conversations/ws/<uuid>; mutating
// actions go through the REST API in conversation-api.ts.  The page reads
// the conversation uuid from the ?uuid= query parameter, so one bundle
// serves every conversation.
//
// There is deliberately no model picker: the model is a property of the
// conversation resource and is changed in the resource editor.

import { LitElement, html, nothing } from 'lit';
import type { TemplateResult } from 'lit';

import { conversationApi } from './conversation-api.ts';
import type {
  ActionEntryInfo,
  ChatEntryInfo,
  ConversationApi,
  ConversationSnapshot,
  EntryInfo,
  ServerEvent,
  ThreadInfo,
} from './conversation-api.ts';

type ConnectionState = 'connecting' | 'connected' | 'disconnected';

const PING_INTERVAL = 25_000;
const RECONNECT_START = 2000;
const RECONNECT_MAX = 15_000;

/** The conversation id is the whole point of the page. */
function uuidFromLocation(): string {
  const params = new URLSearchParams(globalThis.location.search);
  return (params.get('uuid') ?? '').trim();
}

export class ConversationChat extends LitElement {
  private conversationId = '';
  private api: ConversationApi | null = null;

  private snapshot: ConversationSnapshot | null = null;
  private entries: EntryInfo[] = [];
  private activeThread = '';
  private streaming: { thread: string; content: string; reasoning: string } = {
    thread: '',
    content: '',
    reasoning: '',
  };

  private expandedThoughts = new Set<string>();
  private expandedActions = new Set<string>();

  private sidebarOpen = false;
  private draft = '';
  private sending = false;
  private loadingThread = false;
  private creatingThread = false;
  private autoCreatedThread = false;
  private stickToBottom = true;

  private error = '';

  private ws: WebSocket | null = null;
  private wsState: ConnectionState = 'connecting';
  private reconnectDelay = RECONNECT_START;
  private reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null =
    null;
  private pingTimer: ReturnType<typeof globalThis.setInterval> | null = null;
  private destroyed = false;

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    this.conversationId = uuidFromLocation();
    if (!this.conversationId) {
      this.error = 'No conversation id was provided in the URL.';
      this.requestUpdate();
      return;
    }
    this.api = conversationApi(this.conversationId);
    this.connectSocket();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.destroyed = true;
    this.clearTimers();
    this.ws?.close();
    this.ws = null;
  }

  private clearTimers(): void {
    if (this.reconnectTimer !== null) {
      globalThis.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.pingTimer !== null) {
      globalThis.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  // ------------------------------------------------------------------
  // Socket
  // ------------------------------------------------------------------

  private connectSocket(): void {
    if (this.destroyed) {
      return;
    }
    const protocol = globalThis.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url =
      `${protocol}//${globalThis.location.host}/conversations/ws/` +
      encodeURIComponent(this.conversationId);
    const socket = new WebSocket(url);
    this.ws = socket;
    this.wsState = 'connecting';
    this.requestUpdate();

    socket.addEventListener('open', () => {
      if (this.ws !== socket) {
        return;
      }
      this.wsState = 'connected';
      this.reconnectDelay = RECONNECT_START;
      this.startPing();
      this.requestUpdate();
    });

    socket.addEventListener('close', () => {
      if (this.ws === socket) {
        this.ws = null;
      }
      this.stopPing();
      if (this.destroyed) {
        return;
      }
      this.wsState = 'disconnected';
      this.scheduleReconnect();
      this.requestUpdate();
    });

    socket.addEventListener('error', () => {
      this.error = 'Lost the connection to the conversation.';
      this.requestUpdate();
    });

    socket.addEventListener('message', (event: MessageEvent<string>) => {
      this.handleSocketMessage(event.data);
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) {
      return;
    }
    const delay = this.reconnectDelay;
    this.reconnectDelay = Math.min(this.reconnectDelay * 1.7, RECONNECT_MAX);
    this.reconnectTimer = globalThis.setTimeout(() => {
      this.reconnectTimer = null;
      this.connectSocket();
    }, delay);
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = globalThis.setInterval(() => {
      this.sendSocket({ type: 'ping' });
    }, PING_INTERVAL);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      globalThis.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private sendSocket(message: Record<string, unknown>): void {
    const socket = this.ws;
    if (socket === null || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    socket.send(JSON.stringify(message));
  }

  private handleSocketMessage(raw: string): void {
    let event: ServerEvent;
    try {
      event = JSON.parse(raw) as ServerEvent;
    } catch {
      return;
    }
    switch (event.type) {
      case 'snapshot': {
        this.applySnapshot(event.snapshot);
        break;
      }
      case 'status': {
        this.applyStatus(event.status);
        break;
      }
      case 'threads': {
        this.applyThreads(event.threads);
        break;
      }
      case 'entries': {
        this.applyEntries(event.thread, event.entries);
        break;
      }
      case 'entry': {
        this.applyEntry(event.entry);
        break;
      }
      case 'action': {
        this.upsertEntry(event.action);
        break;
      }
      case 'delta': {
        this.applyDelta(event.thread, event.kind, event.text);
        break;
      }
      case 'error': {
        this.error = event.message || 'The model request failed.';
        this.streaming = { thread: '', content: '', reasoning: '' };
        break;
      }
      case 'pong': {
        break;
      }
    }
    this.requestUpdate();
  }

  private applySnapshot(snapshot: ConversationSnapshot): void {
    this.snapshot = snapshot;
    const slugs = snapshot.threads.map((thread) => thread.slug);
    if (!this.activeThread || !slugs.includes(this.activeThread)) {
      this.activeThread = slugs[0] ?? '';
    }
    if (snapshot.threads.length === 0) {
      void this.ensureDefaultThread();
      return;
    }
    if (this.activeThread) {
      this.subscribe(this.activeThread);
    }
  }

  private applyStatus(status: string): void {
    if (this.snapshot) {
      this.snapshot = { ...this.snapshot, status };
    }
    if (status === 'idle' || status === 'error') {
      this.streaming = { thread: '', content: '', reasoning: '' };
    }
  }

  private applyThreads(threads: ThreadInfo[]): void {
    if (this.snapshot) {
      this.snapshot = { ...this.snapshot, threads };
    }
    const slugs = threads.map((thread) => thread.slug);
    if (!this.activeThread || !slugs.includes(this.activeThread)) {
      const first = slugs[0];
      if (first) {
        this.selectThread(first);
      }
    }
  }

  private applyEntries(thread: string, entries: EntryInfo[]): void {
    if (thread !== this.activeThread) {
      return;
    }
    this.entries = entries;
    this.loadingThread = false;
    this.stickToBottom = true;
  }

  private applyEntry(entry: EntryInfo): void {
    const thread = entry.thread;
    if (entry.type === 'thread') {
      return;
    }
    if (entry.type === 'message' && entry.message.role === 'assistant') {
      this.streaming = { thread: '', content: '', reasoning: '' };
    }
    if (thread === this.activeThread) {
      this.upsertEntry(entry);
      this.stickToBottom = true;
    }
    this.bumpThread(thread, entry);
  }

  private upsertEntry(entry: EntryInfo): void {
    if (entry.type === 'thread') {
      return;
    }
    if (entry.thread !== this.activeThread) {
      return;
    }
    const index = this.entries.findIndex((item) => item.id === entry.id);
    if (index === -1) {
      this.entries = [...this.entries, entry];
    } else {
      const next = [...this.entries];
      next[index] = entry;
      this.entries = next;
    }
  }

  private bumpThread(thread: string, entry: EntryInfo): void {
    if (!this.snapshot || entry.type === 'thread') {
      return;
    }
    const added = entry.type === 'message' ? 1 : 0;
    this.snapshot = {
      ...this.snapshot,
      threads: this.snapshot.threads.map((info) =>
        info.slug === thread
          ? {
              ...info,
              message_count: info.message_count + added,
              updated: entry.timestamp,
            }
          : info
      ),
    };
  }

  private applyDelta(thread: string, kind: string, text: string): void {
    if (thread !== this.activeThread) {
      return;
    }
    if (this.streaming.thread !== thread) {
      this.streaming = { thread, content: '', reasoning: '' };
    }
    this.streaming =
      kind === 'reasoning'
        ? {
            ...this.streaming,
            reasoning: this.streaming.reasoning + text,
          }
        : {
            ...this.streaming,
            content: this.streaming.content + text,
          };
    this.stickToBottom = true;
  }

  // ------------------------------------------------------------------
  // Threads
  // ------------------------------------------------------------------

  private subscribe(slug: string): void {
    this.loadingThread = true;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendSocket({ type: 'subscribe', thread: slug });
      return;
    }
    void this.loadThreadRest(slug);
  }

  private async loadThreadRest(slug: string): Promise<void> {
    if (!this.api) {
      return;
    }
    try {
      const entries = await this.api.entries(slug);
      this.applyEntries(slug, entries);
    } catch (error) {
      this.error = describeError(error);
      this.loadingThread = false;
    }
    this.requestUpdate();
  }

  private selectThread(slug: string): void {
    if (!slug) {
      return;
    }
    this.activeThread = slug;
    this.entries = [];
    this.streaming = { thread: '', content: '', reasoning: '' };
    this.sidebarOpen = false;
    this.subscribe(slug);
    this.requestUpdate();
  }

  private async ensureDefaultThread(): Promise<void> {
    if (this.autoCreatedThread || this.creatingThread || !this.api) {
      return;
    }
    this.autoCreatedThread = true;
    this.creatingThread = true;
    try {
      const thread = await this.api.createThread('Chat');
      this.selectThread(thread.slug);
    } catch (error) {
      this.error = describeError(error);
      this.autoCreatedThread = false;
    } finally {
      this.creatingThread = false;
      this.requestUpdate();
    }
  }

  private async newThread(): Promise<void> {
    if (!this.api || this.creatingThread) {
      return;
    }
    const answer = globalThis.prompt('Name for the new thread', '');
    if (answer === null) {
      return;
    }
    const title = answer.trim() || 'Thread';
    this.creatingThread = true;
    try {
      const thread = await this.api.createThread(title);
      this.selectThread(thread.slug);
    } catch (error) {
      this.error = describeError(error);
    } finally {
      this.creatingThread = false;
      this.requestUpdate();
    }
  }

  // ------------------------------------------------------------------
  // Composer and actions
  // ------------------------------------------------------------------

  private async sendMessage(): Promise<void> {
    const text = this.draft.trim();
    if (!this.api || !this.activeThread || !text || this.sending) {
      return;
    }
    this.draft = '';
    this.sending = true;
    this.error = '';
    this.requestUpdate();
    try {
      await this.api.send(this.activeThread, text);
      if (this.wsState !== 'connected') {
        await this.loadThreadRest(this.activeThread);
      }
    } catch (error) {
      this.error = describeError(error);
      this.draft = text;
    } finally {
      this.sending = false;
      this.requestUpdate();
    }
  }

  private async interrupt(): Promise<void> {
    if (!this.api || !this.activeThread) {
      return;
    }
    this.error = '';
    try {
      await this.api.interrupt();
    } catch (error) {
      this.error = describeError(error);
    }
    this.requestUpdate();
  }

  private toggleThoughts(id: string): void {
    if (this.expandedThoughts.has(id)) {
      this.expandedThoughts.delete(id);
    } else {
      this.expandedThoughts.add(id);
    }
    this.requestUpdate();
  }

  private toggleAction(id: string): void {
    if (this.expandedActions.has(id)) {
      this.expandedActions.delete(id);
    } else {
      this.expandedActions.add(id);
    }
    this.requestUpdate();
  }

  private onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.sendMessage();
    }
  }

  private onMessagesScroll(): void {
    const list = this.querySelector('.chat-messages');
    if (!(list instanceof HTMLElement)) {
      return;
    }
    const remaining = list.scrollHeight - list.scrollTop - list.clientHeight;
    this.stickToBottom = remaining < 80;
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  protected override updated(): void {
    if (!this.stickToBottom) {
      return;
    }
    const list = this.querySelector('.chat-messages');
    if (list instanceof HTMLElement) {
      list.scrollTop = list.scrollHeight;
    }
  }

  override render(): TemplateResult {
    if (!this.conversationId) {
      return html`<div class="chat-shell">
        <p class="chat-error">${this.error}</p>
      </div>`;
    }
    return html`
      <div class="chat-shell">
        ${this.renderHeader()} ${this.renderError()}
        <div class="chat-body">
          ${this.renderSidebar()}
          <div
            class="chat-backdrop ${this.sidebarOpen ? 'open' : ''}"
            @click="${() => {
              this.sidebarOpen = false;
              this.requestUpdate();
            }}"
          ></div>
          <div class="chat-main">
            ${this.renderMessages()} ${this.renderComposer()}
          </div>
        </div>
      </div>
    `;
  }

  private renderHeader(): TemplateResult {
    const title = this.snapshot?.title || 'Conversation';
    const model = this.snapshot?.model ?? '';
    const status = this.snapshot?.status ?? 'idle';
    return html`
      <header class="chat-header">
        <h1>${title}</h1>            
        
        ${model ? html`<p class="chat-badge">${model}</p>` : nothing}
        <p class="chat-badge status-${status}">${status}</p>
        <p class="chat-badge conn-${this.wsState}">
          ${this.wsState}
        </p>
        <button
          class="chat-menu-btn"
          data-testid="chat-menu"
          title="Threads"
          @click="${() => {
            this.sidebarOpen = !this.sidebarOpen;
            this.requestUpdate();
          }}"
        >
          <span class="mdi mdi-list-box"></span>
          Threads
        </button>

        </div>
        ${
          status === 'thinking'
            ? html`<button
                class="chat-interrupt"
                data-testid="chat-interrupt"
                @click="${() => void this.interrupt()}"
              >
                Stop
              </button>`
            : nothing
        }
      </header>
    `;
  }

  private renderError(): TemplateResult | typeof nothing {
    if (!this.error) {
      return nothing;
    }
    return html`<p class="chat-error" role="alert">${this.error}</p>`;
  }

  private renderSidebar(): TemplateResult {
    const threads = this.snapshot?.threads ?? [];
    return html`
      <aside
        class="chat-sidebar ${this.sidebarOpen ? 'open' : ''}"
        data-testid="chat-sidebar"
      >
        <div class="chat-sidebar-head">
          <h2>Threads</h2>
          <button
            class="chat-new-thread"
            data-testid="chat-new-thread"
            ?disabled="${this.creatingThread}"
            @click="${() => void this.newThread()}"
          >
            New
          </button>
        </div>
        <ul class="chat-thread-list">
          ${threads.map((thread) => this.renderThreadItem(thread))}
        </ul>
      </aside>
    `;
  }

  private renderThreadItem(thread: ThreadInfo): TemplateResult {
    const active = thread.slug === this.activeThread;
    return html`
      <li>
        <button
          class="chat-thread ${active ? 'active' : ''}"
          data-thread="${thread.slug}"
          data-testid="chat-thread"
          @click="${() => this.selectThread(thread.slug)}"
        >
          <span class="chat-thread-title">${thread.title}</span>
          <span class="chat-thread-count">${thread.message_count}</span>
        </button>
      </li>
    `;
  }

  private renderMessages(): TemplateResult {
    if (this.loadingThread) {
      return html`<div
        class="chat-messages"
        data-testid="chat-messages"
        @scroll="${() => this.onMessagesScroll()}"
      >
        <p class="chat-empty">Loading thread…</p>
      </div>`;
    }
    const visible = this.entries.filter((entry) => entry.type !== 'thread');
    const showStreaming =
      this.streaming.thread === this.activeThread &&
      (this.streaming.content || this.streaming.reasoning);
    return html`
      <div
        class="chat-messages"
        data-testid="chat-messages"
        @scroll="${() => this.onMessagesScroll()}"
      >
        ${visible.length === 0 && !showStreaming
          ? html`<p class="chat-empty">
              No messages yet. Say something to start.
            </p>`
          : nothing}
        ${visible.map((entry) => this.renderEntry(entry))}
        ${showStreaming ? this.renderStreaming() : nothing}
      </div>
    `;
  }

  private renderEntry(entry: EntryInfo): TemplateResult | typeof nothing {
    if (entry.type === 'message') {
      return this.renderMessage(entry);
    }
    if (entry.type === 'action') {
      return this.renderAction(entry);
    }
    return nothing;
  }

  private renderMessage(entry: ChatEntryInfo): TemplateResult {
    const role = entry.message.role;
    const expanded = this.expandedThoughts.has(entry.id);
    const reasoning = entry.message.reasoning;
    return html`
      <div class="chat-msg role-${role}">
        <div class="chat-bubble">
          ${entry.author
            ? html`<span class="chat-author">${entry.author}</span>`
            : nothing}
          <div class="chat-text">${entry.message.content}</div>
          ${reasoning
            ? html`<div class="chat-thoughts">
                <button
                  class="chat-thoughts-toggle"
                  data-testid="chat-thoughts-toggle"
                  @click="${() => this.toggleThoughts(entry.id)}"
                >
                  ${expanded ? 'Hide' : 'Show'} thoughts
                  (${formatCount(reasoning.length)} chars)
                </button>
                ${expanded
                  ? html`<pre class="chat-thoughts-body">${reasoning}</pre>`
                  : nothing}
              </div>`
            : nothing}
          ${this.renderUsage(entry)}
        </div>
      </div>
    `;
  }

  private renderUsage(entry: ChatEntryInfo): TemplateResult | typeof nothing {
    const usage = entry.usage;
    if (!usage) {
      return nothing;
    }
    return html`<div class="chat-usage" data-testid="chat-usage">
      <span title="Input tokens">${formatCount(usage.prompt_tokens)} in</span>
      <span title="Output tokens"
        >${formatCount(usage.completion_tokens)} out</span
      >
      <span class="chat-cost" title="Reported cost"
        >${formatCost(usage.cost)}</span
      >
    </div>`;
  }

  private renderStreaming(): TemplateResult {
    const reasoning = this.streaming.reasoning;
    return html`
      <div class="chat-msg role-assistant streaming">
        <div class="chat-bubble">
          ${reasoning
            ? html`<pre class="chat-thoughts-body">${reasoning}</pre>`
            : nothing}
          <div class="chat-text">
            ${this.streaming.content}<span class="chat-cursor">▌</span>
          </div>
        </div>
      </div>
    `;
  }

  private renderAction(entry: ActionEntryInfo): TemplateResult {
    const expanded = this.expandedActions.has(entry.id);
    return html`
      <div class="chat-action status-${entry.status}">
        <button
          class="chat-action-head"
          @click="${() => this.toggleAction(entry.id)}"
        >
          <span class="chat-action-name">${entry.name}</span>
          <span class="chat-action-status">${entry.status}</span>
          <span class="chat-action-time">${entry.duration.toFixed(2)}s</span>
        </button>
        ${expanded
          ? html`<div class="chat-action-body">
              <pre class="chat-action-args">
${JSON.stringify(entry.arguments, null, 2)}</pre
              >
              <pre class="chat-action-result">${entry.result}</pre>
            </div>`
          : nothing}
      </div>
    `;
  }

  private renderComposer(): TemplateResult {
    const noThread = !this.activeThread;
    const canSend = !noThread && this.draft.trim().length > 0;
    return html`
      <form
        class="chat-composer"
        @submit="${(event: Event) => {
          event.preventDefault();
          void this.sendMessage();
        }}"
      >
        <textarea
          class="chat-input"
          data-testid="chat-input"
          rows="2"
          placeholder="Type a message…"
          .value="${this.draft}"
          ?disabled="${noThread}"
          @input="${(event: Event) => {
            const target = event.target;
            if (target instanceof HTMLTextAreaElement) {
              this.draft = target.value;
              this.requestUpdate();
            }
          }}"
          @keydown="${(event: KeyboardEvent) => this.onComposerKeydown(event)}"
        ></textarea>
        <button
          class="chat-send"
          data-testid="chat-send"
          type="submit"
          ?disabled="${!canSend}"
        >
          Send
        </button>
      </form>
    `;
  }
}

function describeError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function formatCount(value: number): string {
  if (value >= 10_000) {
    return `${Math.round(value / 1000)}k`;
  }
  return String(value);
}

function formatCost(cost: number | null): string {
  if (cost === null) {
    return 'cost unknown';
  }
  if (cost === 0) {
    return '$0';
  }
  const digits = cost < 0.01 ? 5 : 4;
  return `$${cost.toFixed(digits)}`;
}

customElements.define('conversation-chat', ConversationChat);
