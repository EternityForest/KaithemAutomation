// Container app admin page.
//
// A single page serves both management surfaces, chosen by the `type`
// query parameter:
//
//   type=app       development view: dev-run, manual scripts, template
//   type=instance  admin view: start/stop one running instance
//
// Every script in the project config becomes a launch button, and every
// script plus the app itself gets its own console.  Output is tagged with
// the script that produced it so each console only shows its own stream;
// raw chunks are written to an xterm terminal so ANSI formatting renders.
// Backed by /containerapps/api.  The app itself is reached through its
// path proxy under /apps/<name>, not this page.
//
// Building is never automatic: a build is just an ordinary script the
// developer runs by hand.

import { LitElement, html, nothing } from 'lit';
import type { TemplateResult } from 'lit';

import {
  ApiError,
  dapWebsocketUrl,
  getApp,
  getInstance,
  runAppAction,
  runInstanceAction,
  websocketUrl,
} from './container-apps-api.ts';
import type {
  AppAction,
  AppSnapshot,
  CommandSnapshot,
  ContainerAppSnapshot,
  InstanceAction,
  InstanceSnapshot,
  SurfaceKind,
} from './container-apps-api.ts';
import './console.ts';

const MAX_LOG_CHARS = 200_000;

/** The script name reserved for the project's own long running command. */
const APP_COMMAND = 'app';

