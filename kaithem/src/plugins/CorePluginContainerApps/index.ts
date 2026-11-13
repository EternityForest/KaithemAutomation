// Container app admin page.
//
// A single page serves both management surfaces, chosen by the `type`
// query parameter:
//
//   type=app       development view: build, dev-run, action scripts
//   type=instance  admin view: start/stop/adjust one running instance
//
// The page shows status, environment and the live build/run log, backed
// by /containerapps/api.  The app itself is reached through its path
// proxy under /apps/<name>, not this page.

import { LitElement, html, nothing } from 'lit';
import type { TemplateResult } from 'lit';

import {
  ApiError,
  getApp,
  getInstance,
  runAppAction,
  runInstanceAction,
  websocketUrl,
} from './container-apps-api.ts';
import type {
  AppAction,
  AppSnapshot,
  ContainerAppSnapshot,
  InstanceAction,
  InstanceSnapshot,
  SurfaceKind,
} from './container-apps-api.ts';

const MAX_LOG_LINES = 2000;

interface ConfirmRequest {
  action: AppAction | InstanceAction;
  title: string;
  message: string;
}

export class ContainerAppAdmin extends LitElement {
  private kind: SurfaceKind = 'app';
  private module = '';
  private resource = '';
  private snapshot: ContainerAppSnapshot | null = null;
  private logLines: string[] = [];
  private busy = '';
  private error = '';
  private notice = '';
  private confirmRequest: ConfirmRequest | null = null;
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private closed = false;

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    const params = new URLSearchParams(location.search);
    this.kind = params.get('type') === 'instance' ? 'instance' : 'app';
    this.module = params.get('module') ?? '';
    this.resource = params.get('resource') ?? '';
    document.title =
      this.kind === 'instance'
        ? 'Container App Instance - Kaithem'
        : 'Container App - Kaithem';
    if (!this.module || !this.resource) {
      this.error = 'Missing module or resource in the page URL.';
      this.requestUpdate();
      return;
    }
    void this.load();
    this.connect();
  }

  override disconnectedCallback(): void {
    this.closed = true;
    this.closeSocket();
    super.disconnectedCallback();
  }

  // ------------------------------------------------------------------
  // Data
  // ------------------------------------------------------------------

  private async load(): Promise<void> {
    try {
      this.applySnapshot(await this.fetch());
    } catch (error) {
      this.error = this.describe(error);
      this.requestUpdate();
    }
  }

  private fetch(): Promise<ContainerAppSnapshot> {
    if (this.kind === 'instance') {
      return getInstance(this.module, this.resource);
    }
    return getApp(this.module, this.resource);
  }

  private applySnapshot(snapshot: ContainerAppSnapshot): void {
    this.snapshot = snapshot;
    this.logLines = snapshot.log.slice(-MAX_LOG_LINES);
    this.requestUpdate();
  }

  private describe(error: unknown): string {
    if (error instanceof ApiError) {
      return error.message;
    }
    return error instanceof Error ? error.message : String(error);
  }

  private connect(): void {
    if (this.closed) {
      return;
    }
    const socket = new WebSocket(
      websocketUrl(this.kind, this.module, this.resource)
    );
    this.socket = socket;
    socket.addEventListener('message', (event) => {
      this.handleMessage(event.data);
    });
    socket.addEventListener('close', () => {
      this.socket = null;
      if (!this.closed) {
        this.scheduleReconnect();
      }
    });
    socket.addEventListener('error', () => {
      socket.close();
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) {
      return;
    }
    this.reconnectTimer = globalThis.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 2000);
  }

  private closeSocket(): void {
    if (this.reconnectTimer !== null) {
      globalThis.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket !== null) {
      this.socket.close();
      this.socket = null;
    }
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== 'string') {
      return;
    }
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }
    if (message.event === 'snapshot') {
      this.applySnapshot(message.snapshot as unknown as ContainerAppSnapshot);
      return;
    }
    if (message.event === 'log' && typeof message.line === 'string') {
      this.logLines.push(message.line);
      if (this.logLines.length > MAX_LOG_LINES) {
        this.logLines.splice(0, this.logLines.length - MAX_LOG_LINES);
      }
      this.requestUpdate();
      return;
    }
    if (message.event === 'status' && this.snapshot) {
      this.snapshot = { ...this.snapshot, status: String(message.status) };
      this.requestUpdate();
    }
  }

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  private async perform(
    action: AppAction | InstanceAction,
    body?: Record<string, unknown>
  ): Promise<void> {
    this.busy = action;
    this.error = '';
    this.notice = '';
    this.requestUpdate();
    try {
      const snapshot =
        this.kind === 'instance'
          ? await runInstanceAction(
              this.module,
              this.resource,
              action as InstanceAction
            )
          : await runAppAction(
              this.module,
              this.resource,
              action as AppAction,
              body
            );
      this.applySnapshot(snapshot);
      this.notice = `${action} finished.`;
    } catch (error) {
      this.error = this.describe(error);
    } finally {
      this.busy = '';
      this.requestUpdate();
    }
  }

  private requestConfirm(request: ConfirmRequest): void {
    this.confirmRequest = request;
    this.requestUpdate();
  }

  private confirm(): void {
    const request = this.confirmRequest;
    if (request === null) {
      return;
    }
    this.confirmRequest = null;
    void this.perform(request.action);
  }

  private cancelConfirm(): void {
    this.confirmRequest = null;
    this.requestUpdate();
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  override render(): TemplateResult {
    return html`
      <main class="ca-shell">
        <header class="ca-header">
          <div>
            <h1 data-testid="ca-title">
              ${this.snapshot?.title || this.resource || 'Container App'}
            </h1>
            <p class="ca-subtitle">
              ${this.kind === 'instance' ? 'Instance' : 'App'} in module
              <code>${this.module}</code> · resource
              <code>${this.resource}</code>
            </p>
          </div>
          <button
            class="btn"
            data-testid="ca-refresh"
            ?disabled="${this.busy !== ''}"
            @click="${() => void this.load()}"
          >
            Refresh
          </button>
        </header>

        ${this.error
          ? html`<p class="ca-error" data-testid="ca-error">${this.error}</p>`
          : nothing}
        ${this.notice
          ? html`<p class="ca-notice" data-testid="ca-notice">
              ${this.notice}
            </p>`
          : nothing}
        ${this.renderStatus()} ${this.renderActions()} ${this.renderDetails()}
        ${this.renderLog()}
      </main>
      ${this.renderConfirmDialog()}
    `;
  }

  private renderStatus(): TemplateResult {
    const snapshot = this.snapshot;
    if (snapshot === null) {
      return html`<p data-testid="ca-loading">Loading…</p>`;
    }
    const dev = snapshot.type === 'app' && snapshot.dev;
    return html`
      <section class="ca-status">
        <span
          class="ca-badge ca-badge-${snapshot.status}"
          data-testid="ca-status"
          >${snapshot.status}</span
        >
        <span data-testid="ca-built"
          >${snapshot.built ? 'Built' : 'Not built'}</span
        >
        ${dev ? html`<span data-testid="ca-dev">Dev mode</span>` : nothing}
        ${snapshot.error
          ? html`<span class="ca-error" data-testid="ca-runtime-error"
              >${snapshot.error}</span
            >`
          : nothing}
      </section>
    `;
  }

  private renderActions(): TemplateResult {
    if (this.snapshot === null) {
      return html``;
    }
    return this.kind === 'instance'
      ? this.renderInstanceActions()
      : this.renderAppActions();
  }

  private renderAppActions(): TemplateResult {
    const snapshot = this.snapshot as AppSnapshot;
    const disabled = this.busy !== '';
    const dev = snapshot.dev;
    const built = snapshot.built;
    const scriptButtons = snapshot.scripts.map(
      (name) => html`
        <button
          class="btn"
          data-testid="ca-script-${name}"
          ?disabled="${disabled}"
          @click="${() => void this.perform('run-script', { name })}"
        >
          Run ${name}
        </button>
      `
    );
    return html`
      <section class="ca-actions" data-testid="ca-app-actions">
        <button
          class="btn"
          data-testid="ca-copy-template"
          ?disabled="${disabled || !snapshot.empty}"
          @click="${() => void this.perform('copy-template')}"
        >
          Copy Template
        </button>
        <button
          class="btn primary"
          data-testid="ca-build"
          ?disabled="${disabled}"
          @click="${() => void this.perform('build')}"
        >
          Build
        </button>
        <button
          class="btn"
          data-testid="ca-dev-mode"
          ?disabled="${disabled || dev || !built}"
          @click="${() => void this.perform('dev')}"
        >
          Dev Mode
        </button>
        <button
          class="btn"
          data-testid="ca-stop-dev"
          ?disabled="${disabled || !dev}"
          @click="${() => void this.perform('stop-dev')}"
        >
          Stop Dev Mode
        </button>
        <button
          class="btn"
          data-testid="ca-reload"
          ?disabled="${disabled}"
          @click="${() => void this.perform('reload')}"
        >
          Reload Config
        </button>
        <button
          class="btn"
          data-testid="ca-clean"
          ?disabled="${disabled}"
          @click="${() =>
            this.requestConfirm({
              action: 'clean',
              title: 'Clean build artifacts',
              message:
                'Delete the build output and its marker? The source ' +
                'project is left untouched.',
            })}"
        >
          Clean
        </button>
        <button
          class="btn danger"
          data-testid="ca-delete-runtime"
          ?disabled="${disabled}"
          @click="${() =>
            this.requestConfirm({
              action: 'delete-runtime',
              title: 'Delete runtime containers',
              message:
                'Delete this app\u2019s containers? Project files and ' +
                'build artifacts are left untouched.',
            })}"
        >
          Delete Runtime
        </button>
        ${scriptButtons}
      </section>
    `;
  }

  private renderInstanceActions(): TemplateResult {
    const snapshot = this.snapshot as InstanceSnapshot;
    const disabled = this.busy !== '';
    const running = snapshot.running;
    return html`
      <section class="ca-actions" data-testid="ca-instance-actions">
        <button
          class="btn primary"
          data-testid="ca-start"
          ?disabled="${disabled || running || !snapshot.built}"
          @click="${() => void this.perform('start')}"
        >
          Start
        </button>
        <button
          class="btn"
          data-testid="ca-stop"
          ?disabled="${disabled || !running}"
          @click="${() => void this.perform('stop')}"
        >
          Stop
        </button>
        <button
          class="btn"
          data-testid="ca-reload"
          ?disabled="${disabled}"
          @click="${() => void this.perform('reload')}"
        >
          Reload Config
        </button>
        <button
          class="btn danger"
          data-testid="ca-delete-runtime"
          ?disabled="${disabled}"
          @click="${() =>
            this.requestConfirm({
              action: 'delete-runtime',
              title: 'Delete instance containers',
              message:
                'Delete this instance\u2019s containers? Its data folder ' +
                'is left untouched.',
            })}"
        >
          Delete Runtime
        </button>
      </section>
    `;
  }

  private renderDetails(): TemplateResult {
    const snapshot = this.snapshot;
    if (snapshot === null) {
      return html``;
    }
    const envRows = Object.entries(snapshot.environment).map(
      ([key, value]) => html`
        <tr>
          <th scope="row">${key}</th>
          <td><code>${value}</code></td>
        </tr>
      `
    );
    return html`
      <section class="ca-details">
        <dl>
          <dt>App type</dt>
          <dd data-testid="ca-kind">${snapshot.kind ?? '—'}</dd>
          <dt>Run image</dt>
          <dd data-testid="ca-run-image">${snapshot.run_image ?? '—'}</dd>
          <dt>Build image</dt>
          <dd data-testid="ca-build-image">${snapshot.build_image ?? '—'}</dd>
          ${this.renderExtraDetails(snapshot)}
        </dl>
        <h2>Environment</h2>
        <table class="ca-env" data-testid="ca-environment">
          <tbody>
            ${envRows}
          </tbody>
        </table>
      </section>
    `;
  }

  private renderExtraDetails(
    snapshot: ContainerAppSnapshot
  ): TemplateResult {
    if (snapshot.type === 'instance') {
      return html`
        <dt>App</dt>
        <dd data-testid="ca-app-ref">${snapshot.app || '—'}</dd>
        <dt>URL</dt>
        <dd>
          <a href="${snapshot.url}" data-testid="ca-url">${snapshot.url}</a>
        </dd>
      `;
    }
    const preview = snapshot.dev
      ? html`<a href="${snapshot.dev_url}" data-testid="ca-dev-url"
          >${snapshot.dev_url}</a
        >`
      : '—';
    return html`
      <dt>Dev preview</dt>
      <dd data-testid="ca-dev-url">${preview}</dd>
    `;
  }

  private renderLog(): TemplateResult {
    return html`
      <section class="ca-log-section">
        <h2>Log</h2>
        <pre class="ca-log" data-testid="ca-log">${this.logLines.join('\n')}</pre>
      </section>
    `;
  }

  private renderConfirmDialog(): TemplateResult {
    const request = this.confirmRequest;
    if (request === null) {
      return html``;
    }
    return html`
      <div class="ca-modal-backdrop" data-testid="ca-confirm">
        <div class="ca-modal" role="dialog" aria-modal="true">
          <h2>${request.title}</h2>
          <p>${request.message}</p>
          <div class="ca-modal-actions">
            <button
              class="btn"
              data-testid="ca-confirm-cancel"
              @click="${() => this.cancelConfirm()}"
            >
              Cancel
            </button>
            <button
              class="btn danger"
              data-testid="ca-confirm-ok"
              @click="${() => this.confirm()}"
            >
              Confirm
            </button>
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define('container-app-admin', ContainerAppAdmin);
