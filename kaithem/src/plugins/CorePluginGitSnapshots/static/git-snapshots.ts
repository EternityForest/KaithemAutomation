// SPDX-License-Identifier: GPL-3.0-or-later
// Snapshot backup UI.
//
// This presents the system git binary as a dead simple "snapshot backup":
// it lists snapshots, takes a new one, and restores an old one. There is
// no branch, commit, or merge vocabulary anywhere, and git init is fully
// hidden. The folder comes from the ?workspace= query parameter, so one
// bundle serves every folder, and the page is meant to be embedded in an
// iframe (the API enforces system_admin on every call).

import { LitElement, html, nothing } from 'lit';
import type { TemplateResult } from 'lit';

import { gitSnapshotsApi } from './git-snapshots-api.ts';
import type {
  GitSnapshotsApi,
  SnapshotInfo,
  StatusInfo,
} from './git-snapshots-api.ts';

/** The folder is the whole point of the page. */
function workspaceFromLocation(): string {
  const params = new URLSearchParams(globalThis.location.search);
  return (params.get('workspace') ?? '').trim();
}

export class GitSnapshots extends LitElement {
  static override properties = {
    status: { state: true },
    snapshots: { state: true },
    loading: { state: true },
    busy: { state: true },
    message: { state: true },
    error: { state: true },
    notice: { state: true },
    confirmRestore: { state: true },
  };

  override createRenderRoot() {
    return this;
  }

  declare status: StatusInfo | null;
  declare snapshots: SnapshotInfo[];
  declare loading: boolean;
  declare busy: boolean;
  declare message: string;
  declare error: string;
  declare notice: string;
  declare confirmRestore: string;

  private workspace = '';
  private api: GitSnapshotsApi | null = null;
  private destroyed = false;

  constructor() {
    super();
    this.status = null;
    this.snapshots = [];
    this.loading = true;
    this.busy = false;
    this.message = '';
    this.error = '';
    this.notice = '';
    this.confirmRestore = '';
  }

  override connectedCallback(): void {
    super.connectedCallback();
    this.workspace = workspaceFromLocation();
    if (!this.workspace) {
      this.loading = false;
      this.error = 'No folder was provided in the URL.';
      this.requestUpdate();
      return;
    }
    this.api = gitSnapshotsApi(this.workspace);
    void this.refresh();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.destroyed = true;
  }

  private async refresh(): Promise<void> {
    if (!this.api) {
      return;
    }
    try {
      const status = await this.api.status();
      if (this.destroyed) {
        return;
      }
      this.status = status;
      this.snapshots = status.snapshots;
      this.error = '';
    } catch (error) {
      this.error = describeError(error);
    } finally {
      this.loading = false;
      this.requestUpdate();
    }
  }

  private async takeSnapshot(): Promise<void> {
    if (!this.api || this.busy) {
      return;
    }
    const message = this.message.trim();
    if (!message) {
      this.error = 'Give the snapshot a name before saving it.';
      this.requestUpdate();
      return;
    }
    this.busy = true;
    this.error = '';
    this.notice = '';
    this.confirmRestore = '';
    this.requestUpdate();
    try {
      await this.api.take(message);
      this.message = '';
      this.notice = 'Snapshot saved.';
      await this.refresh();
    } catch (error) {
      this.error = describeError(error);
    } finally {
      this.busy = false;
      this.requestUpdate();
    }
  }

