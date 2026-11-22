// xterm.js console for a single container app command.
//
// The parent owns the command's output text and passes the whole buffer in
// through the `text` property on every update.  This element writes only the
// new suffix to the terminal, so output streams in incrementally even though
// the bound property is the full log so far.

import { LitElement, html } from 'lit';
import type { PropertyValues, TemplateResult } from 'lit';
import type { FitAddon } from '@xterm/addon-fit';
import type { Terminal } from '@xterm/xterm';

import { createTerminal } from '../../js/xterm-terminal.ts';

export class CaConsole extends LitElement {
  static override properties = {
    text: { type: String },
  };

  /** The command's full output so far, including ANSI escape codes. */
  // tsconfig has useDefineForClassFields on: a plain field initializer would
  // create an own instance property that shadows the accessor Lit installs
  // for the static property, so setting `.text` would never schedule a
  // re-render. Declare the type and initialize in the constructor instead.
  declare text: string;

  private term: Terminal | null = null;
  private fit: FitAddon | null = null;
  private resizeObserver: ResizeObserver | null = null;
  /** The prefix of `text` already written to the terminal. */
  private written = '';

  constructor() {
    super();
    this.text = '';
  }

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override render(): TemplateResult {
    return html`<div class="ca-console-term"></div>`;
  }

  override firstUpdated(): void {
    const { term, fit } = createTerminal({
      term: { fontSize: 12.5, scrollback: 5000, cursorBlink: false },
    });
    this.term = term;
    this.fit = fit;
    const host = this.querySelector<HTMLElement>('.ca-console-term');
    if (host !== null) {
      term.open(host);
      fit.fit();
      this.resizeObserver = new ResizeObserver(() => {
        fit.fit();
      });
      this.resizeObserver.observe(host);
    }
    this.syncTerminal();
  }

  override updated(changed: PropertyValues<this>): void {
    if (changed.has('text')) {
      this.syncTerminal();
    }
  }

  override disconnectedCallback(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.term?.dispose();
    this.term = null;
    this.fit = null;
    this.written = '';
    super.disconnectedCallback();
  }

  private syncTerminal(): void {
    const term = this.term;
    if (term === null || this.text === this.written) {
      return;
    }
    if (this.text.startsWith(this.written)) {
      term.write(this.text.slice(this.written.length));
    } else {
      // The buffer was cleared (a new run) or trimmed: repaint from scratch.
      term.reset();
      term.write(this.text);
    }
    this.written = this.text;
  }
}

customElements.define('ca-console', CaConsole);
