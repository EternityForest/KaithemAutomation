// Bluetooth console UI.
//
// State arrives over /bluetooth/ws; mutating actions use the REST API.  The
// server's BlueZ wrapper emits pairing prompts as agent_request events, which
// this page renders as modals and answers with agent_response messages.

import { LitElement, html, nothing } from 'lit';
import type { TemplateResult } from 'lit';

import {
  connectDevice,
  deleteDeviceConfig,
  disconnectDevice,
  forgetDevice,
  pairDevice,
  refreshSnapshot,
  setAdapterProperties,
  setDeviceConfig,
  setDiscovering,
  setTrusted,
} from './bluetooth-api.ts';
import type {
  AdapterPropertyValue,
  AgentRequest,
  BluetoothAdapter,
  BluetoothDevice,
  BluetoothDeviceConfig,
  BluetoothSnapshot,
} from './bluetooth-api.ts';

const EMPTY_SNAPSHOT: BluetoothSnapshot = {
  available: false,
  error: 'Connecting to Bluetooth service…',
  agent_registered: false,
  agent_error: null,
  adapters: [],
  adapter: null,
  devices: [],
  revision: 0,
  updated: 0,
};

type SocketMessage = {
  type?: string;
  snapshot?: BluetoothSnapshot;
  agent_requests?: AgentRequest[];
  request?: AgentRequest;
  address?: string;
  config?: BluetoothDeviceConfig;
  id?: string;
  accepted?: boolean;
};

export class BluetoothConsole extends LitElement {
  private snapshot: BluetoothSnapshot = { ...EMPTY_SNAPSHOT };
  private ws: WebSocket | null = null;
  private wsStatus: 'connecting' | 'connected' | 'disconnected' = 'connecting';
  private reconnectDelay = 2000;
  private reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
  private destroyed = false;

