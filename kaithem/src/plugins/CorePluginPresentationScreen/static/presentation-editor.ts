// Presentation editor: opens one .pptx from the screen's content folder,
// lets the admin edit it with the real PowerPoint engine, and pushes the
// in-memory deck back to the folder.

import 'pptx-vanilla-viewer/styles.css';

import { LitElement, html } from 'lit';
import { createPptxViewer } from 'pptx-vanilla-viewer';
import type { PptxViewerInstance } from 'pptx-vanilla-viewer';
import { PptxHandler } from 'pptx-viewer-core';

import {
  adminUrl,
  errorMessage,
  fileUrl,
  saveFile,
  screenRefFromUrl,
  validatePptxFilename,
} from './presentation-api.ts';
import type { ScreenRef } from './presentation-api.ts';

export class PresentationEditor extends LitElement {
  private ref: ScreenRef | null = null;
  private viewer: PptxViewerInstance | null = null;
  private container: HTMLElement | null = null;

  private filename = '';
  private status = '';
  private statusIsError = false;
  private loaded = false;
  private saving = false;
  private dirty = false;
  private slideCount = 0;
  private currentSlide = 0;

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener('beforeunload', this.onBeforeUnload);
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener('beforeunload', this.onBeforeUnload);
    this.viewer?.destroy();
    this.viewer = null;
  }

  override firstUpdated(): void {
    const container = this.querySelector<HTMLElement>('.ps-editor__stage');
    if (!container) {
      throw new Error('Editor stage element is missing');
    }
    this.container = container;

    try {
      this.ref = screenRefFromUrl();
    } catch (error) {
      this.setError(errorMessage(error));
      return;
    }

    const params = new URLSearchParams(globalThis.location.search);
    this.filename = params.get('file') ?? '';
    this.createViewer();
    this.requestUpdate();
  }

  private onBeforeUnload = (event: BeforeUnloadEvent): void => {
    if (this.dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  };

  private createViewer(): void {
    if (!this.container || !this.ref) {
      return;
    }

    const source = this.filename ? fileUrl(this.ref, this.filename) : undefined;

    this.viewer = createPptxViewer(this.container, {
      source,
      fileName: this.filename || 'Untitled.pptx',
      editable: true,
      showToolbar: true,
      showThumbnails: true,
      // The property inspector stays enabled: it is the only way to adjust
      // position/size/fill/line, and hiding it left its toggle dead.
      inspectorInitiallyOpen: true,
      // The built-in File tab would offer Download/Open; saving is handled
      // by this page's own Save button instead.
      hiddenActions: ['file', 'record', 'share', 'broadcast', 'export', 'help'],
      customization: {
        hiddenPanels: ['quickAccessToolbar'],
      },
      onLoad: ({ slideCount }) => {
        this.loaded = true;
        this.slideCount = slideCount;
        this.currentSlide = 0;
        this.dirty = false;
        this.setStatus(`Loaded ${slideCount} slide(s)`);
      },
      onSlideChange: (index) => {
        this.currentSlide = index;
        this.requestUpdate();
      },
      onDirtyChange: (dirty) => {
        this.dirty = dirty;
        this.requestUpdate();
      },
      onError: (message) => {
        this.setError(message);
      },
    });

    if (!this.filename) {
      void this.startNewDeck();
    }
  }

  /**
   * Seed the editor with a blank deck so a brand-new presentation can be
   * saved straight into the screen's content folder.
   */
  private async startNewDeck(): Promise<void> {
    this.filename = 'Untitled.pptx';
    this.requestUpdate();
    try {
      // Without initialSlideCount the builder produces a zero-slide deck,
      // which the editor cannot render (and shows no editing chrome for).
      const { handler, data } = await PptxHandler.create({
        title: 'New Presentation',
        creator: '',
        initialSlideCount: 1,
      });
      if (!this.viewer) {
        return;
      }
      await this.viewer.loadFile(await handler.save(data.slides));
      this.dirty = true;
      this.setStatus('New presentation created');
    } catch (error) {
      this.setError(`Could not create a new deck: ${errorMessage(error)}`);
    }
  }

  private setStatus(message: string): void {
    this.status = message;
    this.statusIsError = false;
    this.requestUpdate();
  }

  private setError(message: string): void {
    this.status = message;
    this.statusIsError = true;
    this.requestUpdate();
  }

  private updateFilename(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.filename = input.value;
    this.requestUpdate();
  }

  private async save(): Promise<void> {
    if (!this.viewer || !this.ref) {
      return;
    }
    this.saving = true;
    this.status = 'Saving…';
    this.statusIsError = false;
    this.requestUpdate();

    try {
      if (!this.filename.endsWith('.pptx')) {
        this.filename += '.pptx';
      }
      const name = validatePptxFilename(this.filename);

      // Serialises the in-memory deck back to PPTX bytes.
      const pptxBlob = await this.viewer.getContent();

      await saveFile(this.ref, name, new Uint8Array(pptxBlob));
      this.filename = name;
      this.dirty = false;
      this.setStatus(`Saved ${name}`);

      // Keep the URL in sync so reloading reopens the file just saved.
      const url = new URL(globalThis.location.href);
      url.searchParams.set('file', name);
      globalThis.history.replaceState(null, '', url.toString());
    } catch (error) {
      this.setError(`Save failed: ${errorMessage(error)}`);
    } finally {
      this.saving = false;
      this.requestUpdate();
    }
  }

  private openFile(): void {
    if (!this.ref) {
      return;
    }
    const url = new URL(globalThis.location.href);
    url.searchParams.set('file', this.filename);
    globalThis.location.href = url.toString();
  }

  override render() {
    const adminHref = this.ref ? adminUrl(this.ref) : '/';
    return html`
      <div class="ps-editor">
        <header class="ps-toolbar">
          <a class="ps-toolbar__back" href="${adminHref}">← Presentations</a>
          <span class="ps-toolbar__title">Presentation Editor</span>
          <label class="ps-toolbar__field">
            <span>Filename</span>
            <input
              data-testid="editor-filename"
              type="text"
              spellcheck="false"
              .value="${this.filename}"
              @input="${this.updateFilename}"
              @keydown="${(event: KeyboardEvent) => {
                if (event.key === 'Enter') {
                  this.save();
                }
              }}"
            >
          </label>
          <button
            data-testid="editor-open"
            ?disabled="${!this.filename}"
            @click="${this.openFile}"
          >
            Open
          </button>
          <button
            class="ps-primary"
            data-testid="editor-save"
            ?disabled="${this.saving}"
            @click="${this.save}"
          >
            ${this.saving ? 'Saving…' : 'Save'}
          </button>
          ${this.dirty
            ? html`<span class="ps-badge ps-badge--dirty"
                >Unsaved changes</span
              >`
            : ''}

          <span
            class="ps-status ${this.statusIsError ? 'ps-status--error' : ''}"
            data-testid="editor-status"
            >${this.status}</span
          >
          <span class="ps-toolbar__meta">
            ${this.loaded
              ? `Slide ${this.currentSlide + 1} / ${this.slideCount}`
              : ''}
          </span>
        </header>
        <div class="ps-editor__stage"></div>
      </div>
    `;
  }
}

customElements.define('presentation-editor', PresentationEditor);
