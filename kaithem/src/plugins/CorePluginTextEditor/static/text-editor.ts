// SPDX-License-Identifier: GPL-3.0-or-later
// Simple text editor plugin. A micro version of vs code.
// Uses Ace editor, compiled with Vite.
// Lit component, no shadow DOM, works with the global barrel.css theme.

import { LitElement, html, nothing } from 'lit';
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
// ext-language_tools defines editor.completers and enableBasicAutocompletion.
// ace-linters pushes its completer into editor.completers, which only exists
// once this extension is loaded, so without it LSP completion silently does
// nothing.
import 'ace-builds/src-noconflict/ext-language_tools';
import 'ace-builds/src-noconflict/theme-chrome';

// ace-linters connects Ace to a language server over a websocket and wires
// up completions, hover, diagnostics, etc. It is self-contained and does not
// import ace-builds at runtime.
import { AceLanguageClient } from 'ace-linters/build/ace-language-client';

interface Tab {
  path: string;
  content: string;
  dirty: boolean;
  ace: Editor | null;
  lspRegistered?: boolean;
}

interface FileNode {
  name: string;
  type: 'file' | 'dir';
  size?: number;
  children?: FileNode[];
}

const params = new URLSearchParams(globalThis.location.search);
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
    authRequired: { state: true },
  };

  override createRenderRoot() {
    return this;
  }
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
  declare authRequired: boolean;

  constructor() {
    super();
    this.tabs = [];
    this.activeTab = null;
    this.sidebarOpen = false;
    this.tree = [];
    this.lspStatus = 'unavailable';
    this.contextMenu = null;
    this.authRequired = false;
  }

  private ws: WebSocket | null = null;
  private lspProvider: any = null;
  // One websocket (and one backend language server) per language, created
  // lazily the first time a document of that language needs the server.
  private _lspSockets = new Map<string, WebSocket>();
  private _lspReady = new Set<string>();
  private _lspLanguages: string[] = [];
  private _lspInitialized = false;
  private _lspWorkspaceUri = '';
  private _lspModuleBaseRel = '';
  private _isMobile = globalThis.matchMedia('(max-width: 768px)').matches;
  private _watchedResources = new Set<string>();
  private _applyingRemote = false;
  private _contextMenuOpenedAt = 0;

  override firstUpdated() {
    window.addEventListener('beforeunload', this._beforeUnload);
    document.addEventListener('click', this._onDocumentClick);
    this._refreshTree();
    this._openFile(RESOURCE);
    this._connectWatch();
    this._initLsp();
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener('beforeunload', this._beforeUnload);
    document.removeEventListener('click', this._onDocumentClick);
    this.ws?.close();
    for (const socket of this._lspSockets.values()) socket.close();
    this._lspSockets.clear();
    this._lspReady.clear();
  }

  private _onDocumentClick = () => {
    if (!this.contextMenu) return;
    // Some touch devices emit a synthetic click right after a long-press
    // opens the menu; ignore it so the menu is not dismissed instantly.
    if (Date.now() - this._contextMenuOpenedAt < 350) return;
    this.contextMenu = null;
  };

  private _openContextMenu(e: MouseEvent, path: string, isDir: boolean) {
    e.preventDefault();
    this._contextMenuOpenedAt = Date.now();
    this.contextMenu = { x: e.clientX, y: e.clientY, path, isDir };
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
      // The backend returns 401 not_logged_in (instead of redirecting to the
      // login page) when the user is not authenticated, so we can show a
      // full-screen splash rather than silently rendering a login page.
      if (r.status === 401 && j.error === 'not_logged_in') {
        this.authRequired = true;
      }
      throw new Error(j.error || 'error');
    }
    return r.json();
  }

  private _b64(value: string): string {
    const bytes = new TextEncoder().encode(value);
    let bin = '';
    for (const b of bytes) bin += String.fromCharCode(b);
    return btoa(bin);
  }

  private _login() {
    // Send the user to the login page and come back here afterwards.
    globalThis.location.href =
      '/login?go=' + encodeURIComponent(this._b64(globalThis.location.href));
  }

  private _retry() {
    this.authRequired = false;
    this._refreshTree();
    this._openFile(RESOURCE);
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED) this._connectWatch();
    if (!this._lspInitialized) this._initLsp();
  }

  private _wsSend(msg: object) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private _watchResource(path: string) {
    this._watchedResources.add(path);
    this._wsSend({ type: 'watch', resource: path });
  }

  private _unwatchResource(path: string) {
    this._watchedResources.delete(path);
    this._wsSend({ type: 'unwatch', resource: path });
  }

  private _applyRemoteContent(resource: string, content: string) {
    const tab = this.tabs.find((t) => t.path === resource);
    // Never clobber unsaved local edits, and skip no-op updates (e.g. the
    // echo of our own save).
    if (!tab || tab.dirty || tab.content === content) return;
    tab.content = content;
    if (tab.ace) {
      this._applyingRemote = true;
      tab.ace.setValue(content, -1);
      this._applyingRemote = false;
    }
    this.tabs = [...this.tabs];
  }

  private async _refreshTree() {
    try {
      this.tree = await this._api('GET', 'list', { module: MODULE, resource: '' });
    } catch (error) {
      console.error(error);
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
      this._watchResource(path);
    } catch (error) {
      const msg = (error as Error).message;
      switch (msg) {
      case 'too_large': {
        alert('This file is 5MB or larger and cannot be opened.');
      
      break;
      }
      case 'binary': {
        alert('This file is not a plain text file.');
      
      break;
      }
      case 'not_a_file': {
        alert('That path is not a file.');
      
      break;
      }
      default: {
        alert('Could not open file: ' + msg);
      }
      }
      console.error(error);
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

      ed.setOptions({
          enableBasicAutocompletion: true,
          enableLiveAutocompletion: false
      });
    
      // Ace injects its base editor CSS into document.head by default. Inside
      // a shadow root that CSS is invisible to the editor, leaving .ace_scroller
      // position:static and all layers off-screen. Inject the base CSS into the
      // shadow root that actually contains the editor element.
      (ed.renderer as any).attachToShadowRoot();
      ed.session.on('change', () => {
        if (this._applyingRemote) return;
        const value = ed.getValue();
        // Ignore the echo of a remote apply if the change event fires
        // asynchronously (after _applyingRemote was cleared).
        if (value === tab.content) return;
        tab.content = value;
        tab.dirty = true;
        this.tabs = [...this.tabs];
      });
      tab.ace = ed;
      this._registerLspEditor(tab);
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
    // Read the live value straight from Ace so we never save a stale buffer.
    const content = tab.ace ? tab.ace.getValue() : tab.content;
    try {
      await this._api('POST', 'write', undefined, {
        module: MODULE,
        resource: tab.path,
        content,
      });
      tab.content = content;
      tab.dirty = false;
      this.tabs = [...this.tabs];
    } catch (error) {
      const msg = (error as Error).message;
      if (msg === 'too_large') {
        alert('This file is 5MB or larger and cannot be saved.');
      } else {
        alert('Could not save file: ' + msg);
      }
      console.error(error);
    }
  }

  private _closeTab(path: string) {
    const tab = this.tabs.find((t) => t.path === path);
    if (tab?.dirty && !confirm('Unsaved changes in ' + path + '. Close anyway?')) return;
    this._unregisterLspEditor(tab);
    this.tabs = this.tabs.filter((t) => t.path !== path);
    this._unwatchResource(path);
    if (this.activeTab === path) {
      this.activeTab = this.tabs.at(-1)?.path || null;
    }
  }

  private _connectWatch() {
    this.ws = new WebSocket(
      `/text-editor-plugin/ws/${encodeURIComponent(MODULE)}/${encodeURIComponent(RESOURCE)}`
    );
    this.ws.addEventListener('open', () => {
      // (Re)subscribe to any files opened before the socket was ready.
      for (const r of this._watchedResources) {
        this._wsSend({ type: 'watch', resource: r });
      }
    });
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'file-changed') {
        this._applyRemoteContent(msg.resource, msg.content);
      }
    };
  }

  private async _initLsp() {
    if (this._lspInitialized) return;
    try {
      const info = await this._api('GET', 'lsp_info', { module: MODULE });
      this._lspLanguages = info.languages || [];
      if (!this._lspLanguages.length || !info.workspaceUri) {
        this.lspStatus = 'unavailable';
        return;
      }
      this._lspWorkspaceUri = info.workspaceUri;
      this._lspModuleBaseRel = info.moduleBaseRel || '';
      this.lspStatus = 'connecting';

      // A single provider serves every language: ace-linters keys every
      // request callback by the provider instance, so calling for() more
      // than once would make responses go to the wrong editor. Each language
      // gets its own server (and its own socket) via the config array; the
      // socket is created lazily by _lspSocketFor the first time the
      // language is actually used.
      const self = this;
      this.lspProvider = AceLanguageClient.for(
        this._lspLanguages.map((lang: string) => ({
          serviceName: lang,
          module: () => import('ace-linters/build/language-client'),
          modes: lang,
          type: 'socket' as const,
          get socket() {
            return self._lspSocketFor(lang);
          },
        })),
        { workspacePath: this._lspWorkspaceUri }
      );
      this.lspProvider.changeWorkspaceFolder(this._lspWorkspaceUri);
      this._lspInitialized = true;
      this._registerAllLspEditors();
      this._refreshLspStatus();
    } catch (error) {
      this.lspStatus = 'unavailable';
      console.error(error);
    }
  }

  private _lspSocketFor(lang: string): WebSocket {
    const existing = this._lspSockets.get(lang);
    if (existing) return existing;
    const socket = new WebSocket(
      `/text-editor-plugin/lsp-ws/${encodeURIComponent(MODULE)}/${encodeURIComponent(lang)}`
    );
    this._lspSockets.set(lang, socket);
    // Use addEventListener (not onopen/onclose) because ace-linters assigns
    // the socket's on* properties itself.
    socket.addEventListener('open', () => {
      this._lspReady.add(lang);
      this._refreshLspStatus();
    });
    socket.addEventListener('close', () => {
      this._lspReady.delete(lang);
      this._lspSockets.delete(lang);
      this._refreshLspStatus();
    });
    return socket;
  }

  private _refreshLspStatus() {
    if (this._lspReady.size > 0) this.lspStatus = 'connected';
    else if (this._lspSockets.size > 0) this.lspStatus = 'connecting';
    else this.lspStatus = 'unavailable';
  }

  private _lspUriFor(path: string): string {
    const rel = this._lspModuleBaseRel
      ? this._lspModuleBaseRel + '/' + path
      : path;
    const encoded = rel
      .split('/')
      .map((s) => encodeURIComponent(s))
      .join('/');
    return this._lspWorkspaceUri + '/' + encoded;
  }

  private _languageForPath(path: string): string | null {
    const mode = this._aceMode(path).slice('ace/mode/'.length);
    return this._lspLanguages.includes(mode) ? mode : null;
  }

  private _registerAllLspEditors() {
    for (const t of this.tabs) {
      if (t.ace) this._registerLspEditor(t);
    }
  }

  private _registerLspEditor(tab: Tab) {
    if (!this.lspProvider || !tab.ace || tab.lspRegistered) return;
    // Languages without a configured server (e.g. .go, .lua, .sh) are not
    // in _lspLanguages; registering them would create a socket for a
    // language the backend has no image for.
    if (!this._languageForPath(tab.path)) return;
    try {
      this.lspProvider.registerEditor(tab.ace, {
        filePath: this._lspUriFor(tab.path),
      });
      tab.lspRegistered = true;
    } catch (error) {
      console.error(error);
    }
  }

  private _unregisterLspEditor(tab: Tab | undefined) {
    if (!this.lspProvider || !tab?.ace || !tab.lspRegistered) return;
    try {
      this.lspProvider.unregisterEditor(tab.ace, true);
    } catch (error) {
      console.error(error);
    }
    tab.lspRegistered = false;
  }

  private _renderTree(nodes: FileNode[], depth = 0, parentPath = ''): any {
    return nodes.map((n) => {
      const fullPath = parentPath ? parentPath + '/' + n.name : n.name;
      return html`
        <div
          class="tree-item"
          style="padding-left: ${0.5 + depth * 0.75}rem"
          @click="${() => {
            if (n.type === 'file') this._openFile(fullPath);
          }}"
          @contextmenu="${(e: Event) =>
            this._openContextMenu(e as MouseEvent, fullPath, n.type === 'dir')}"
        >
          ${n.type === 'dir' ? '📁 ' : '📄 '}${n.name}
        </div>
        ${n.type === 'dir' && n.children
          ? this._renderTree(n.children, depth + 1, fullPath)
          : nothing}
      `;
    });
  }

  private async _ctxAction(action: string) {
    const cm = this.contextMenu;
    this.contextMenu = null;
    if (!cm) return;
    const path = cm.path;
    const dir = cm.isDir ? path : path.split('/').slice(0, -1).join('/');

    try {
      switch (action) {
      case 'newfile': {
        const name = prompt('New file name');
        if (name) {
          await this._api('POST', 'new_file', undefined, {
            module: MODULE,
            resource: dir ? dir + '/' + name : name,
          });
          this._refreshTree();
        }
      
      break;
      }
      case 'newfolder': {
        const name = prompt('New folder name');
        if (name) {
          await this._api('POST', 'new_folder', undefined, {
            module: MODULE,
            resource: dir ? dir + '/' + name : name,
          });
          this._refreshTree();
        }
      
      break;
      }
      case 'rename': {
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
      
      break;
      }
      case 'delete': {
        if (confirm('Delete ' + path + '?')) {
          await this._api('POST', 'delete', undefined, {
            module: MODULE,
            resource: path,
          });
          this._refreshTree();
        }
      
      break;
      }
      // No default
      }
    } catch (error) {
      alert('Error: ' + (error as Error).message);
    }
  }

  render() {
    if (this.authRequired) {
      return html`
        <div class="splash" data-testid="auth-splash">
          <div class="splash-box">
            <div class="splash-icon mdi mdi-lock-outline"></div>
            <h1>Not logged in</h1>
            <p>You need to sign in to use the text editor.</p>
            <div class="splash-actions">
              <button data-testid="auth-login" @click="${this._login}">
                Log in
              </button>
              <button data-testid="auth-retry" @click="${this._retry}">
                Retry
              </button>
            </div>
          </div>
        </div>
      `;
    }
    return html`
      <header>
        <button
          @click="${() => (this.sidebarOpen = !this.sidebarOpen)}"
          data-testid="sidebar-toggle"
        >
          <span class="mdi mdi-file-tree"></span>
        </button>
        
        <button @click="${this._save}" data-testid="save-btn">
        <span class="mdi mdi-content-save"></span>Save
        </button>
        <span style="flex:1"></span>
        <span>${this.activeTab?.split('/').pop() || ''}</span>
      </header>
      <div class="tabbar" data-testid="tabbar">
        ${this.tabs.map(
          (t) => html`
            <div
              class="tab ${t.path === this.activeTab ? 'active' : ''}"
              @click="${() => {
                this.activeTab = t.path;
                this._focusTab();
              }}"
            >
              <span>${t.path.split('/').pop()}${t.dirty ? ' •' : ''}</span>
              <span
                class="close"
                @click="${(e: Event) => {
                  e.stopPropagation();
                  this._closeTab(t.path);
                }}"
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
                  @contextmenu="${(e: Event) =>
                    this._openContextMenu(e as MouseEvent, '', true)}"
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
                @click="${() => (this.contextMenu = null)}"
              >
                ${this.contextMenu.isDir
                  ? html`
                      <button data-testid="ctx-new-file" @click="${() => this._ctxAction('newfile')}">New file</button>
                      <button data-testid="ctx-new-folder" @click="${() => this._ctxAction('newfolder')}">New folder</button>
                      <button data-testid="ctx-rename" @click="${() => this._ctxAction('rename')}">Rename</button>
                      <button data-testid="ctx-delete" @click="${() => this._ctxAction('delete')}">Delete</button>
                    `
                  : html`
                      <button data-testid="ctx-rename" @click="${() => this._ctxAction('rename')}">Rename</button>
                      <button data-testid="ctx-delete" @click="${() => this._ctxAction('delete')}">Delete</button>
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