  private busy = '';
  private error = '';
  private agentRequests: AgentRequest[] = [];
  private promptValues = new Map<string, string>();
  private displays: AgentRequest[] = [];

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    this.connectSocket();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.destroyed = true;
    if (this.reconnectTimer !== null) {
      globalThis.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  // ------------------------------------------------------------------
  // Socket
  // ------------------------------------------------------------------

  private connectSocket(): void {
    if (this.destroyed) {
      return;
    }
    const protocol = globalThis.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(
      `${protocol}//${globalThis.location.host}/bluetooth/ws`,
    );
    this.ws = socket;
    this.wsStatus = 'connecting';
    this.requestUpdate();

    socket.addEventListener('open', () => {
      if (this.ws !== socket) {
        return;
      }
      this.wsStatus = 'connected';
      this.reconnectDelay = 2000;
      this.requestUpdate();
    });

    socket.addEventListener('close', () => {
      if (this.ws === socket) {
        this.ws = null;
      }
      if (this.destroyed) {
        return;
      }
      this.wsStatus = 'disconnected';
      this.scheduleReconnect();
      this.requestUpdate();
    });

    socket.addEventListener('error', () => {
      this.error = 'WebSocket connection failed';
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
    this.reconnectDelay = Math.min(this.reconnectDelay * 1.7, 15_000);
    this.reconnectTimer = globalThis.setTimeout(() => {
      this.reconnectTimer = null;
      this.connectSocket();
    }, delay);
  }

  private handleSocketMessage(raw: string): void {
    let message: SocketMessage;
    try {
      message = JSON.parse(raw) as SocketMessage;
    } catch {
      return;
    }

    if (message.type === 'snapshot' && message.snapshot) {
      this.snapshot = message.snapshot;
      if (Array.isArray(message.agent_requests)) {
        this.agentRequests = message.agent_requests;
      }
    } else if (
      message.type === 'config' &&
      typeof message.address === 'string' &&
      message.config
    ) {
      const address = message.address.toUpperCase();
      const config = message.config;
      this.snapshot = {
        ...this.snapshot,
        devices: this.snapshot.devices.map((device) =>
          device.address.toUpperCase() === address
            ? { ...device, config }
            : device,
        ),
      };
    } else if (message.type === 'agent_request' && message.request) {
      const request = message.request;
      if (!this.agentRequests.some((item) => item.id === request.id)) {
        this.agentRequests = [...this.agentRequests, request];
      }
    } else if (message.type === 'agent_display' && message.request) {
      const request = message.request;
      // DisplayPasskey is repeated as digits are entered; keep only the latest.
      this.displays = [
        ...this.displays.filter(
          (item) =>
            !(item.kind === request.kind && item.device_path === request.device_path),
        ),
        request,
      ].slice(-5);
    } else if (message.type === 'agent_resolved' && message.id) {
      this.agentRequests = this.agentRequests.filter(
        (item) => item.id !== message.id,
      );
      this.displays = this.displays.filter((item) => item.id !== message.id);
      this.promptValues.delete(message.id);
    } else if (message.type === 'error') {
      this.error = 'A pairing prompt was already resolved';
    }
    this.requestUpdate();
  }

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  private async run(
    key: string,
    action: () => Promise<BluetoothSnapshot>,
  ): Promise<void> {
    this.busy = key;
    this.error = '';
    this.requestUpdate();
    try {
      this.snapshot = await action();
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.busy = '';
      this.requestUpdate();
    }
  }

  private toggleScan(): void {
    const adapter = this.snapshot.adapter;
    if (!adapter) {
      return;
    }
    void this.run('scan', () => setDiscovering(!adapter.discovering));
  }

  private refresh(): void {
    void this.run('refresh', refreshSnapshot);
  }

  private pair(device: BluetoothDevice): void {
    void this.run(`pair:${device.address}`, () => pairDevice(device.address));
  }

  private connect(device: BluetoothDevice): void {
    void this.run(`connect:${device.address}`, () =>
      connectDevice(device.address),
    );
  }

  private disconnect(device: BluetoothDevice): void {
    void this.run(`disconnect:${device.address}`, () =>
      disconnectDevice(device.address),
    );
  }

  private toggleTrust(device: BluetoothDevice): void {
    void this.run(`trust:${device.address}`, () =>
      setTrusted(device.address, !device.trusted),
    );
  }

  private forget(device: BluetoothDevice): void {
    const label = this.deviceLabel(device);
    if (
      !globalThis.confirm(
        `Forget ${label}? The pairing and its saved settings will be removed.`,
      )
    ) {
      return;
    }
    void this.run(`forget:${device.address}`, () =>
      forgetDevice(device.address),
    );
  }

  private setDeviceFlag(
    device: BluetoothDevice,
    key: 'auto_connect' | 'alerts',
    value: boolean,
  ): void {
    const values: Partial<BluetoothDeviceConfig> =
      key === 'auto_connect'
        ? { auto_connect: value }
        : { alerts: value };
    void this.run(`config:${device.address}:${key}`, async () => {
      const result = await setDeviceConfig(device.address, values);
      return result.snapshot;
    });
  }

  private renameDevice(device: BluetoothDevice): void {
    const current = device.config?.name ?? '';
    const next = globalThis.prompt(
      `Local name for ${this.deviceLabel(device)} (blank to clear)`,
      current,
    );
    if (next === null) {
      return;
    }
    const trimmed = next.trim();
    if (trimmed === current) {
      return;
    }
    void this.run(`name:${device.address}`, async () => {
      const result = await setDeviceConfig(device.address, {
        name: trimmed === '' ? null : trimmed,
      });
      return result.snapshot;
    });
  }

  private removeSettings(device: BluetoothDevice): void {
    const label = this.deviceLabel(device);
    if (
      !globalThis.confirm(
        `Remove saved settings for ${label}? This deletes its ` +
          'auto-connect, alerts, and local name configuration.',
      )
    ) {
      return;
    }
    void this.run(`settings:${device.address}`, () =>
      deleteDeviceConfig(device.address),
    );
  }

  private deviceLabel(device: BluetoothDevice): string {
    return (
      device.config?.name || device.alias || device.name || 'Unknown device'
    );
  }

  private setAdapterFlag(
    adapter: BluetoothAdapter,
    key: 'Powered' | 'Discoverable' | 'Pairable' | 'Advertising',
    value: boolean,
  ): void {
    void this.run(`adapter:${adapter.path}:${key}`, () =>
      setAdapterProperties(this.adapterId(adapter), { [key]: value }),
    );
  }

  private makeConnectable(adapter: BluetoothAdapter): void {
    const values: Record<string, AdapterPropertyValue> = {
      Powered: true,
      Discoverable: true,
      Pairable: true,
    };
    if (adapter.le_advertising) {
      values.Advertising = true;
    }
    void this.run(`connectable:${adapter.path}`, () =>
      setAdapterProperties(this.adapterId(adapter), values),
    );
  }

  private renameAdapter(adapter: BluetoothAdapter): void {
    const current = adapter.alias || adapter.name || '';
    const next = globalThis.prompt('Controller name', current);
    if (next === null) {
      return;
    }
    const trimmed = next.trim();
    if (trimmed === '' || trimmed === current) {
      return;
    }
    void this.run(`rename:${adapter.path}`, () =>
      setAdapterProperties(this.adapterId(adapter), { Alias: trimmed }),
    );
  }

  private adapterId(adapter: BluetoothAdapter): string {
    return adapter.address || adapter.path;
  }

  private setPromptValue(request: AgentRequest, value: string): void {
    this.promptValues.set(request.id, value);
    this.requestUpdate();
  }

  private respond(request: AgentRequest, accepted: boolean): void {
    const socket = this.ws;
    if (socket === null || socket.readyState !== WebSocket.OPEN) {
      this.error = 'Not connected to the server; cannot answer the prompt';
      this.requestUpdate();
      return;
    }

    const value = (this.promptValues.get(request.id) ?? '').trim();
    if (accepted && request.kind === 'pin' && value === '') {
      this.error = 'Enter the PIN shown by the device';
      this.requestUpdate();
      return;
    }
    if (accepted && request.kind === 'passkey' && !/^\d+$/.test(value)) {
      this.error = 'Enter a numeric passkey';
      this.requestUpdate();
      return;
    }

    socket.send(
      JSON.stringify({
        type: 'agent_response',
        id: request.id,
        accepted,
        value,
      }),
    );
    this.agentRequests = this.agentRequests.filter(
      (item) => item.id !== request.id,
    );
    this.promptValues.delete(request.id);
    this.requestUpdate();
  }

  private dismissDisplay(request: AgentRequest): void {
    this.displays = this.displays.filter((item) => item.id !== request.id);
    this.requestUpdate();
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  override render(): TemplateResult {
    return html`
      <main class="bt-shell">
        <header class="bt-header">
          <div>
            <h1>Bluetooth</h1>
          </div>
          <span class="bt-connection ${this.wsStatus}">
            ${this.wsStatus === 'connected'
              ? 'Live'
              : this.wsStatus === 'connecting'
                ? 'Connecting…'
                : 'Disconnected'}
          </span>
        </header>

        ${this.error ? html`<p class="bt-error">${this.error}</p>` : nothing}
        ${this.renderUnavailable()}
        ${this.renderControllers()}
        ${this.renderToolbar()}
        ${this.renderDevices()}
      </main>
      ${this.renderPrompts()}
      ${this.renderDisplays()}
    `;
  }

  private renderUnavailable(): TemplateResult | typeof nothing {
    if (this.snapshot.available) {
      return nothing;
    }
    return html`
      <section class="bt-notice error">
        <strong>Bluetooth is not available.</strong>
        <span>${this.snapshot.error || 'Could not reach BlueZ over D-Bus.'}</span>
      </section>
    `;
  }

  private renderControllers(): TemplateResult {
    if (this.snapshot.adapters.length === 0) {
      return html`
        <section class="bt-notice">
          <strong>No Bluetooth controllers found.</strong>
          <span>BlueZ did not report any adapters.</span>
        </section>
      `;
    }
    return html`
      <section class="bt-controllers">
        <h2 class="bt-section-title">Controllers</h2>
        <div class="bt-controller-list">
          ${this.snapshot.adapters.map((adapter) =>
            this.renderController(adapter),
          )}
        </div>
      </section>
      ${this.snapshot.agent_registered
        ? nothing
        : html`
            <section class="bt-notice">
              <strong>Pairing prompts are unavailable.</strong>
              <span>
                ${this.snapshot.agent_error ||
                'Could not register a BlueZ pairing agent.'}
              </span>
            </section>
          `}
    `;
  }

  private renderController(adapter: BluetoothAdapter): TemplateResult {
    const label = adapter.alias || adapter.name || 'Controller';
    return html`
      <article class="bt-controller ${adapter.powered ? 'powered' : ''}">
        <div class="bt-controller-head">
          <div class="bt-controller-identity">
            <strong>${label}</strong>
            <code>${adapter.address || adapter.path}</code>
            <span class="bt-controller-path">${adapter.path}</span>
          </div>
          <div class="bt-badges">
            ${this.badge(adapter.powered ? 'Powered' : 'Off', adapter.powered)}
            ${this.badge(
              adapter.discovering ? 'Scanning' : 'Not scanning',
              adapter.discovering,
            )}
            ${adapter.le_advertising
              ? this.badge('LE advertising', adapter.advertising)
              : nothing}
          </div>
        </div>
        <div class="bt-controller-flags">
          ${this.renderFlag(adapter, 'Powered', 'Powered', adapter.powered, false)}
          ${this.renderFlag(
            adapter,
            'Discoverable',
            'Discoverable',
            adapter.discoverable,
            false,
          )}
          ${this.renderFlag(
            adapter,
            'Pairable',
            'Pairable',
            adapter.pairable,
            false,
          )}
          ${this.renderFlag(
            adapter,
            'Advertising',
            'Advertising',
            adapter.advertising,
            !adapter.le_advertising,
          )}
        </div>
        <div class="bt-controller-actions">
          <button
            class="btn primary"
            ?disabled="${this.busy === `connectable:${adapter.path}`}"
            @click="${() => this.makeConnectable(adapter)}"
          >
            ${this.busy === `connectable:${adapter.path}`
              ? 'Applying…'
              : 'Make connectable'}
          </button>
          <button
            class="btn"
            ?disabled="${this.busy === `rename:${adapter.path}`}"
            @click="${() => this.renameAdapter(adapter)}"
          >
            ${this.busy === `rename:${adapter.path}` ? 'Renaming…' : 'Set name'}
          </button>
        </div>
        ${adapter.le_advertising
          ? nothing
          : html`
              <p class="bt-controller-note">
                This controller has no LE advertising manager, so it cannot
                advertise.
              </p>
            `}
      </article>
    `;
  }

  private renderFlag(
    adapter: BluetoothAdapter,
    key: 'Powered' | 'Discoverable' | 'Pairable' | 'Advertising',
    label: string,
    checked: boolean,
    disabled: boolean,
  ): TemplateResult {
    const busyKey = `adapter:${adapter.path}:${key}`;
    return html`
      <label class="bt-flag">
        <input
          type="checkbox"
          .checked="${checked}"
          ?disabled="${disabled || this.busy === busyKey}"
          @change="${(event: Event) =>
            this.setAdapterFlag(
              adapter,
              key,
              (event.target as HTMLInputElement).checked,
            )}"
        >
        <span>${label}</span>
      </label>
    `;
  }

  private renderToolbar(): TemplateResult {
    const adapter = this.snapshot.adapter;
    return html`
      <section class="bt-toolbar">
        <button
          class="btn"
          ?disabled="${!adapter || this.busy === 'scan'}"
          @click="${this.toggleScan}"
        >
          ${this.busy === 'scan'
            ? 'Working…'
            : adapter?.discovering
              ? 'Stop scan'
              : 'Scan for devices'}
        </button>
        <button
          class="btn"
          ?disabled="${this.busy === 'refresh'}"
          @click="${this.refresh}"
        >
          ${this.busy === 'refresh' ? 'Refreshing…' : 'Refresh'}
        </button>
      </section>
    `;
  }

  private renderDevices(): TemplateResult {
    if (this.snapshot.devices.length === 0) {
      return html`
        <section class="bt-empty">
          <p>No Bluetooth devices are known yet.</p>
          <p>Start a scan to discover nearby devices.</p>
        </section>
      `;
    }
    return html`
      <section class="bt-device-list">
        ${this.snapshot.devices.map((device) => this.renderDevice(device))}
      </section>
    `;
  }

  private renderDevice(device: BluetoothDevice): TemplateResult {
    const label = this.deviceLabel(device);
    const controller = this.snapshot.adapters.find(
      (adapter) => adapter.path === device.adapter,
    );
    const config = device.config;
    return html`
      <article
        class="bt-device ${device.connected ? 'connected' : ''}
        ${device.seen ? '' : 'unseen'}"
      >
        <div class="bt-device-body">
          <div class="bt-device-title">
            <strong>${label}</strong>
            ${device.connected ? this.badge('Connected', true) : nothing}
            ${device.seen ? nothing : this.badge('Not seen', false)}
            ${device.paired ? this.badge('Paired', true) : nothing}
            ${device.trusted ? this.badge('Trusted', true) : nothing}
            ${device.blocked ? this.badge('Blocked', false) : nothing}
          </div>
          <code class="bt-address">${device.address}</code>
          <dl class="bt-details">
            <div>
              <dt>Battery</dt>
              <dd>
                ${device.battery === null ? '—' : `${device.battery}%`}
              </dd>
            </div>
            <div>
              <dt>RSSI</dt>
              <dd>${device.rssi === null ? '—' : `${device.rssi} dBm`}</dd>
            </div>
            <div>
              <dt>TX power</dt>
              <dd>
                ${device.tx_power === null ? '—' : `${device.tx_power} dBm`}
              </dd>
            </div>
            <div>
              <dt>Address type</dt>
              <dd>${device.address_type || '—'}</dd>
            </div>
            <div>
              <dt>Services</dt>
              <dd>${device.uuids.length}</dd>
            </div>
            <div>
              <dt>Controller</dt>
              <dd>
                ${controller
                  ? controller.alias || controller.name || controller.path
                  : '—'}
              </dd>
            </div>
          </dl>
          <div class="bt-device-config">
            <label class="bt-flag">
              <input
                type="checkbox"
                .checked="${config.auto_connect}"
                ?disabled="${(device.seen && !device.paired) ||
                this.busy === `config:${device.address}:auto_connect`}"
                @change="${(event: Event) =>
                  this.setDeviceFlag(
                    device,
                    'auto_connect',
                    (event.target as HTMLInputElement).checked,
                  )}"
              >
              <span>Auto-connect</span>
            </label>
            <label class="bt-flag">
              <input
                type="checkbox"
                .checked="${config.alerts}"
                ?disabled="${this.busy === `config:${device.address}:alerts`}"
                @change="${(event: Event) =>
                  this.setDeviceFlag(
                    device,
                    'alerts',
                    (event.target as HTMLInputElement).checked,
                  )}"
              >
              <span>Alerts</span>
            </label>
            <button
              class="btn"
              style="flex-basis:fit-content"
              ?disabled="${this.busy === `name:${device.address}`}"
              @click="${() => this.renameDevice(device)}"
            >
              ${this.busy === `name:${device.address}`
                ? 'Saving…'
                : config.name
                  ? 'Rename'
                  : 'Local name'}
            </button>
          </div>
        </div>
        <div class="bt-actions">
          ${device.seen
            ? html`
                ${device.paired
                  ? nothing
                  : html`
                      <button
                        class="btn"
                        ?disabled="${this.busy === `pair:${device.address}`}"
                        @click="${() => this.pair(device)}"
                      >
                        ${this.busy === `pair:${device.address}`
                          ? 'Pairing…'
                          : 'Pair'}
                      </button>
                    `}
                <button
                  class="btn"
                  ?disabled="${this.busy === `trust:${device.address}`}"
                  @click="${() => this.toggleTrust(device)}"
                >
                  ${device.trusted ? 'Untrust' : 'Trust'}
                </button>
                ${device.connected
                  ? html`
                      <button
                        class="btn"
                        ?disabled="${this.busy ===
                        `disconnect:${device.address}`}"
                        @click="${() => this.disconnect(device)}"
                      >
                        ${this.busy === `disconnect:${device.address}`
                          ? 'Disconnecting…'
                          : 'Disconnect'}
                      </button>
                    `
                  : html`
                      <button
                        class="btn"
                        ?disabled="${this.busy ===
                        `connect:${device.address}`}"
                        @click="${() => this.connect(device)}"
                      >
                        ${this.busy === `connect:${device.address}`
                          ? 'Connecting…'
                          : 'Connect'}
                      </button>
                    `}
                <button
                  class="btn danger"
                  ?disabled="${this.busy === `forget:${device.address}`}"
                  @click="${() => this.forget(device)}"
                >
                  ${this.busy === `forget:${device.address}`
                    ? 'Forgetting…'
                    : 'Forget'}
                </button>
              `
            : html`
                <p class="bt-unseen-note">
                  Out of range or unknown to BlueZ. Only the saved settings
                  can be changed here.
                </p>
                <button
                  class="btn danger"
                  ?disabled="${this.busy === `settings:${device.address}`}"
                  @click="${() => this.removeSettings(device)}"
                >
                  ${this.busy === `settings:${device.address}`
                    ? 'Removing…'
                    : 'Remove settings'}
                </button>
              `}
        </div>
      </article>
    `;
  }

  private renderPrompts(): TemplateResult | typeof nothing {
    if (this.agentRequests.length === 0) {
      return nothing;
    }
    return html`
      <div class="bt-modal-backdrop">
        ${this.agentRequests.map((request) => this.renderPrompt(request))}
      </div>
    `;
  }

  private renderPrompt(request: AgentRequest): TemplateResult {
    const value = this.promptValues.get(request.id) ?? '';
    const deviceLabel = request.name || request.address || 'Unknown device';
    return html`
      <section class="bt-modal">
        <h2>${this.promptTitle(request)}</h2>
        <p class="bt-modal-device">
          ${deviceLabel}
          ${request.address ? html`<code>${request.address}</code>` : nothing}
        </p>
        ${request.passkey === null
          ? nothing
          : html`<p class="bt-passkey">${request.passkey}</p>`}
        ${request.uuid
          ? html`<p class="bt-modal-detail">Service: <code>${request.uuid}</code></p>`
          : nothing}
        ${request.kind === 'pin' || request.kind === 'passkey'
          ? html`
              <label class="bt-prompt-field">
                <span>${request.kind === 'pin' ? 'PIN code' : 'Passkey'}</span>
                <input
                  class="bt-input"
                  type="${request.kind === 'passkey' ? 'number' : 'text'}"
                  inputmode="${request.kind === 'passkey' ? 'numeric' : 'text'}"
                  autocomplete="off"
                  .value="${value}"
                  @input="${(event: Event) =>
                    this.setPromptValue(
                      request,
                      (event.target as HTMLInputElement).value,
                    )}"
                >
              </label>
            `
          : nothing}
        <div class="bt-modal-actions">
          <button class="btn" @click="${() => this.respond(request, false)}">
            Cancel
          </button>
          <button
            class="btn primary"
            @click="${() => this.respond(request, true)}"
          >
            Accept
          </button>
        </div>
      </section>
    `;
  }

  private renderDisplays(): TemplateResult | typeof nothing {
    if (this.displays.length === 0) {
      return nothing;
    }
    return html`
      <div class="bt-display-stack">
        ${this.displays.map(
          (request) => html`
            <section class="bt-display">
              <div>
                <strong>${this.displayTitle(request)}</strong>
                <p>
                  ${request.name || request.address || request.device_path}
                </p>
                <p class="bt-passkey">
                  ${request.pin ?? request.passkey ?? '—'}
                  ${request.entered === null
                    ? nothing
                    : html`<small>${request.entered} digits entered</small>`}
                </p>
              </div>
              <button class="btn" @click="${() => this.dismissDisplay(request)}">
                Dismiss
              </button>
            </section>
          `,
        )}
      </div>
    `;
  }

  private promptTitle(request: AgentRequest): string {
    switch (request.kind) {
      case 'pin': {
        return 'Enter PIN';
      }
      case 'passkey': {
        return 'Enter passkey';
      }
      case 'confirm': {
        return 'Confirm pairing';
      }
      case 'authorize': {
        return 'Authorize device';
      }
      case 'authorize_service': {
        return 'Authorize service';
      }
      default: {
        return 'Pairing request';
      }
    }
  }

  private displayTitle(request: AgentRequest): string {
    switch (request.kind) {
      case 'display_pin': {
        return 'PIN shown by device';
      }
      case 'display_passkey': {
        return 'Passkey';
      }
      default: {
        return 'Pairing code';
      }
    }
  }

  private badge(text: string, positive: boolean): TemplateResult {
    return html`<span class="bt-badge ${positive ? 'on' : 'off'}">${text}</span>`;
  }
}

customElements.define('bluetooth-console', BluetoothConsole);
