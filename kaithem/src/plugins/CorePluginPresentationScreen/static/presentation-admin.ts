// Admin page for a presentation screen: file list, playback controls,
// viewing settings, and an embedded viewer.

import { LitElement, html } from 'lit';

import {
  deleteFile,
  editorUrl,
  errorMessage,
  formatBytes,
  getConfig,
  getStatus,
  listFiles,
  screenRefFromUrl,
  sendCommand,
  setConfig,
  viewerUrl,
} from './presentation-api.ts';
import type { PresentationFileInfo, ScreenRef } from './presentation-api.ts';

const STATUS_POLL_MS = 5000;

export class PresentationAdmin extends LitElement {
  private ref: ScreenRef | null = null;

  private screenTitle = 'Presentation Screen';
  private titleDraft = '';
  private requiresAdmin = false;
  private files: PresentationFileInfo[] = [];
  private connected = 0;
  private slideNumber = 1;

  private status = '';
  private statusIsError = false;
  private loading = false;
  private savingSettings = false;

  private pollTimer: number | null = null;

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override firstUpdated(): void {
    try {
      this.ref = screenRefFromUrl();
    } catch (error) {
      this.setError(errorMessage(error));
      return;
    }
    void this.refresh(true);
    this.pollTimer = globalThis.setInterval(() => {
      void this.refreshStatus();
    }, STATUS_POLL_MS);
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this.pollTimer !== null) {
      globalThis.clearInterval(this.pollTimer);
      this.pollTimer = null;
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

  private async refresh(includeFiles = false): Promise<void> {
    if (!this.ref) {
      return;
    }
    this.loading = true;
    this.requestUpdate();
    try {
      const config = await getConfig(this.ref);
      this.screenTitle = config.title;
      this.titleDraft = config.title;
      this.requiresAdmin = config.view_requires_admin;
      if (includeFiles) {
        this.files = await listFiles(this.ref);
      }
      await this.refreshStatus();
    } catch (error) {
      this.setError(errorMessage(error));
    } finally {
      this.loading = false;
      this.requestUpdate();
    }
  }

  private async refreshStatus(): Promise<void> {
    if (!this.ref) {
      return;
    }
    try {
      const status = await getStatus(this.ref);
      this.connected = status.connected;
      this.requestUpdate();
    } catch {
      // A transient status failure must not disturb the page.
    }
  }

  private async saveSettings(): Promise<void> {
    if (!this.ref) {
      return;
    }
    this.savingSettings = true;
    this.requestUpdate();
    try {
      const title = this.titleDraft.trim() || 'Presentation Screen';
      await setConfig(this.ref, {
        title,
        view_requires_admin: this.requiresAdmin,
      });
      this.screenTitle = title;
      this.titleDraft = title;
      this.setStatus('Settings saved');
    } catch (error) {
      this.setError(`Could not save settings: ${errorMessage(error)}`);
    } finally {
      this.savingSettings = false;
      this.requestUpdate();
    }
  }

  private async command(
    action: 'load' | 'stop' | 'next' | 'prev' | 'goto',
    file?: string,
    slide?: number
  ): Promise<void> {
    if (!this.ref) {
      return;
    }
    try {
      await sendCommand(this.ref, { action, file, slide });
      if (action === 'load' && file) {
        this.setStatus(`Playing ${file}`);
      } else if (action === 'goto' && slide !== undefined) {
        this.setStatus(`Moved to slide ${slide + 1}`);
      } else if (action !== 'load') {
        this.setStatus(`Sent ${action}`);
      }
    } catch (error) {
      this.setError(`Command failed: ${errorMessage(error)}`);
    }
  }

  private async deletePresentation(file: PresentationFileInfo): Promise<void> {
    if (!this.ref) {
      return;
    }
    const confirmed = globalThis.confirm(
      `Delete "${file.name}"? This cannot be undone.`
    );
    if (!confirmed) {
      return;
    }
    try {
      await deleteFile(this.ref, file.name);
      this.files = this.files.filter((item) => item.name !== file.name);
      this.setStatus(`Deleted ${file.name}`);
    } catch (error) {
      this.setError(`Delete failed: ${errorMessage(error)}`);
    }
  }

  private updateSlideNumber(event: Event): void {
    const input = event.target as HTMLInputElement;
    const value = Number.parseInt(input.value, 10);
    this.slideNumber = Number.isNaN(value) ? 1 : Math.max(1, value);
    this.requestUpdate();
  }

  private goToSlide(): void {
    const slide = Math.max(1, Math.floor(this.slideNumber));
    void this.command('goto', undefined, slide - 1);
  }

  private updateTitle(event: Event): void {
    this.titleDraft = (event.target as HTMLInputElement).value;
    this.requestUpdate();
  }

  private updateRequiresAdmin(event: Event): void {
    this.requiresAdmin = (event.target as HTMLInputElement).checked;
    this.requestUpdate();
  }

  private renderFile(file: PresentationFileInfo) {
    if (!this.ref) {
      return '';
    }
    return html`
      <li class="ps-file" data-testid="file-row">
        <div class="ps-file__info">
          <span class="ps-file__name" data-testid="file-name"
            >${file.name}</span
          >
          <span class="ps-file__meta"
            >${formatBytes(file.size)} ·
            ${new Date(file.mtime * 1000).toLocaleString()}</span
          >
        </div>
        <div class="ps-file__actions">
          <button
            data-testid="file-play"
            title="Play on the viewer"
            @click="${() => this.command('load', file.name)}"
          >
            ▶ Play
          </button>
          <a
            class="button"
            data-testid="file-edit"
            href="${editorUrl(this.ref, file.name)}"
            >Edit</a
          >
          <button
            class="ps-danger"
            data-testid="file-delete"
            title="Delete this file"
            @click="${() => this.deletePresentation(file)}"
          >
            Delete
          </button>
        </div>
      </li>
    `;
  }

  override render() {
    if (!this.ref) {
      return html`<div class="ps-admin ps-admin--error">${this.status}</div>`;
    }

    return html`
      <div class="ps-admin">
        <aside class="ps-admin__side">
          <h2 class="ps-admin__title" data-testid="admin-title">
            ${this.screenTitle}
          </h2>

          <section class="ps-panel">
            <h3>Settings</h3>
            <label class="ps-field">
              <span>Title</span>
              <input
                data-testid="admin-title-input"
                type="text"
                .value="${this.titleDraft}"
                @input="${this.updateTitle}"
              >
            </label>
            <label class="ps-checkbox">
              <input
                data-testid="admin-requires-admin"
                type="checkbox"
                .checked="${this.requiresAdmin}"
                @change="${this.updateRequiresAdmin}"
              >
              <span>Require admin login to view</span>
            </label>
            <p class="ps-hint">
              When unchecked, anyone with the viewer link can watch.
            </p>
            <button
              class="ps-primary"
              data-testid="admin-save-settings"
              ?disabled="${this.savingSettings}"
              @click="${this.saveSettings}"
            >
              ${this.savingSettings ? 'Saving…' : 'Save settings'}
            </button>
          </section>

          <section class="ps-panel ps-panel--grow">
            <div class="ps-panel__head">
              <h3>Presentations</h3>
              <div class="ps-panel__actions">
                <a
                  class="button"
                  data-testid="admin-new-presentation"
                  href="${editorUrl(this.ref)}"
                  >New</a
                >
                <button
                  data-testid="admin-refresh"
                  title="Refresh the file list"
                  ?disabled="${this.loading}"
                  @click="${() => this.refresh(true)}"
                >
                  Refresh
                </button>
              </div>
            </div>
            ${this.files.length > 0
              ? html`<ul class="ps-file-list">
                  ${this.files.map((file) => this.renderFile(file))}
                </ul>`
              : html`<p class="ps-empty" data-testid="admin-no-files">
                  No presentations yet. Use New to create one.
                </p>`}
          </section>

          <p
            class="ps-status ${this.statusIsError ? 'ps-status--error' : ''}"
            data-testid="admin-status"
          >
            ${this.status}
          </p>
        </aside>

        <div class="ps-admin__main">
          <div class="tool-bar nogrow">
            <button
              data-testid="control-prev"
              title="Previous slide"
              @click="${() => this.command('prev')}"
            >
              ◀ Prev
            </button>
            <button
              data-testid="control-next"
              title="Next slide"
              @click="${() => this.command('next')}"
            >
              Next ▶
            </button>
            <button
              data-testid="control-stop"
              class="ps-danger"
              title="Stop the presentation"
              @click="${() => this.command('stop')}"
            >
              ■ Stop
            </button>
            <label class="ps-goto">
              <span>Slide</span>
              <input
                data-testid="control-slide"
                type="number"
                min="1"
                step="1"
                .value="${String(this.slideNumber)}"
                @input="${this.updateSlideNumber}"
                @keydown="${(event: KeyboardEvent) => {
                  if (event.key === 'Enter') {
                    this.goToSlide();
                  }
                }}"
              >
            </label>
            <button data-testid="control-goto" @click="${this.goToSlide}">
              Go
            </button>
            <span class="grow"></span>

            <a
              class="button"
              data-testid="admin-open-viewer"
              href="${viewerUrl(this.ref)}"
              target="_blank"
              rel="noopener"
              >Open viewer</a
            >            
            <p data-testid="admin-viewer-count">
              (${this.connected} viewer${this.connected === 1 ? '' : 's'})
            </p>
          </div>
          <iframe
            class="ps-admin__iframe"
            data-testid="admin-viewer-frame"
            title="Presentation viewer"
            src="${viewerUrl(this.ref)}"
          ></iframe>
        </div>
      </div>
    `;
  }
}

customElements.define('presentation-admin', PresentationAdmin);
