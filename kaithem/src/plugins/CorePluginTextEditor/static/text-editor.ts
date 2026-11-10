// SPDX-License-Identifier: GPL-3.0-or-later
// Simple text editor plugin. A micro version of vs code.
// Uses Ace editor, compiled with Vite.
// Lit component, no shadow DOM, works with the global barrel.css theme.

import { LitElement, html, css, nothing } from 'lit';
import * as ace from 'ace-builds';
// The ace-builds webpack-resolver is webpack-only and breaks under Vite
// (it uses require('file-loader?...') specifiers that cannot be resolved).
// Instead, register the worker URLs for the modes we use with Vite's
// ?worker&url imports, which emit the worker files as assets.
import javascriptWorkerUrl from 'ace-builds/src-noconflict/worker-javascript?worker&url';
import cssWorkerUrl from 'ace-builds/src-noconflict/worker-css?worker&url';
import htmlWorkerUrl from 'ace-builds/src-noconflict/worker-html?worker&url';
import jsonWorkerUrl from 'ace-builds/src-noconflict/worker-json?worker&url';
import yamlWorkerUrl from 'ace-builds/src-noconflict/worker-yaml?worker&url';
import luaWorkerUrl from 'ace-builds/src-noconflict/worker-lua?worker&url';

import type { Editor } from 'ace-builds';

// Register the standalone worker files for every mode that uses a worker.
// Modes without a listed worker (golang, rust, sh, markdown) run
// without a background worker and need no URL.
ace.config.setModuleUrl('ace/mode/javascript_worker', javascriptWorkerUrl);
ace.config.setModuleUrl('ace/mode/css_worker', cssWorkerUrl);
ace.config.setModuleUrl('ace/mode/html_worker', htmlWorkerUrl);
ace.config.setModuleUrl('ace/mode/json_worker', jsonWorkerUrl);
ace.config.setModuleUrl('ace/mode/yaml_worker', yamlWorkerUrl);
ace.config.setModuleUrl('ace/mode/lua_worker', luaWorkerUrl);

// Ace resolves modes/themes via its internal AMD loader. Side-effect imports
// register each module into that registry so ace.edit can find them offline,
// with no external script fetches needed at runtime.
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-typescript';
import 'ace-builds/src-noconflict/mode-javascript';
import 'ace-builds/src-noconflict/mode-json';
import 'ace-builds/src-noconflict/mode-css';
import 'ace-builds/src-noconflict/mode-html';
import 'ace-builds/src-noconflict/mode-yaml';
import 'ace-builds/src-noconflict/mode-markdown';
import 'ace-builds/src-noconflict/mode-golang';
import 'ace-builds/src-noconflict/mode-rust';
import 'ace-builds/src-noconflict/mode-lua';
import 'ace-builds/src-noconflict/mode-sh';
import 'ace-builds/src-noconflict/mode-text';
import 'ace-builds/src-noconflict/ext-searchbox';
import 'ace-builds/src-noconflict/theme-chrome';

const MAX_FILE_BYTES = 5 * 1024 * 1024;

interface Tab {
  path: string;
  content: string;
  dirty: boolean;
  ace: Editor | null;
}

interface FileNode {
  name: string;
  type: 'file' | 'dir';
  size?: number;
  children?: FileNode[];
}

const params = new URLSearchParams(window.location.search);
const MODULE = params.get('module') || '';
const RESOURCE = params.get('resource') || '';

class TextEditorPage extends LitElement {
  static override properties = {
    tabs: { state: true },
    activeTab: { state: true },
    sidebarOpen: { state: true },
    tree: { state: true },
    lspStatus: { state: true },
    contextMenu: { state: true },
  };

