// Admin page for a presentation screen: file list, playback state, viewing
// settings, and an embedded viewer.
//
// The server owns one playback state; this page replaces it wholesale.  The
// viewer only mirrors it, so next/prev here move the whole screen.

import { LitElement, html } from 'lit';
import type { TemplateResult } from 'lit';

import {
  deleteFile,
  editorUrl,
  errorMessage,
  formatBytes,
  getConfig,
  getState,
  getStatus,
  listFiles,
  normalizeState,
  screenRefFromUrl,
  setConfig,
  setDefaultState,
  setState,
  stoppedState,
  viewerUrl,
} from './presentation-api.ts';
import type {
  PresentationFileInfo,
  PresentationState,
  ScreenRef,
} from './presentation-api.ts';

const STATUS_POLL_MS = 5000;

export class PresentationAdmin extends LitElement {
  private ref: ScreenRef | null = null;

  private screenTitle = 'Presentation Screen';
  private titleDraft = '';
  private requiresAdmin = false;
  private files: PresentationFileInfo[] = [];
  private connected = 0;

  private currentState: PresentationState = stoppedState();
  private defaultState: PresentationState = stoppedState();
  private slideDraft = '1';

  private status = '';
  private statusIsError = false;
  private loading = false;
  private savingSettings = false;
  private busy = false;

  private pollTimer: ReturnType<typeof setInterval> | null = null;

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
      void this.poll();
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

  private applyState(state: PresentationState): void {
    this.currentState = normalizeState(state);
    this.slideDraft =
      this.currentState.type === 'pptx'
        ? String(this.currentState.slide + 1)
        : '1';
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
      await this.poll();
    } catch (error) {
      this.setError(errorMessage(error));
    } finally {
      this.loading = false;
      this.requestUpdate();
    }
  }

  /** Light periodic sync of the viewer count and the shared state. */
  private async poll(): Promise<void> {
    if (!this.ref) {
      return;
    }
    try {
      const [status, state] = await Promise.all([
        getStatus(this.ref),
        getState(this.ref),
      ]);
      this.connected = status.connected;
      this.defaultState = state.default_state;
      // Do not stomp on a half-typed slide number while an edit is pending.
      if (!this.busy) {
        this.applyState(state.state);
      } else {
        this.requestUpdate();
      }
    } catch {
      // A transient poll failure must not disturb the page.
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

  /** Replace the server state and let the poll pick up the echo. */
  private async commitState(
    state: PresentationState,
    message: string
  ): Promise<void> {
    if (!this.ref) {
      return;
    }
    this.busy = true;
    try {
      await setState(this.ref, state);
      this.applyState(state);
      this.setStatus(message);
    } catch (error) {
      this.setError(`Could not update the screen: ${errorMessage(error)}`);
    } finally {
      this.busy = false;
    }
  }

  private playPresentation(file: PresentationFileInfo): void {
    const confirmed = globalThis.confirm(
      `Start presenting "${file.name}" on every viewer?`
    );
    if (!confirmed) {
      return;
    }
    void this.commitState(
      { type: 'pptx', file: file.name, slide: 0 },
      `Playing ${file.name}`
    );
  }

  private stopPresentation(): void {
    const confirmed = globalThis.confirm(
      'Stop the presentation on every viewer?'
    );
    if (!confirmed) {
      return;
    }
    void this.commitState(stoppedState(), 'Stopped');
  }

  private stepSlide(delta: number): void {
    if (this.currentState.type !== 'pptx') {
      return;
    }
    const slide = Math.max(0, this.currentState.slide + delta);
    void this.commitState(
      { ...this.currentState, slide },
      `Moved to slide ${slide + 1}`
    );
  }

  private updateSlideNumber(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.slideDraft = input.value;
    this.requestUpdate();
  }

  private goToSlide(): void {
    if (this.currentState.type !== 'pptx') {
      return;
    }
    const parsed = Number.parseInt(this.slideDraft, 10);
    const slide = Math.max(0, (Number.isNaN(parsed) ? 1 : parsed) - 1);
    void this.commitState(
      { ...this.currentState, slide },
      `Moved to slide ${slide + 1}`
    );
  }

  private async saveDefaultState(): Promise<void> {
    if (!this.ref) {
      return;
    }
    try {
      this.defaultState = await setDefaultState(this.ref);
      this.setStatus('Default start state updated');
    } catch (error) {
      this.setError(`Could not save the default: ${errorMessage(error)}`);
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

  private updateTitle(event: Event): void {
    this.titleDraft = (event.target as HTMLInputElement).value;
    this.requestUpdate();
  }

  private updateRequiresAdmin(event: Event): void {
    this.requiresAdmin = (event.target as HTMLInputElement).checked;
    this.requestUpdate();
  }

  private renderStateList(
    state: PresentationState,
    testId: string
  ): TemplateResult {
    const rows: [string, string][] =
      state.type === 'pptx'
        ? [
            ['type', state.type],
            ['file', state.file],
            ['slide', `${state.slide} (slide ${state.slide + 1})`],
          ]
        : [['type', state.type]];
    return html`
      <dl class="ps-kv" data-testid="${testId}">
        ${rows.map(
          ([key, value]) =>
            html`<dt>${key}</dt>
              <dd>${value}</dd>`
        )}
      </dl>
    `;
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
            @click="${() => this.playPresentation(file)}"
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

    const playing = this.currentState.type === 'pptx';

    return html`
      <div class="ps-admin">
        <aside class="ps-admin__side">
          <h2 class="ps-admin__title" data-testid="admin-title">
            ${this.screenTitle}
          </h2>

          <section class="ps-panel">
            <h3>State</h3>
            <div class="ps-kv-group">
              <span class="ps-kv-group__label">Current</span>
              ${this.renderStateList(this.currentState, 'state-current')}
            </div>
            <div class="ps-kv-group">
              <span class="ps-kv-group__label">Default</span>
              ${this.renderStateList(this.defaultState, 'state-default')}
            </div>
            <button
              data-testid="admin-set-default"
              title="Save the current state as the start state"
              @click="${this.saveDefaultState}"
            >
              Set current state as default
            </button>
          </section>

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
              ?disabled="${!playing || this.busy}"
              @click="${() => this.stepSlide(-1)}"
            >
              ◀ Prev
            </button>
            <button
              data-testid="control-next"
              title="Next slide"
              ?disabled="${!playing || this.busy}"
              @click="${() => this.stepSlide(1)}"
            >
              Next ▶
            </button>
            <button
              data-testid="control-stop"
              class="ps-danger"
              title="Stop the presentation"
              ?disabled="${!playing}"
              @click="${this.stopPresentation}"
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
                .value="${this.slideDraft}"
                ?disabled="${!playing}"
                @input="${this.updateSlideNumber}"
                @keydown="${(event: KeyboardEvent) => {
                  if (event.key === 'Enter') {
                    this.goToSlide();
                  }
                }}"
              >
            </label>
            <button
              data-testid="control-goto"
              ?disabled="${!playing || this.busy}"
              @click="${this.goToSlide}"
            >
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
