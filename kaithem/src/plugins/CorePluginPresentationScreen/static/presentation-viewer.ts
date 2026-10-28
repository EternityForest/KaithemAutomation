// Presentation viewer: a bare PPTX canvas that mirrors the server's playback
// state.  It never writes state back: next/prev move the local view only, and
// any server-side change replaces the local state wholesale.

import 'pptx-vanilla-viewer/styles.css';

import { LitElement, html } from 'lit';
import { createPptxViewer } from 'pptx-vanilla-viewer';
import type { PptxViewerInstance } from 'pptx-vanilla-viewer';
// The engine only plays slide transitions in fullscreen presentation mode, so
// this mirrored screen drives the engine's own overlay helper directly.
import { playTransitionOverlay } from 'pptx-vanilla-viewer/internals';

import {
  errorMessage,
  fileUrl,
  normalizeState,
  screenRefFromUrl,
  stoppedState,
} from './presentation-api.ts';
import type {
  PresentationState,
  ScreenRef,
  ViewerMessage,
} from './presentation-api.ts';

const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 10_000;

const NEXT_KEYS = new Set(['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter']);
const PREV_KEYS = new Set(['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace']);

export class PresentationViewer extends LitElement {
  private ref: ScreenRef | null = null;
  private viewer: PptxViewerInstance | null = null;
  private container: HTMLElement | null = null;

  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = RECONNECT_MIN_MS;
  private shuttingDown = false;
  private denied = false;

  private connected = false;
  private state: PresentationState = stoppedState();
  private slideCount = 0;
  private errorText = '';
  private loading = false;
  private loadToken = 0;
  /** Slide already placed on screen, or null right after a deck loads. */
  private shownIndex: number | null = null;
  /** Tears down a still-playing transition overlay. */
  private transitionCancel: (() => void) | null = null;

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    globalThis.addEventListener('keydown', this.onKeyDown);
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    globalThis.removeEventListener('keydown', this.onKeyDown);
    this.shuttingDown = true;
    this.clearReconnect();
    if (this.socket) {
      this.socket.close(1000);
      this.socket = null;
    }
    this.destroyViewer();
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

  /**
   * Local-only slide navigation.  The server never learns about these
   * keypresses, so the screen keeps whatever state it already had.
   */
  private onKeyDown = (event: KeyboardEvent): void => {
    if (event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }
    if (NEXT_KEYS.has(event.key)) {
      event.preventDefault();
      this.stepSlide(1);
    } else if (PREV_KEYS.has(event.key)) {
      event.preventDefault();
      this.stepSlide(-1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      this.showSlide(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      this.showSlide(Number.MAX_SAFE_INTEGER);
    }
  };

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
      let message: ViewerMessage;
      try {
        message = JSON.parse(event.data as string) as ViewerMessage;
      } catch {
        return;
      }
      if (message.action === 'state') {
        this.connected = true;
        void this.applyState(normalizeState(message.state));
      }
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

  // -- State -------------------------------------------------------------

  /** Adopt the server's state in full, then show it. */
  private async applyState(state: PresentationState): Promise<void> {
    if (state.type === 'none') {
      this.state = stoppedState();
      this.stop();
      return;
    }

    if (state.file !== this.playingFile()) {
      this.state = state;
      await this.load(state.file);
      return;
    }

    this.state = state;
    this.showSlide(state.slide);
  }

  private playingFile(): string {
    return this.state.type === 'pptx' ? this.state.file : '';
  }

  /** Local-only navigation; the server is not told about it. */
  private stepSlide(delta: number): void {
    if (this.state.type !== 'pptx') {
      return;
    }
    this.showSlide(this.state.slide + delta);
  }

  /** Clamp to the deck length and move both the engine and local state. */
  private showSlide(index: number): void {
    if (this.state.type !== 'pptx' || !this.viewer) {
      return;
    }
    const last = Math.max(0, this.slideCount - 1);
    const target = Math.min(Math.max(0, Math.floor(index)), last);
    this.state = { ...this.state, slide: target };

    const current = this.viewer.getCurrentSlide();
    // Mirror the engine's own rule: forward replays the incoming slide's
    // transition, backward the outgoing slide's.  Nothing animates on the
    // first placement of a freshly-loaded deck.
    const animating = this.shownIndex !== null && target !== current;
    const wrap = animating ? this.stageWrap() : null;
    const outgoing = wrap ? this.stageNode(wrap) : null;
    const transition = animating
      ? this.viewer.getSlide(target > current ? target : current)?.transition
      : undefined;

    this.cancelTransition();

    if (target === current + 1) {
      this.viewer.goNext();
    }
    else {
      this.viewer.goToSlide(target);
    }

    // Navigation re-renders the stage synchronously: the node captured above
    // is now detached, and the live stage is the freshly-rendered one.
    if (wrap && outgoing && transition?.type && transition.type !== 'none') {
      const incoming = this.stageNode(wrap);
      if (incoming) {
        this.transitionCancel = playTransitionOverlay({
          doc: document,
          stageWrap: wrap,
          outgoing,
          incoming: incoming.cloneNode(true) as HTMLElement,
          transition,
          outgoingSlide: this.viewer.getSlide(current),
          incomingSlide: this.viewer.getSlide(target),
          onDone: () => {
            this.transitionCancel = null;
          },
        });
      }
    }

    this.shownIndex = target;
    this.requestUpdate();
  }

  private stageWrap(): HTMLElement | null {
    return (
      this.container?.querySelector<HTMLElement>('.pptxv-stage-wrap') ?? null
    );
  }

  private stageNode(wrap: HTMLElement): HTMLElement | null {
    return wrap.querySelector<HTMLElement>('.pptxv-stage');
  }

  private cancelTransition(): void {
    if (this.transitionCancel) {
      this.transitionCancel();
      this.transitionCancel = null;
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
      showFormatToolbar: false,
      showCompatibilityToasts: false,
      // No chrome and no decorative margin: the slide fills the letterboxed
      // black stage as large as it can and is centred.
      fitPadding: { horizontal: 0, vertical: 0 },
      maxFitScale: null,
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
      onLoad: ({ slideCount }) => {
        this.slideCount = slideCount;
        if (this.state.type === 'pptx') {
          this.showSlide(this.state.slide);
        }
        this.requestUpdate();
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

    const token = ++this.loadToken;
    this.loading = true;
    this.errorText = '';
    this.slideCount = 0;
    this.cancelTransition();
    this.shownIndex = null;
    this.requestUpdate();

    try {
      const viewer = this.ensureViewer();
      await viewer.loadUrl(fileUrl(this.ref, filename));
      if (token !== this.loadToken) {
        return;
      }
      this.showSlide(this.state.type === 'pptx' ? this.state.slide : 0);
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
    this.slideCount = 0;
    this.errorText = '';
    this.destroyViewer();
    this.requestUpdate();
  }

  private destroyViewer(): void {
    this.cancelTransition();
    this.shownIndex = null;
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
    const idle = this.state.type === 'none' && !this.errorText;
    return html`
      <div class="ps-viewer">
        <div class="ps-viewer__stage"></div>
        ${idle
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
