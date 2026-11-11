// Podman image manager UI.
//
// Lists images in the shared Kaithem podman storage and exposes the
// tag/pull/prune/export/import actions backed by /podman/api.

import { LitElement, html, nothing } from 'lit';
import type { TemplateResult } from 'lit';

import {
  ApiError,
  addTag,
  exportUrl,
  importImage,
  listImages,
  prune,
  pullImage,
  removeImage,
} from './podman-api.ts';
import type { PodmanImage, PruneResult } from './podman-api.ts';

const BYTE_UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B';
  }
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    BYTE_UNITS.length - 1
  );
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${BYTE_UNITS[exponent]}`;
}

function formatDate(unixSeconds: number): string {
  if (!unixSeconds) {
    return '—';
  }
  return new Date(unixSeconds * 1000).toLocaleString();
}

function shortId(id: string): string {
  const value = id.startsWith('sha256:') ? id.slice('sha256:'.length) : id;
  return value.slice(0, 12);
}

interface ImageRow {
  image: PodmanImage;
  name: string | null;
}

export class PodmanManager extends LitElement {
  private images: PodmanImage[] = [];
  private loading = false;
  private busy = '';
  private error = '';
  private notice = '';

  private pullValue = '';
  private selectedFile: File | null = null;
  private pruneOpen = false;
  private pruneResult: PruneResult | null = null;
  private tagTarget: string | null = null;
  private tagValue = '';
  private deleteTarget: string | null = null;

  override createRenderRoot(): HTMLElement {
    return this;
  }

  override connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  private async load(): Promise<void> {
    this.loading = true;
    this.error = '';
    this.requestUpdate();
    try {
      this.images = await listImages();
    } catch (error) {
      this.error = this.describe(error);
    } finally {
      this.loading = false;
      this.requestUpdate();
    }
  }

  private describe(error: unknown): string {
    if (error instanceof ApiError) {
      return error.message;
    }
    return error instanceof Error ? error.message : String(error);
  }

  private async run(key: string, action: () => Promise<void>): Promise<void> {
    this.busy = key;
    this.error = '';
    this.notice = '';
    this.requestUpdate();
    try {
      await action();
    } catch (error) {
      this.error = this.describe(error);
    } finally {
      this.busy = '';
      this.requestUpdate();
    }
  }

  private handlePull(): void {
    const image = this.pullValue.trim();
    if (!image) {
      return;
    }
    void this.run('pull', async () => {
      await pullImage(image);
      this.notice = `Pulled ${image}.`;
      await this.load();
    });
  }

  private openTagDialog(image: string): void {
    this.tagTarget = image;
    this.tagValue = image;
    this.requestUpdate();
  }

  private submitTag(): void {
    const image = this.tagTarget;
    const newTag = this.tagValue.trim();
    if (image === null || !newTag) {
      return;
    }
    void this.run('tag', async () => {
      await addTag(image, newTag);
      this.tagTarget = null;
      this.notice = `Tagged ${image} as ${newTag}.`;
      await this.load();
    });
  }

  private confirmPrune(): void {
    void this.run('prune', async () => {
      this.pruneResult = await prune();
      this.pruneOpen = false;
      this.notice = 'Prune complete.';
      await this.load();
    });
  }

  private openDeleteDialog(image: string): void {
    this.deleteTarget = image;
    this.requestUpdate();
  }

  private confirmDelete(): void {
    const image = this.deleteTarget;
    if (image === null) {
      return;
    }
    void this.run('delete', async () => {
      await removeImage(image);
      this.deleteTarget = null;
      this.notice = `Removed ${image}.`;
      await this.load();
    });
  }

  private handleFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
    this.requestUpdate();
  }

  private handleUpload(): void {
    const file = this.selectedFile;
    if (file === null) {
      return;
    }
    void this.run('import', async () => {
      const output = await importImage(file);
      this.selectedFile = null;
      this.notice = output.trim() || `Imported ${file.name}.`;
      await this.load();
    });
  }

  private rows(): ImageRow[] {
    const rows: ImageRow[] = [];
    for (const image of this.images) {
      if (image.names.length === 0) {
        rows.push({ image, name: null });
        continue;
      }
      for (const name of image.names) {
        rows.push({ image, name });
      }
    }
    return rows;
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  override render(): TemplateResult {
    return html`
      <main class="pm-shell">
        <header class="pm-header">
          <div>
            <h1>Podman Images</h1>
            <p class="pm-subtitle">
              Images in the shared Kaithem rootless podman storage.
            </p>
          </div>
          <button
            class="btn"
            ?disabled="${this.loading || this.busy !== ''}"
            @click="${() => void this.load()}"
          >
            Refresh
          </button>
        </header>

        ${this.error ? html`<p class="pm-error">${this.error}</p>` : nothing}
        ${this.notice ? html`<p class="pm-notice">${this.notice}</p>` : nothing}
        ${this.renderToolbar()} ${this.renderTable()}
        ${this.renderPruneResult()}
      </main>
      ${this.renderTagDialog()} ${this.renderPruneDialog()}
      ${this.renderDeleteDialog()}
    `;
  }

  private renderToolbar(): TemplateResult {
    return html`
      <section class="pm-toolbar">
        <div class="pm-pull">
          <input
            type="text"
            placeholder="Image tag to pull, e.g. docker.io/library/alpine:latest"
            .value="${this.pullValue}"
            @input="${(event: Event) =>
              (this.pullValue = (event.target as HTMLInputElement).value)}"
            @keydown="${(event: KeyboardEvent) => {
              if (event.key === 'Enter') {
                this.handlePull();
              }
            }}"
          >
          <button
            class="btn primary"
            ?disabled="${this.busy !== ''}"
            @click="${() => this.handlePull()}"
          >
            Pull
          </button>
        </div>

        <div class="pm-import">
          <input
            type="file"
            accept=".tar,application/x-tar"
            ?disabled="${this.busy !== ''}"
            @change="${this.handleFileSelected}"
          >
          <button
            class="btn"
            ?disabled="${this.busy !== '' || this.selectedFile === null}"
            @click="${() => this.handleUpload()}"
          >
            Upload
          </button>
          <button
            class="btn danger"
            ?disabled="${this.busy !== ''}"
            @click="${() => {
              this.pruneOpen = true;
              this.requestUpdate();
            }}"
          >
            Prune older than 1 week
          </button>
        </div>
      </section>
    `;
  }

  private renderTable(): TemplateResult {
    const rows = this.rows();
    if (rows.length === 0) {
      return html`
        <section class="pm-empty">
          ${this.loading ? 'Loading images…' : 'No images found.'}
        </section>
      `;
    }
    return html`
      <table class="pm-table">
        <thead>
          <tr>
            <th>Tag</th>
            <th>Size</th>
            <th>Image ID</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => this.renderRow(row))}
        </tbody>
      </table>
    `;
  }

  private renderRow(row: ImageRow): TemplateResult {
    const { image, name } = row;
    return html`
      <tr>
        <td>
          ${name
            ? html`<code class="pm-tag">${name}</code>`
            : html`<span class="pm-untagged">&lt;untagged&gt;</span>`}
        </td>
        <td>${formatBytes(image.size)}</td>
        <td><code title="${image.id}">${shortId(image.id)}</code></td>
        <td>${formatDate(image.created)}</td>
        <td class="pm-actions">
          ${name
            ? html`
                <a class="button" href="${exportUrl(name)}">Export</a>
                <button class="btn" @click="${() => this.openTagDialog(name)}">
                  Add tag
                </button>
                <button
                  class="btn danger"
                  @click="${() => this.openDeleteDialog(name)}"
                >
                  Delete
                </button>
              `
            : nothing}
        </td>
      </tr>
    `;
  }

  private renderPruneResult(): TemplateResult | typeof nothing {
    if (this.pruneResult === null) {
      return nothing;
    }
    const output = [this.pruneResult.containers, this.pruneResult.images]
      .map((part) => part.trim())
      .filter((part) => part.length > 0)
      .join('\n');
    return html`
      <section class="pm-prune-result">
        <h2>Prune output</h2>
        <pre>${output || 'Nothing to prune.'}</pre>
      </section>
    `;
  }

  private renderTagDialog(): TemplateResult | typeof nothing {
    if (this.tagTarget === null) {
      return nothing;
    }
    const busy = this.busy === 'tag';
    return html`
      <div class="pm-modal-backdrop">
        <section class="pm-modal">
          <h2>Add a tag</h2>
          <p>New tag pointing at <code>${this.tagTarget}</code>:</p>
          <input
            type="text"
            .value="${this.tagValue}"
            @input="${(event: Event) =>
              (this.tagValue = (event.target as HTMLInputElement).value)}"
            @keydown="${(event: KeyboardEvent) => {
              if (event.key === 'Enter') {
                this.submitTag();
              }
            }}"
          >
          <div class="pm-modal-actions">
            <button
              class="btn"
              ?disabled="${busy}"
              @click="${() => {
                this.tagTarget = null;
                this.requestUpdate();
              }}"
            >
              Cancel
            </button>
            <button
              class="btn primary"
              ?disabled="${busy || !this.tagValue.trim()}"
              @click="${() => this.submitTag()}"
            >
              Add tag
            </button>
          </div>
        </section>
      </div>
    `;
  }

  private renderPruneDialog(): TemplateResult | typeof nothing {
    if (!this.pruneOpen) {
      return nothing;
    }
    const busy = this.busy === 'prune';
    return html`
      <div class="pm-modal-backdrop">
        <section class="pm-modal">
          <h2>Prune old containers and images?</h2>
          <p>
            This removes stopped containers and unused images older than one
            week. It cannot be undone.
          </p>
          <div class="pm-modal-actions">
            <button
              class="btn"
              ?disabled="${busy}"
              @click="${() => {
                this.pruneOpen = false;
                this.requestUpdate();
              }}"
            >
              Cancel
            </button>
            <button
              class="btn danger"
              ?disabled="${busy}"
              @click="${() => this.confirmPrune()}"
            >
              Prune
            </button>
          </div>
        </section>
      </div>
    `;
  }

  private renderDeleteDialog(): TemplateResult | typeof nothing {
    if (this.deleteTarget === null) {
      return nothing;
    }
    const busy = this.busy === 'delete';
    return html`
      <div class="pm-modal-backdrop">
        <section class="pm-modal">
          <h2>Delete image?</h2>
          <p>
            This removes <code>${this.deleteTarget}</code>. If the image has
            other tags, only this tag is removed and the image is kept until its
            last tag is gone. This cannot be undone.
          </p>
          <div class="pm-modal-actions">
            <button
              class="btn"
              ?disabled="${busy}"
              @click="${() => {
                this.deleteTarget = null;
                this.requestUpdate();
              }}"
            >
              Cancel
            </button>
            <button
              class="btn danger"
              ?disabled="${busy}"
              @click="${() => this.confirmDelete()}"
            >
              Delete
            </button>
          </div>
        </section>
      </div>
    `;
  }
}

customElements.define('podman-manager', PodmanManager);