  static override styles = css`
    :host {
      display: flex;
      flex-direction: column;
      height: 100dvh;
      width: 100%;
      overflow: hidden;
      font-family: inherit;
      background: var(--bg, #fff);
      color: var(--fg, #1c1c1c);
    }
    header {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.25rem 0.5rem;
      background: var(--bg2, #e1ded7);
      flex-shrink: 0;
    }
    .tabbar {
      display: flex;
      overflow-x: auto;
      flex-shrink: 0;
      background: var(--bg2, #e1ded7);
      border-bottom: 1px solid #ccc;
      scrollbar-width: thin;
    }
    .tab {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.25rem 0.6rem;
      cursor: pointer;
      white-space: nowrap;
      border-right: 1px solid #ccc;
      font-size: 0.85rem;
    }
    .tab.active {
      background: var(--bg, #fff);
    }
    .tab .close {
      opacity: 0.6;
      cursor: pointer;
      padding: 0 0.2rem;
    }
    .main {
      display: flex;
      flex: 1;
      overflow: hidden;
      position: relative;
    }
    .sidebar {
      width: 260px;
      background: var(--bg2, #e1ded7);
      border-right: 1px solid #ccc;
      overflow-y: auto;
      flex-shrink: 0;
      font-size: 0.85rem;
    }
    .sidebar.mobile {
      position: absolute;
      inset: 0;
      width: 100%;
      z-index: 10;
      background: var(--bg2, #e1ded7);
    }
    .editor {
      flex: 1;
      overflow: hidden;
    }
    .editor .ace {
      width: 100%;
      height: 100%;
    }
    .statusbar {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.1rem 0.5rem;
      font-size: 0.75rem;
      background: var(--bg2, #e1ded7);
      flex-shrink: 0;
    }
    .badge {
      border-radius: 4px;
      padding: 0 0.35rem;
      font-size: 0.7rem;
    }
    .badge.connected {
      background: #2e7d32;
      color: #fff;
    }
    .badge.unavailable {
      background: #ddd;
      color: #555;
    }
    .tree-root {
      min-height: 100%;
      min-width: 100%;
    }
    .tree-item {
      padding: 0.15rem 0.5rem;
      cursor: pointer;
      white-space: nowrap;
    }
    .tree-item:hover {
      background: rgba(0, 0, 0, 0.08);
    }
    .contextmenu {
      position: fixed;
      z-index: 20;
      background: #fff;
      border: 1px solid #ccc;
      padding: 0.2rem;
      min-width: 140px;
    }
    .contextmenu button {
      display: block;
      width: 100%;
      text-align: left;
      background: none;
      border: none;
      color: inherit;
      padding: 0.3rem 0.6rem;
      cursor: pointer;
      font-size: 0.85rem;
    }
    .contextmenu button:hover {
      background: rgba(0, 0, 0, 0.08);
    }
    @media (max-width: 768px) {
      .sidebar {
        width: 100%;
      }
    }
  `;

  // tsconfig has useDefineForClassFields on: plain field initializers would
  // create own instance properties that shadow the accessors Lit installs for
  // static properties, so assignments would never schedule a re-render and
  // the tabs would never appear. Declare the types and initialize in the
  // constructor so the reactive accessors stay active.
  declare tabs: Tab[];
  declare activeTab: string | null;
  declare sidebarOpen: boolean;
  declare tree: FileNode[];
  declare lspStatus: 'connected' | 'unavailable' | 'connecting';
  declare contextMenu: {
    x: number;
    y: number;
    path: string;
    isDir: boolean;
  } | null;

  constructor() {
    super();
    this.tabs = [];
    this.activeTab = null;
    this.sidebarOpen = false;
    this.tree = [];
    this.lspStatus = 'unavailable';
    this.contextMenu = null;
  }

  private ws: WebSocket | null = null;
  private _isMobile = window.matchMedia('(max-width: 768px)').matches;

  override firstUpdated() {
    window.addEventListener('beforeunload', this._beforeUnload);
    this._refreshTree();
    this._openFile(RESOURCE);
    this._connectLsp();
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener('beforeunload', this._beforeUnload);
    this.ws?.close();
  }

  private _beforeUnload = (e: BeforeUnloadEvent) => {
    if (this.tabs.some((t) => t.dirty)) {
      e.preventDefault();
      e.returnValue = '';
    }
  };

  private async _api(
    method: 'GET' | 'POST',
    path: string,
    params?: Record<string, string>,
    body?: Record<string, string>
  ): Promise<any> {
    const qs = new URLSearchParams(params || {});
    const url = '/text-editor-plugin/api/' + path + (qs.toString() ? '?' + qs : '');
    const opts: RequestInit = { method };
    if (body) {
      const f = new FormData();
      for (const [k, v] of Object.entries(body)) f.append(k, v);
      opts.body = f;
    }
    const r = await fetch(url, opts);
    if (!r.ok) {
      const j = await r.json().catch(() => ({ error: 'error' }));
      throw new Error(j.error || 'error');
    }
    return r.json();
  }

  private async _refreshTree() {
    try {
      this.tree = await this._api('GET', 'list', { module: MODULE, resource: '' });
    } catch (e) {
      console.error(e);
    }
  }