  private async restore(commit: string): Promise<void> {
    if (!this.api || this.busy) {
      return;
    }
    this.busy = true;
    this.error = '';
    this.notice = '';
    this.confirmRestore = '';
    this.requestUpdate();
    try {
      await this.api.restore(commit);
      this.notice = 'Folder restored to the chosen snapshot.';
      await this.refresh();
    } catch (error) {
      this.error = describeError(error);
    } finally {
      this.busy = false;
      this.requestUpdate();
    }
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  override render(): TemplateResult {
    return html`
      <div class="snap-shell">
        ${this.renderHeader()} ${this.renderBanners()}
        <div class="snap-body">${this.renderBody()}</div>
      </div>
    `;
  }

  private renderHeader(): TemplateResult {
    const name = this.status?.name || 'Folder';
    return html`
      <header class="snap-header">
        <div class="snap-heading">
          <h1>Snapshot backup</h1>
          <p class="snap-folder" title="${this.workspace}">${name}</p>
        </div>
        <button
          class="snap-ghost"
          data-testid="snap-refresh"
          title="Refresh"
          ?disabled="${this.loading || this.busy}"
          @click="${() => void this.refresh()}"
        >
          Refresh
        </button>
      </header>
    `;
  }

  private renderBanners(): TemplateResult | typeof nothing {
    return html`
      ${this.error
        ? html`<p class="snap-banner snap-error" role="alert">
            ${this.error}
          </p>`
        : nothing}
      ${this.notice
        ? html`<p class="snap-banner snap-notice">${this.notice}</p>`
        : nothing}
    `;
  }

  private renderBody(): TemplateResult {
    if (this.loading) {
      return html`<p class="snap-empty">Loading…</p>`;
    }
    if (this.status?.state === 'nested_repo') {
      return this.renderNestedNotice();
    }
    return html`${this.renderTakeForm()}${this.renderList()}`;
  }

  private renderNestedNotice(): TemplateResult {
    return html`
      <div class="snap-info-box" data-testid="snap-nested">
        <p>This folder is inside another Git repository.</p>
        <p>
          Snapshots must be taken from the top of that repository, so the
          folder was left exactly as it was.
        </p>
      </div>
    `;
  }

  private renderTakeForm(): TemplateResult {
    return html`
      <form
        class="snap-take"
        data-testid="snap-take-form"
        @submit="${(event: Event) => {
          event.preventDefault();
          void this.takeSnapshot();
        }}"
      >
        <input
          class="snap-message"
          data-testid="snap-message"
          type="text"
          placeholder="What changed?"
          maxlength="200"
          .value="${this.message}"
          ?disabled="${this.busy}"
          @input="${(event: Event) => {
            const target = event.target;
            if (target instanceof HTMLInputElement) {
              this.message = target.value;
              this.requestUpdate();
            }
          }}"
        />
        <button
          class="snap-primary"
          data-testid="snap-take"
          type="submit"
          ?disabled="${this.busy}"
        >
          Take snapshot
        </button>
      </form>
    `;
  }

  private renderList(): TemplateResult {
    if (this.snapshots.length === 0) {
      return html`<p class="snap-empty" data-testid="snap-empty">
        No snapshots yet. Take one to save the current state.
      </p>`;
    }
    return html`
      <ul class="snap-list" data-testid="snap-list">
        ${this.snapshots.map((snapshot) => this.renderItem(snapshot))}
      </ul>
    `;
  }

  private renderItem(snapshot: SnapshotInfo): TemplateResult {
    const confirming = this.confirmRestore === snapshot.commit;
    return html`
      <li class="snap-item" data-commit="${snapshot.commit}">
        <div class="snap-item-main">
          <span class="snap-subject">${snapshot.subject}</span>
          <span class="snap-meta">
            <span class="snap-sha">${snapshot.short}</span>
            <span>${formatDate(snapshot.timestamp)}</span>
            <span>${snapshot.author}</span>
          </span>
        </div>
        ${confirming ? this.renderConfirm(snapshot) : this.renderRestore()}
      </li>
    `;
  }

  private renderRestore(): TemplateResult {
    return html`
      <button
        class="snap-ghost"
        data-testid="snap-restore"
        ?disabled="${this.busy}"
        @click="${(event: Event) => {
          const item = (event.target as HTMLElement).closest('.snap-item');
          const commit = item?.getAttribute('data-commit') ?? '';
          this.confirmRestore = commit;
          this.requestUpdate();
        }}"
      >
        Restore
      </button>
    `;
  }

  private renderConfirm(snapshot: SnapshotInfo): TemplateResult {
    return html`
      <div class="snap-confirm">
        <span class="snap-confirm-text">Replace current files?</span>
        <button
          class="snap-ghost"
          data-testid="snap-cancel"
          ?disabled="${this.busy}"
          @click="${() => {
            this.confirmRestore = '';
            this.requestUpdate();
          }}"
        >
          Cancel
        </button>
        <button
          class="snap-danger"
          data-testid="snap-confirm"
          ?disabled="${this.busy}"
          @click="${() => void this.restore(snapshot.commit)}"
        >
          Restore
        </button>
      </div>
    `;
  }
}

function describeError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function formatDate(timestamp: number): string {
  if (!timestamp) {
    return '';
  }
  return new Date(timestamp * 1000).toLocaleString();
}

customElements.define('git-snapshots', GitSnapshots);
