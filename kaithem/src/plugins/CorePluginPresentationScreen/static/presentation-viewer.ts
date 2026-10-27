// Presentation viewer: a bare PPTX canvas driven entirely by commands from
// the server.  It never sends slides back; every connected viewer receives
// the same load/stop/next/prev/goto commands.

import { LitElement, html } from 'lit';
import { createPptxViewer } from 'pptx-vanilla-viewer';
import type { PptxViewerInstance } from 'pptx-vanilla-viewer';

import {
  errorMessage,
  fileUrl,
  screenRefFromUrl,
} from './presentation-api';
import type { ScreenRef, ViewerCommand } from './presentation-api';

const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 10_000;

export class PresentationViewer extends LitElement {
  private ref: ScreenRef | null = null;
  private viewer: PptxViewerInstance | null = null;
  private container: HTMLElement | null = null;

  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private reconnectDelay = RECONNECT_MIN_MS;
  private shuttingDown = false;
  private denied = false;

  private connected = false;
  private playingFile = '';
  private errorText = '';
  private loading = false;
  private loadToken = 0;

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override firstUpdated(): void {
    const container = this.querySelector<HTMLElement>('.ps-viewer__stage');
    if (!container) {
      throw new Error('Viewer stage element is missing');
    }
    this.container = container;

    try {
      this.ref = screenRefFromUrl();
    } catch (error) {
      this.errorText = errorMessage(error);
      this.requestUpdate();
      return;
    }

    document.title = `${this.ref.resource} – Presentation`;
    this.connect();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.shuttingDown = true;
    this.clearReconnect();
    if (this.socket) {
      this.socket.close(1000);
      this.socket = null;
    }
    this.destroyViewer();
  }

  // -- WebSocket ---------------------------------------------------------

  private connect(): void {
    if (!this.ref || this.shuttingDown) {
      return;
    }
    const protocol = globalThis.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url =
      `${protocol}//${globalThis.location.host}/presentation-screen/ws/` +
      `${encodeURIComponent(this.ref.module)}/` +
      `${encodeURIComponent(this.ref.resource)}`;

    const socket = new WebSocket(url);
    this.socket = socket;

    socket.addEventListener('open', () => {
      this.connected = true;
      this.reconnectDelay = RECONNECT_MIN_MS;
      this.requestUpdate();
    });

    socket.addEventListener('message', (event) => {
      let command: ViewerCommand;
      try {
        command = JSON.parse(event.data as string) as ViewerCommand;
      } catch {
        return;
      }
      if (command.action === 'ready') {
        this.connected = true;
        this.requestUpdate();
        return;
      }
      void this.handleCommand(command);
    });

    socket.addEventListener('close', (event) => {
      this.connected = false;
      this.socket = null;
      if (event.code === 1008) {
        this.denied = true;
        this.errorText = 'Access denied: viewing requires an admin login.';
        this.requestUpdate();
        return;
      }
      this.requestUpdate();
      this.scheduleReconnect();
    });

    socket.addEventListener('error', () => {
      // The close event that follows does the reconnect bookkeeping.
      this.connected = false;
      this.requestUpdate();
    });
  }

  private scheduleReconnect(): void {
    if (this.shuttingDown || this.denied || this.reconnectTimer !== null) {
      return;
    }
    this.reconnectTimer = globalThis.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectDelay);
    this.reconnectDelay = Math.min(
      this.reconnectDelay * 2,
      RECONNECT_MAX_MS
    );
  }

  private clearReconnect(): void {
    if (this.reconnectTimer !== null) {
      globalThis.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  // -- Commands ----------------------------------------------------------

  private async handleCommand(command: ViewerCommand): Promise<void> {
    try {
      switch (command.action) {
        case 'load': {
          await this.load(command.file ?? '');
          break;
        }
        case 'stop': {
          this.stop();
          break;
        }
        case 'next': {
          this.viewer?.next();
          break;
        }
        case 'prev': {
          this.viewer?.prev();
          break;
        }
        case 'goto': {
          if (typeof command.slide === 'number') {
            this.viewer?.goToSlide(command.slide);
          }
          break;
        }
        default: {
          break;
        }
      }
    } catch (error) {
      this.errorText = errorMessage(error);
      this.requestUpdate();
    }
  }

  private ensureViewer(): PptxViewerInstance {
    if (this.viewer) {
      return this.viewer;
    }
    if (!this.container) {
      throw new Error('Viewer stage element is missing');
    }
    this.viewer = createPptxViewer(this.container, {
      editable: false,
      readOnly: true,
      showToolbar: false,
      showThumbnails: false,
      showInspector: false,
      showCompatibilityToasts: false,
      customization: {
        hiddenPanels: [
          'titleBar',
          'statusBar',
          'slidesPane',
          'quickAccessToolbar',
          'notes',
          'inspector',
          'selectionPane',
          'findReplace',
          'accessibilityPane',
          'comparePane',
        ],
      },
      onError: (message) => {
        this.errorText = message;
        this.requestUpdate();
      },
    });
    return this.viewer;
  }

  private async load(filename: string): Promise<void> {
    if (!this.ref) {
      return;
    }
    if (!filename) {
      this.errorText = 'Load command did not include a file.';
      this.requestUpdate();
      return;
    }

    const token = ++this.loadToken;
    this.loading = true;
    this.errorText = '';
    this.playingFile = filename;
    this.requestUpdate();

    try {
      const viewer = this.ensureViewer();
      await viewer.loadUrl(fileUrl(this.ref, filename));
      if (token !== this.loadToken) {
        return;
      }
      viewer.goToSlide(0);
    } catch (error) {
      if (token === this.loadToken) {
        this.errorText = `Could not load ${filename}: ${errorMessage(error)}`;
      }
    } finally {
      if (token === this.loadToken) {
        this.loading = false;
        this.requestUpdate();
      }
    }
  }

  private stop(): void {
    this.loadToken += 1;
    this.loading = false;
    this.playingFile = '';
    this.errorText = '';
    this.destroyViewer();
    this.requestUpdate();
  }

  private destroyViewer(): void {
    if (this.viewer) {
      try {
        this.viewer.destroy();
      } catch {
        // Destroying is best effort; the container is cleared anyway.
      }
      this.viewer = null;
    }
    if (this.container) {
      this.container.replaceChildren();
    }
  }

  // -- Rendering ---------------------------------------------------------

  override render() {
    const showPlaceholder = !this.playingFile && !this.errorText;
    return html`
      <div class="ps-viewer">
        <div class="ps-viewer__stage"></div>
        ${showPlaceholder
          ? html`<div class="ps-viewer__empty" data-testid="viewer-idle">
              Waiting for a presentation…
            </div>`
          : ''}
        ${this.errorText
          ? html`<div class="ps-viewer__error" data-testid="viewer-error">
              ${this.errorText}
            </div>`
          : ''}
        ${!this.connected && !this.denied
          ? html`<div class="ps-viewer__badge" data-testid="viewer-offline">
              Reconnecting…
            </div>`
          : ''}
      </div>
    `;
  }
}

customElements.define('presentation-viewer', PresentationViewer);