  private async _openFile(path: string) {
    if (!path) return;
    if (this.tabs.some((t) => t.path === path)) {
      this.activeTab = path;
      this._focusTab();
      return;
    }

    try {
      const j = await this._api('GET', 'read', { module: MODULE, resource: path });
      const tab: Tab = { path, content: j.content, dirty: false, ace: null };
      this.tabs = [...this.tabs, tab];
      this.activeTab = path;
      this._mountAce(path);
    } catch (e) {
      console.error(e);
    }
  }

  private _mountAce(path: string) {
    const tab = this.tabs.find((t) => t.path === path);
    if (!tab) return;
    requestAnimationFrame(() => {
      const el = this.renderRoot.querySelector(`#ace-${CSS.escape(path)}`);
      if (!el || tab.ace) return;
      const ed = ace.edit(el as HTMLElement, {
        mode: this._aceMode(path),
        theme: 'ace/theme/chrome',
        value: tab.content,
        tabSize: 4,
        useSoftTabs: true,
        printMargin: false,
      });
      ed.session.on('change', () => {
        tab.content = ed.getValue();
        tab.dirty = true;
        this.tabs = [...this.tabs];
      });
      tab.ace = ed;
      this.tabs = [...this.tabs];
    });
  }

  private _aceMode(path: string): string {
    const ext = path.split('.').pop()?.toLowerCase();
    return {
      py: 'ace/mode/python',
      ts: 'ace/mode/typescript',
      tsx: 'ace/mode/typescript',
      js: 'ace/mode/javascript',
      jsx: 'ace/mode/javascript',
      mjs: 'ace/mode/javascript',
      json: 'ace/mode/json',
      css: 'ace/mode/css',
      html: 'ace/mode/html',
      htm: 'ace/mode/html',
      yaml: 'ace/mode/yaml',
      yml: 'ace/mode/yaml',
      md: 'ace/mode/markdown',
      go: 'ace/mode/golang',
      rs: 'ace/mode/rust',
      lua: 'ace/mode/lua',
      sh: 'ace/mode/sh',
    }[ext || ''] || 'ace/mode/text';
  }

  private _focusTab() {
    requestAnimationFrame(() => {
      const tab = this.tabs.find((t) => t.path === this.activeTab);
      tab?.ace?.resize();
    });
  }

  private async _save() {
    const tab = this.tabs.find((t) => t.path === this.activeTab);
    if (!tab) return;
    await this._api('POST', 'write', undefined, {
      module: MODULE,
      resource: tab.path,
      content: tab.content,
    });
    tab.dirty = false;
    this.tabs = [...this.tabs];
  }

  private _closeTab(path: string) {
    const tab = this.tabs.find((t) => t.path === path);
    if (tab?.dirty) {
      if (!confirm('Unsaved changes in ' + path + '. Close anyway?')) return;
    }
    this.tabs = this.tabs.filter((t) => t.path !== path);
    if (this.activeTab === path) {
      this.activeTab = this.tabs[this.tabs.length - 1]?.path || null;
    }
  }