/** Render a step image list, or an em dash when there are none. */
function formatImages(images: string[]): string {
  return images.length > 0 ? images.join(', ') : '—';
}

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
  private busy = '';
  private error = '';
  private notice = '';
  private confirmRequest: ConfirmRequest | null = null;
  private selectedTemplate = '';
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null =
    null;
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
    for (const command of snapshot.commands) {
      command.log =
        command.log.length > MAX_LOG_CHARS
          ? command.log.slice(-MAX_LOG_CHARS)
          : command.log;
    }
    this.snapshot = snapshot;
    if (snapshot.type === 'app' && !snapshot.templates.includes(
      this.selectedTemplate
    )) {
      this.selectedTemplate = snapshot.templates[0] ?? '';
    }
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

  private appendOutput(script: string, data: string): void {
    const command = this.findCommand(script);
    if (command === undefined) {
      return;
    }
    command.log += data;
    if (command.log.length > MAX_LOG_CHARS) {
      command.log = command.log.slice(-MAX_LOG_CHARS);
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
    if (
      message.event === 'output' &&
      typeof message.script === 'string' &&
      typeof message.data === 'string'
    ) {
      this.appendOutput(message.script, message.data);
      this.requestUpdate();
      return;
    }
    if (message.event === 'command' && typeof message.script === 'string') {
      const command = this.findCommand(message.script);
      if (command !== undefined) {
        const status = String(message.status);
        if (status === 'running' && message.script !== APP_COMMAND) {
          // The runtime clears a script's buffer on every new run.
          command.log = '';
        }
        command.status = status;
        command.exit_code =
          typeof message.exit_code === 'number' ? message.exit_code : null;
        command.dap_id =
          typeof message.dap_id === 'string' ? message.dap_id : null;
      }
      this.requestUpdate();
      return;
    }
    if (message.event === 'status' && this.snapshot) {
      this.snapshot.status = String(message.status);
      const app = this.findCommand(APP_COMMAND);
      if (app !== undefined) {
        app.status = String(message.status);
      }
      this.requestUpdate();
    }
  }

  private findCommand(name: string): CommandSnapshot | undefined {
    return this.snapshot?.commands.find((command) => command.name === name);
  }

  // ------------------------------------------------------------------
  // Command helpers
  // ------------------------------------------------------------------

  private commands(): CommandSnapshot[] {
    return this.snapshot?.commands ?? [];
  }

  private scriptCommands(): CommandSnapshot[] {
    return this.commands().filter((command) => command.name !== APP_COMMAND);
  }

  private commandStatusOf(name: string): string {
    return this.findCommand(name)?.status ?? 'stopped';
  }

  private commandRunning(name: string): boolean {
    const status = this.commandStatusOf(name);
    return status === 'running' || status === 'loading' || status === 'dev';
  }

  private foregroundBusy(): boolean {
    return this.scriptCommands().some(
      (command) => !command.background && this.commandRunning(command.name)
    );
  }

  /** Text editor URL for a running DAP bridge, or null when not running. */
  private debugUrl(command: CommandSnapshot): string | null {
    if (command.dap_id === null || command.dap_id === undefined) {
      return null;
    }
    let module = this.module;
    let resource = this.resource;
    if (this.kind === 'instance' && this.snapshot?.type === 'instance') {
      const [appModule, appResource] = this.snapshot.app.split(':');
      if (appModule && appResource) {
        module = appModule;
        resource = appResource;
      }
    }
    const fileResource = `${resource}.d/app/container-app.toml`;
    const dap = dapWebsocketUrl(command.dap_id);
    return (
      `/text-editor-plugin/edit?module=${encodeURIComponent(module)}` +
      `&resource=${encodeURIComponent(fileResource)}` +
      `&dap=${encodeURIComponent(dap)}`
    );
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
              action as InstanceAction,
              body
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
        ${this.renderConsoles()}
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
        ${snapshot.kind === null
          ? nothing
          : html`<span data-testid="ca-built"
              >${snapshot.built ? 'Built' : 'Not built'}</span
            >`}
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

  private renderScriptButtons(): TemplateResult {
    const disabled = this.busy !== '';
    const foregroundBusy = this.foregroundBusy();
    return html`${this.scriptCommands().map((command) => {
      const running = this.commandRunning(command.name);
      if (command.background) {
        return html`
          <button
            class="btn"
            data-testid="ca-script-${command.name}"
            ?disabled="${disabled || running}"
            @click="${() =>
              void this.perform('run-script', { name: command.name })}"
          >
            Start ${command.name}
          </button>
          <button
            class="btn"
            data-testid="ca-script-${command.name}-stop"
            ?disabled="${disabled || !running}"
            @click="${() =>
              void this.perform('stop-script', { name: command.name })}"
          >
            Stop ${command.name}
          </button>
        `;
      }
      return html`
        <button
          class="btn"
          data-testid="ca-script-${command.name}"
          ?disabled="${disabled || running || foregroundBusy}"
          @click="${() =>
            void this.perform('run-script', { name: command.name })}"
        >
          Run ${command.name}
        </button>
      `;
    })}`;
  }

  private renderAppActions(): TemplateResult {
    const snapshot = this.snapshot as AppSnapshot;
    const disabled = this.busy !== '';
    const dev = snapshot.dev;
    const built = snapshot.built;
    const hasApp = snapshot.kind !== null;
    return html`
      <section class="ca-actions" data-testid="ca-app-actions">
        <select
          class="ca-template"
          data-testid="ca-template"
          ?disabled="${disabled || !snapshot.empty}"
          @change="${(event: Event) => {
            this.selectedTemplate = (event.target as HTMLSelectElement).value;
          }}"
        >
          ${snapshot.templates.map(
            (name) =>
              html`<option
                value="${name}"
                ?selected="${name === this.selectedTemplate}"
              >
                ${name}
              </option>`
          )}
        </select>
        <button
          class="btn"
          data-testid="ca-copy-template"
          ?disabled="${disabled || !snapshot.empty || !this.selectedTemplate}"
          @click="${() =>
            void this.perform('copy-template', {
              template: this.selectedTemplate,
            })}"
        >
          Copy Template
        </button>
        ${hasApp
          ? html`
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
            `
          : nothing}
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
              title: 'Delete runtime containers',
              message:
                'Delete this app\u2019s containers? Project files are ' +
                'left untouched.',
            })}"
        >
          Delete Runtime
        </button>
        ${this.renderScriptButtons()}
      </section>
    `;
  }

  private renderInstanceActions(): TemplateResult {
    const snapshot = this.snapshot as InstanceSnapshot;
    const disabled = this.busy !== '';
    const running = snapshot.running;
    const hasApp = snapshot.kind !== null;
    return html`
      <section class="ca-actions" data-testid="ca-instance-actions">
        ${hasApp
          ? html`
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
            `
          : nothing}
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
        ${this.renderScriptButtons()}
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
          <dd data-testid="ca-kind">${snapshot.kind ?? 'scripts only'}</dd>
          <dt>Run images</dt>
          <dd data-testid="ca-run-image">
            ${formatImages(snapshot.run_images)}
          </dd>
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
      const url = snapshot.web
        ? html`<a href="${snapshot.url}" data-testid="ca-url"
            >${snapshot.url}</a
          >`
        : '—';
      return html`
        <dt>App</dt>
        <dd data-testid="ca-app-ref">${snapshot.app || '—'}</dd>
        <dt>URL</dt>
        <dd data-testid="ca-url">${url}</dd>
      `;
    }
    const preview = snapshot.dev && snapshot.web
      ? html`<a href="${snapshot.dev_url}" data-testid="ca-dev-url"
          >${snapshot.dev_url}</a
        >`
      : '—';
    return html`
      <dt>Dev preview</dt>
      <dd data-testid="ca-dev-url">${preview}</dd>
    `;
  }

  private renderConsoles(): TemplateResult {
    if (this.snapshot === null) {
      return html``;
    }
    const consoles = this.commands().filter((command) => {
      return (
        command.log.length > 0 || this.commandStatusOf(command.name) !== 'stopped'
      );
    });
    if (consoles.length === 0) {
      return html`
        <section class="ca-consoles" data-testid="ca-consoles">
          <p class="ca-empty">No command output yet.</p>
        </section>
      `;
    }
    return html`
      <section class="ca-consoles" data-testid="ca-consoles">
        ${consoles.map((command) => this.renderConsole(command))}
      </section>
    `;
  }

  private renderConsole(command: CommandSnapshot): TemplateResult {
    const name = command.name;
    const label = name === APP_COMMAND ? 'App' : name;
    const running = this.commandRunning(name);
    const exitCode = command.exit_code;
    const debug = this.debugUrl(command);
    return html`
      <article
        class="ca-console"
        data-testid="ca-console-${name}"
        data-script="${name}"
      >
        <header class="ca-console-header">
          <h2>${label}</h2>
          <span
            class="ca-badge ca-badge-${this.commandStatusOf(name)}"
            data-testid="ca-console-${name}-status"
            >${this.commandStatusOf(name)}</span
          >
          ${exitCode !== null && !running
            ? html`<span class="ca-exit"
                >exit ${exitCode}</span
              >`
            : nothing}
          ${command.background
            ? html`<span class="ca-tag">background</span>`
            : nothing}
          ${debug === null
            ? nothing
            : html`<a
                class="btn"
                data-testid="ca-console-${name}-debug"
                href="${debug}"
                target="_blank"
                rel="noopener"
                >Debug</a
              >`}
          <button
            class="btn danger"
            data-testid="ca-console-${name}-stop"
            ?disabled="${this.busy !== '' || !running}"
            @click="${() => void this.stopCommand(name)}"
          >
            Stop
          </button>
        </header>
        <ca-console
          class="ca-console-log"
          data-testid="ca-console-${name}-log"
          .text="${command.log}"
        ></ca-console>
      </article>
    `;
  }

  private stopCommand(name: string): Promise<void> {
    if (name === APP_COMMAND) {
      return this.perform(this.kind === 'app' ? 'stop-dev' : 'stop-app');
    }
    return this.perform('stop-script', { name });
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