  private _connectLsp() {
    this.ws = new WebSocket(
      `/text-editor-plugin/ws/${encodeURIComponent(MODULE)}/${encodeURIComponent(RESOURCE)}`
    );
    this.ws.onopen = () => {
      this.lspStatus = 'connecting';
    };
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'lsp') {
        this.lspStatus = msg.status;
      } else if (msg.type === 'lsp-server') {
        // Forward to the Ace editor for LSP features.
        this._handleLspMessage(msg);
      }
    };
    this.ws.onclose = () => {
      this.lspStatus = 'unavailable';
    };
  }

  private _handleLspMessage(msg: any) {
    // Placeholder for now; LSP features (completions, hovers) are wired
    // into the Ace editor in a later pass.
    console.log('LSP message', msg);
  }

  private _renderTree(nodes: FileNode[], depth = 0): any {
    return nodes.map((n) =>
      html`
        <div
          class="tree-item"
          style="padding-left: ${0.5 + depth * 0.75}rem"
          @click=${() => {
            if (n.type === 'file') this._openFile(n.name);
          }}
          @contextmenu=${(e: Event) => {
            e.preventDefault();
            this.contextMenu = {
              x: (e as MouseEvent).clientX,
              y: (e as MouseEvent).clientY,
              path: n.name,
              isDir: n.type === 'dir',
            };
          }}
        >
          ${n.type === 'dir' ? '📁 ' : '📄 '}${n.name}
        </div>
        ${n.type === 'dir' && n.children ? this._renderTree(n.children, depth + 1) : nothing}
      `
    );
  }

  private async _ctxAction(action: string) {
    const cm = this.contextMenu;
    this.contextMenu = null;
    if (!cm) return;
    const path = cm.path;
    const dir = cm.isDir ? path : path.split('/').slice(0, -1).join('/');

    try {
      if (action === 'newfile') {
        const name = prompt('New file name');
        if (name) {
          await this._api('POST', 'new_file', undefined, {
            module: MODULE,
            resource: dir ? dir + '/' + name : name,
          });
          this._refreshTree();
        }
      } else if (action === 'newfolder') {
        const name = prompt('New folder name');
        if (name) {
          await this._api('POST', 'new_folder', undefined, {
            module: MODULE,
            resource: dir ? dir + '/' + name : name,
          });
          this._refreshTree();
        }
      } else if (action === 'rename') {
        const oldName = path.split('/').pop();
        const name = prompt('New name', oldName);
        if (name) {
          await this._api('POST', 'rename', undefined, {
            module: MODULE,
            resource: path,
            new_name: name,
          });
          this._refreshTree();
        }
      } else if (action === 'delete') {
        if (confirm('Delete ' + path + '?')) {
          await this._api('POST', 'delete', undefined, {
            module: MODULE,
            resource: path,
          });
          this._refreshTree();
        }
      }
    } catch (e) {
      alert('Error: ' + (e as Error).message);
    }
  }

  render() {
    return html`
      <header>
        <button
          @click=${() => (this.sidebarOpen = !this.sidebarOpen)}
          data-testid="sidebar-toggle"
        >
          <span class="mdi mdi-menu"></span>
        </button>
        <span class="mdi mdi-content-save"></span>
        <button @click=${this._save} data-testid="save-btn">Save</button>
        <span style="flex:1"></span>
        <span>${this.activeTab?.split('/').pop() || ''}</span>
      </header>
      <div class="tabbar" data-testid="tabbar">
        ${this.tabs.map(
          (t) => html`
            <div
              class="tab ${t.path === this.activeTab ? 'active' : ''}"
              @click=${() => {
                this.activeTab = t.path;
                this._focusTab();
              }}
            >
              <span>${t.path.split('/').pop()}${t.dirty ? ' •' : ''}</span>
              <span
                class="close"
                @click=${(e: Event) => {
                  e.stopPropagation();
                  this._closeTab(t.path);
                }}
                >✕</span
              >
            </div>
          `
        )}
      </div>
      <div class="main">
        ${this.sidebarOpen
          ? html`
              <div class="sidebar ${this._isMobile ? 'mobile' : ''}" data-testid="sidebar">
                <div
                  class="tree-root"
                  data-testid="tree-root"
                  @contextmenu=${(e: Event) => {
                    e.preventDefault();
                    this.contextMenu = {
                      x: (e as MouseEvent).clientX,
                      y: (e as MouseEvent).clientY,
                      path: '',
                      isDir: true,
                    };
                  }}
                >
                  ${this.tree.length === 0
                    ? html`<div class="tree-item">Right-click to create a file</div>`
                    : nothing}
                  ${this._renderTree(this.tree)}
                </div>
              </div>
            `
          : nothing}
        <div class="editor">
          ${this.tabs.map(
            (t) => html`
              <div
                id="ace-${t.path}"
                style="display: ${t.path === this.activeTab ? 'block' : 'none'};
                       height: 100%"
                data-testid="ace-${t.path}"
              ></div>
            `
          )}
        </div>
        ${this.contextMenu
          ? html`
              <div
                class="contextmenu"
                style="left: ${this.contextMenu.x}px; top: ${this.contextMenu.y}px"
                @click=${() => (this.contextMenu = null)}
              >
                ${this.contextMenu.isDir
                  ? html`
                      <button data-testid="ctx-new-file" @click=${() => this._ctxAction('newfile')}>New file</button>
                      <button data-testid="ctx-new-folder" @click=${() => this._ctxAction('newfolder')}>New folder</button>
                      <button data-testid="ctx-rename" @click=${() => this._ctxAction('rename')}>Rename</button>
                      <button data-testid="ctx-delete" @click=${() => this._ctxAction('delete')}>Delete</button>
                    `
                  : html`
                      <button data-testid="ctx-rename" @click=${() => this._ctxAction('rename')}>Rename</button>
                      <button data-testid="ctx-delete" @click=${() => this._ctxAction('delete')}>Delete</button>
                    `}
              </div>
            `
          : nothing}
      </div>
      <div class="statusbar">
        <span
          class="badge ${this.lspStatus === 'connected' ? 'connected' : 'unavailable'}"
          data-testid="lsp-badge"
        >
          LSP ${this.lspStatus}
        </span>
      </div>
    `;
  }
}

customElements.define('text-editor-page', TextEditorPage);
