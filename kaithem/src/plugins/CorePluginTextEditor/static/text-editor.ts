// SPDX-License-Identifier: GPL-3.0-or-later
// Simple text editor plugin. A micro version of vs code.
// Uses CodeMirror 6, compiled with Vite.
// Lit component, no shadow DOM, works with the global barrel.css theme.

import { LitElement, html, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { basicSetup } from 'codemirror';
import { Compartment, EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import {
  LanguageDescription,
  LanguageSupport,
  StreamLanguage,
  indentUnit,
} from '@codemirror/language';
import { indentWithTab } from '@codemirror/commands';
// The LSP client is pulled in lazily (see _connectLspClient) so its code is
// not part of the initial bundle; only its types are needed here.
import type { LSPClient, Transport } from '@codemirror/lsp-client';

interface Tab {
  path: string;
  content: string;
  dirty: boolean;
  view: EditorView | null;
  // Reconfigured once the language has been lazily loaded and, later, once
  // an LSP client for the language is available.
  langCompartment: Compartment;
  lspCompartment: Compartment;
  lspAttached: boolean;
}

interface FileNode {
  name: string;
  type: 'file' | 'dir';
  size?: number;
  children?: FileNode[];
}

const params = new URLSearchParams(globalThis.location.search);
// Absolute server path of the workspace folder the editor is rooted at,
// plus the workspace-relative path of the file to open first. Both are
// chosen by the /text-editor-plugin/edit redirect, which roots the editor
// at lsp.detect_workspace() of the clicked file.
const WORKSPACE = params.get('workspace') || '';
const FILE = params.get('file') || '';

// Languages are described with LanguageDescription so each grammar is only
// fetched when a file of that language is opened. There is no
// @codemirror/lang-toml, so TOML (and Lua/Shell) use a legacy stream mode.
const LANGUAGES: readonly LanguageDescription[] = [
  LanguageDescription.of({
    name: 'Python',
    alias: ['py'],
    extensions: ['py', 'pyi'],
    load: () => import('@codemirror/lang-python').then((m) => m.python()),
  }),
  LanguageDescription.of({
    name: 'JavaScript',
    alias: ['js'],
    extensions: ['js', 'mjs', 'cjs', 'jsx'],
    load: () =>
      import('@codemirror/lang-javascript').then((m) =>
        m.javascript({ jsx: true })
      ),
  }),
  LanguageDescription.of({
    name: 'TypeScript',
    alias: ['ts'],
    extensions: ['ts', 'tsx'],
    load: () =>
      import('@codemirror/lang-javascript').then((m) =>
        m.javascript({ typescript: true, jsx: true })
      ),
  }),
  LanguageDescription.of({
    name: 'JSON',
    extensions: ['json'],
    load: () => import('@codemirror/lang-json').then((m) => m.json()),
  }),
  LanguageDescription.of({
    name: 'TOML',
    extensions: ['toml'],
    load: () =>
      import('@codemirror/legacy-modes/mode/toml').then(
        (m) => new LanguageSupport(StreamLanguage.define(m.toml))
      ),
  }),
  LanguageDescription.of({
    name: 'YAML',
    extensions: ['yaml', 'yml'],
    load: () => import('@codemirror/lang-yaml').then((m) => m.yaml()),
  }),
  LanguageDescription.of({
    name: 'C++',
    alias: ['cpp'],
    extensions: ['c', 'h', 'cc', 'cpp', 'cxx', 'hpp', 'hh', 'hxx'],
    load: () => import('@codemirror/lang-cpp').then((m) => m.cpp()),
  }),
  LanguageDescription.of({
    name: 'Markdown',
    extensions: ['md', 'markdown'],
    load: () => import('@codemirror/lang-markdown').then((m) => m.markdown()),
  }),
  LanguageDescription.of({
    name: 'Rust',
    extensions: ['rs'],
    load: () => import('@codemirror/lang-rust').then((m) => m.rust()),
  }),
  LanguageDescription.of({
    name: 'HTML',
    extensions: ['html', 'htm'],
    load: () => import('@codemirror/lang-html').then((m) => m.html()),
  }),
  LanguageDescription.of({
    name: 'CSS',
    extensions: ['css'],
    load: () => import('@codemirror/lang-css').then((m) => m.css()),
  }),
  LanguageDescription.of({
    name: 'Lua',
    extensions: ['lua'],
    load: () =>
      import('@codemirror/legacy-modes/mode/lua').then(
        (m) => new LanguageSupport(StreamLanguage.define(m.lua))
      ),
  }),
  LanguageDescription.of({
    name: 'Shell',
    alias: ['sh', 'bash'],
    extensions: ['sh', 'bash'],
    load: () =>
      import('@codemirror/legacy-modes/mode/shell').then(
        (m) => new LanguageSupport(StreamLanguage.define(m.shell))
      ),
  }),
];

// Extension -> language server id. Only languages the backend has an image
// for get an LSP client (see lsp.LANGUAGE_IMAGES); the rest are just
// syntax-highlighted. JS/TS share one image but are separate servers.
const LSP_LANGUAGE_BY_EXT: Record<string, string> = {
  py: 'python',
  js: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  html: 'html',
  htm: 'html',
};

function _ext(path: string): string {
  return path.split('.').pop()?.toLowerCase() || '';
}

// Wrap a websocket as an LSP transport. The messages are raw JSON-RPC
// bodies with no LSP framing, exactly what the backend bridge and the
// container's stdio (behind the bridge) exchange.
function _socketTransport(socket: WebSocket): Transport {
  const handlers = new Set<(value: string) => void>();
  socket.addEventListener('message', (ev) => {
    if (typeof ev.data !== 'string') return;
    for (const handler of handlers) handler(ev.data);
  });
  return {
    send(message) {
      if (socket.readyState !== WebSocket.OPEN)
        throw new Error('LSP socket is not open');
      socket.send(message);
    },
    subscribe(handler) {
      handlers.add(handler);
    },
    unsubscribe(handler) {
      handlers.delete(handler);
    },
  };
}

class TextEditorPage extends LitElement {
  static override properties = {
    tabs: { state: true },
    activeTab: { state: true },
    sidebarOpen: { state: true },
    tree: { state: true },
    lspStatus: { state: true },
    contextMenu: { state: true },
    authRequired: { state: true },
    panel: { state: true },
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
  declare panel: 'chat' | 'snapshots' | null;

  constructor() {
    super();
    this.tabs = [];
    this.activeTab = null;
    this.sidebarOpen = false;
    this.tree = [];
    this.lspStatus = 'unavailable';
    this.contextMenu = null;
    this.authRequired = false;
    this.panel = null;
  }

  private ws: WebSocket | null = null;
  // One websocket, one LSPClient, and one backend language server per
  // language, created lazily the first time a document of that language
  // needs the server.
  private _lspSockets = new Map<string, WebSocket>();
  private _lspClients = new Map<string, LSPClient>();
  private _lspPending = new Map<string, Promise<LSPClient | null>>();
  private _lspReady = new Set<string>();
  private _lspLanguages: string[] = [];
  private _lspInitialized = false;
  private _lspWorkspaceUri = '';
  // Absolute server path of the workspace folder, used to link the chat
  // and snapshot side panels, and as the LSP container mount root.
  private _workspacePath = WORKSPACE;
  private _isMobile = globalThis.matchMedia('(max-width: 768px)').matches;
  private _watchedPaths = new Set<string>();
  private _applyingRemote = false;
  private _contextMenuOpenedAt = 0;

  override firstUpdated() {
    window.addEventListener('beforeunload', this._beforeUnload);
    document.addEventListener('click', this._onDocumentClick);
    if (!WORKSPACE) return;
    this._refreshTree();
    this._openFile(FILE);
    this._connectWatch();
    // Starting an LSP container is heavy, so hold it back until the first
    // frame has painted and the browser is idle. Attachment is idempotent
    // and also happens when a tab is opened later.
    this._afterFirstPaint(() => this._initLsp());
  }

  // Run fn after the browser has painted at least one frame, and preferably
  // while it is idle, so deferred work does not delay first render.
  private _afterFirstPaint(fn: () => void) {
    requestAnimationFrame(() => {
      const ric = (
        globalThis as unknown as {
          requestIdleCallback?: (
            cb: () => void,
            opts?: { timeout: number }
          ) => void;
        }
      ).requestIdleCallback;
      if (ric) ric(fn, { timeout: 2000 });
      else globalThis.setTimeout(fn, 1);
    });
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener('beforeunload', this._beforeUnload);
    document.removeEventListener('click', this._onDocumentClick);
    this.ws?.close();
    for (const tab of this.tabs) tab.view?.destroy();
    for (const client of this._lspClients.values()) client.disconnect();
    this._lspClients.clear();
    this._lspPending.clear();
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
    const url =
      '/text-editor-plugin/api/' + path + (qs.toString() ? '?' + qs : '');
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
    this._openFile(FILE);
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED)
      this._connectWatch();
    if (!this._lspInitialized) this._initLsp();
  }

  private _togglePanel(which: 'chat' | 'snapshots') {
    this.panel = this.panel === which ? null : which;
  }

  private _panelTitle(): string {
    return this.panel === 'chat' ? 'AI Chat' : 'Snapshot backup';
  }

  private _panelUrl(): string {
    if (!this._workspacePath) return '';
    const workspace = encodeURIComponent(this._workspacePath);
    if (this.panel === 'chat') {
      return '/conversations?workspace=' + workspace;
    }
    if (this.panel === 'snapshots') {
      return '/git-snapshots?workspace=' + workspace;
    }
    return '';
  }

  private _wsSend(msg: object) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private _watchPath(path: string) {
    this._watchedPaths.add(path);
    this._wsSend({ type: 'watch', path });
  }

  private _unwatchPath(path: string) {
    this._watchedPaths.delete(path);
    this._wsSend({ type: 'unwatch', path });
  }

  private _applyRemoteContent(path: string, content: string) {
    const tab = this.tabs.find((t) => t.path === path);
    if (!tab || tab.content === content) return;
    tab.content = content;
    if (tab.view) {
      this._applyingRemote = true;
      tab.view.dispatch({
        changes: { from: 0, to: tab.view.state.doc.length, insert: content },
      });
      this._applyingRemote = false;
    }
    this.tabs = [...this.tabs];
  }

  private async _refreshTree() {
    try {
      this.tree = await this._api('GET', 'list', {
        workspace: WORKSPACE,
        path: '',
      });
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
      const j = await this._api('GET', 'read', {
        workspace: WORKSPACE,
        path,
      });
      const tab: Tab = {
        path,
        content: j.content,
        dirty: false,
        view: null,
        langCompartment: new Compartment(),
        lspCompartment: new Compartment(),
        lspAttached: false,
      };
      this.tabs = [...this.tabs, tab];
      this.activeTab = path;
      this._mountEditor(path);
      this._watchPath(path);
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

  private async _mountEditor(path: string) {
    const tab = this.tabs.find((t) => t.path === path);
    if (!tab || tab.view) return;
    // The tab's host element only exists once Lit has rendered it.
    await this.updateComplete;
    const el = this.renderRoot.querySelector(`#cm-${CSS.escape(path)}`);
    if (!el || tab.view) return;
    const view = new EditorView({
      parent: el as HTMLElement,
      state: EditorState.create({
        doc: tab.content,
        extensions: [
          basicSetup,
          EditorState.tabSize.of(4),
          indentUnit.of('    '),
          keymap.of([
            indentWithTab,
            {
              key: 'Mod-s',
              preventDefault: true,
              run: () => {
                this._save();
                return true;
              },
            },
          ]),
          tab.langCompartment.of([]),
          tab.lspCompartment.of([]),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged || this._applyingRemote) return;
            const value = update.state.doc.toString();
            // Ignore the echo of a remote apply if the change event fires
            // after _applyingRemote was cleared.
            if (value === tab.content) return;
            tab.content = value;
            tab.dirty = true;
            this.tabs = [...this.tabs];
          }),
        ],
      }),
    });
    tab.view = view;
    this._loadLanguage(tab);
    this._attachLsp(tab);
    this.tabs = [...this.tabs];
  }

  private async _loadLanguage(tab: Tab) {
    const desc = LanguageDescription.matchFilename(
      LANGUAGES,
      tab.path.toLowerCase()
    );
    if (!desc) return;
    try {
      const support = await desc.load();
      if (!tab.view) return;
      tab.view.dispatch({
        effects: tab.langCompartment.reconfigure(support),
      });
    } catch (error) {
      console.error(error);
    }
  }

  private _focusTab() {
    requestAnimationFrame(() => {
      const tab = this.tabs.find((t) => t.path === this.activeTab);
      tab?.view?.requestMeasure();
    });
  }

  private async _save() {
    const tab = this.tabs.find((t) => t.path === this.activeTab);
    if (!tab) return;
    // Read the live value straight from the editor so we never save a
    // stale buffer.
    const content = tab.view ? tab.view.state.doc.toString() : tab.content;
    try {
      await this._api('POST', 'write', undefined, {
        workspace: WORKSPACE,
        path: tab.path,
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
    if (
      tab?.dirty &&
      !confirm('Unsaved changes in ' + path + '. Close anyway?')
    )
      return;
    tab?.view?.destroy();
    if (tab) {
      tab.view = null;
      tab.lspAttached = false;
    }
    this.tabs = this.tabs.filter((t) => t.path !== path);
    this._unwatchPath(path);
    if (this.activeTab === path) {
      this.activeTab = this.tabs.at(-1)?.path || null;
    }
  }

  private _connectWatch() {
    const qs = new URLSearchParams({ workspace: WORKSPACE });
    this.ws = new WebSocket('/text-editor-plugin/ws?' + qs);
    this.ws.addEventListener('open', () => {
      // (Re)subscribe to any files opened before the socket was ready.
      for (const p of this._watchedPaths) {
        this._wsSend({ type: 'watch', path: p });
      }
    });
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'file-changed') {
        this._applyRemoteContent(msg.path, msg.content);
      }
    };
  }

  private async _initLsp() {
    if (this._lspInitialized) return;
    try {
      const info = await this._api('GET', 'lsp_info', {
        workspace: WORKSPACE,
      });
      this._lspLanguages = info.languages || [];
      this._workspacePath = info.workspacePath || '';
      this._lspWorkspaceUri = 'file:///workspace';
      if (this._lspLanguages.length === 0) {
        this.lspStatus = 'unavailable';
        return;
      }
      this.lspStatus = 'connecting';
      this._lspInitialized = true;
      // Tabs opened before the language list arrived were not attached yet.
      for (const tab of this.tabs) this._attachLsp(tab);
      this._refreshLspStatus();
    } catch (error) {
      this.lspStatus = 'unavailable';
      console.error(error);
    }
  }

  private _lspSocketFor(lang: string): WebSocket {
    const existing = this._lspSockets.get(lang);
    if (existing) return existing;
    const qs = new URLSearchParams({ workspace: WORKSPACE, language: lang });
    const socket = new WebSocket('/text-editor-plugin/lsp-ws?' + qs);
    this._lspSockets.set(lang, socket);
    // Use addEventListener (not onopen/onclose) so nothing else is clobbered.
    // "Ready" is not set here: a socket being open says nothing about the
    // language server having finished its initialize handshake.
    socket.addEventListener('open', () => {
      this._refreshLspStatus();
    });
    socket.addEventListener('close', () => {
      this._lspReady.delete(lang);
      this._lspSockets.delete(lang);
      this._refreshLspStatus();
    });
    return socket;
  }

  private _lspClientFor(lang: string): Promise<LSPClient | null> {
    let pending = this._lspPending.get(lang);
    if (!pending) {
      pending = this._connectLspClient(lang);
      this._lspPending.set(lang, pending);
    }
    return pending;
  }

  private _connectLspClient(lang: string): Promise<LSPClient | null> {
    const socket = this._lspSocketFor(lang);
    return new Promise((resolve) => {
      const start = async () => {
        let mod: typeof import('@codemirror/lsp-client');
        try {
          mod = await import('@codemirror/lsp-client');
        } catch (error) {
          console.error('Failed to load the LSP client', error);
          this._lspPending.delete(lang);
          resolve(null);
          return;
        }
        const { LSPClient, languageServerExtensions } = mod;
        const client = new LSPClient({
          rootUri: this._lspWorkspaceUri,
          // The client defaults every request to a 3s timeout, but
          // ``initialize`` is sent the moment the socket opens while the
          // backend is still starting (and possibly pulling) the podman
          // container, which routinely takes longer. Give it room so the
          // handshake does not abort and leave the client unusable.
          timeout: 60000,
          extensions: languageServerExtensions(),
        });
        this._lspClients.set(lang, client);
        const onClose = () => {
          client.disconnect();
          this._lspClients.delete(lang);
          this._lspPending.delete(lang);
          this._lspReady.delete(lang);
          this._refreshLspStatus();
        };
        socket.addEventListener('close', onClose);
        client.connect(_socketTransport(socket));
        try {
          // Notifications (didOpen, didChange, ...) and requests wait on
          // ``initializing``, so the client is only usable once it settles.
          await client.initializing;
          this._lspReady.add(lang);
          this._refreshLspStatus();
          resolve(client);
        } catch (error) {
          console.error('LSP initialize failed for ' + lang, error);
          socket.removeEventListener('close', onClose);
          client.disconnect();
          this._lspClients.delete(lang);
          // Clear the cached promise so a later attempt can retry.
          this._lspPending.delete(lang);
          this._refreshLspStatus();
          resolve(null);
        }
      };
      if (socket.readyState === WebSocket.OPEN) {
        start();
        return;
      }
      const onOpen = () => {
        cleanup();
        start();
      };
      const onFail = () => {
        cleanup();
        this._lspPending.delete(lang);
        resolve(null);
      };
      const cleanup = () => {
        socket.removeEventListener('open', onOpen);
        socket.removeEventListener('close', onFail);
        socket.removeEventListener('error', onFail);
      };
      socket.addEventListener('open', onOpen);
      socket.addEventListener('close', onFail);
      socket.addEventListener('error', onFail);
    });
  }

  private _refreshLspStatus() {
    if (this._lspReady.size > 0) this.lspStatus = 'connected';
    else if (this._lspSockets.size > 0) this.lspStatus = 'connecting';
    else this.lspStatus = 'unavailable';
  }

  private _lspUriFor(path: string): string {
    // The workspace is always mounted at /workspace in the container, so
    // a workspace-relative path maps straight onto the file URI.
    const encoded = path
      .split('/')
      .map((s) => encodeURIComponent(s))
      .join('/');
    return this._lspWorkspaceUri + '/' + encoded;
  }

  private _languageForPath(path: string): string | null {
    const lang = LSP_LANGUAGE_BY_EXT[_ext(path)];
    return lang && this._lspLanguages.includes(lang) ? lang : null;
  }

  private async _attachLsp(tab: Tab) {
    if (tab.lspAttached || !tab.view) return;
    // Languages without a configured server (e.g. .css, .rs, .lua) are not
    // in _lspLanguages; attaching them would open a socket for a language
    // the backend has no image for.
    const lang = this._languageForPath(tab.path);
    if (!lang) return;
    const client = await this._lspClientFor(lang);
    if (!client || !tab.view || tab.lspAttached) return;
    try {
      tab.view.dispatch({
        effects: tab.lspCompartment.reconfigure(
          client.plugin(this._lspUriFor(tab.path), lang)
        ),
      });
      tab.lspAttached = true;
    } catch (error) {
      console.error(error);
    }
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
              workspace: WORKSPACE,
              path: dir ? dir + '/' + name : name,
            });
            this._refreshTree();
          }

          break;
        }
        case 'newfolder': {
          const name = prompt('New folder name');
          if (name) {
            await this._api('POST', 'new_folder', undefined, {
              workspace: WORKSPACE,
              path: dir ? dir + '/' + name : name,
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
              workspace: WORKSPACE,
              path,
              new_name: name,
            });
            this._refreshTree();
          }

          break;
        }
        case 'delete': {
          if (confirm('Delete ' + path + '?')) {
            await this._api('POST', 'delete', undefined, {
              workspace: WORKSPACE,
              path,
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
    if (!WORKSPACE) {
      return html`
        <div class="splash" data-testid="no-workspace-splash">
          <div class="splash-box">
            <div class="splash-icon mdi mdi-folder-off-outline"></div>
            <h1>No folder to edit</h1>
            <p>
              This editor works on a folder. Open it from a file's actions menu
              so the folder can be detected.
            </p>
          </div>
        </div>
      `;
    }
    return html`
      <header>
        <tool-bar>
          <button
            @click="${() => (this.sidebarOpen = !this.sidebarOpen)}"
            data-testid="sidebar-toggle"
          >
            <span class="mdi mdi-file-tree"></span>
          </button>

          <button @click="${this._save}" data-testid="save-btn">
            <span class="mdi mdi-content-save"></span>Save
          </button>
          <button
            @click="${() => this._togglePanel('chat')}"
            data-testid="chat-toggle"
            title="AI chat for this workspace"
          >
            <span class="mdi mdi-robot"></span>Chat
          </button>
          <button
            @click="${() => this._togglePanel('snapshots')}"
            data-testid="snapshots-toggle"
            title="Snapshot backup for this workspace"
          >
            <span class="mdi mdi-history"></span>Snapshots
          </button>
        </tool-bar>
      </header>
      <div class="tool-bar" data-testid="tabbar">
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
              <div
                class="sidebar h-pane paper ${this._isMobile ? 'mobile' : ''}"
                data-testid="sidebar"
              >
                <div
                  class="tree-root"
                  data-testid="tree-root"
                  @contextmenu="${(e: Event) =>
                    this._openContextMenu(e as MouseEvent, '', true)}"
                >
                  ${this.tree.length === 0
                    ? html`<div class="tree-item">
                        Right-click to create a file
                      </div>`
                    : nothing}
                  ${this._renderTree(this.tree)}
                </div>
              </div>
            `
          : nothing}
        <div class="editor">
          ${repeat(
            this.tabs,
            (t) => t.path,
            (t) => html`
              <div
                class="cm-host"
                id="cm-${t.path}"
                style="display: ${t.path === this.activeTab ? 'block' : 'none'}"
                data-testid="cm-${t.path}"
              ></div>
            `
          )}
        </div>
        ${this.panel
          ? html`
              <div
                class="panel paper h-pane ${this._isMobile ? 'mobile' : ''}"
                data-testid="panel"
              >
                <div class="panel-head">
                  <span class="panel-title">${this._panelTitle()}</span>
                  <button
                    class="panel-close"
                    data-testid="panel-close"
                    @click="${() => (this.panel = null)}"
                  >
                    ✕
                  </button>
                </div>
                ${this._workspacePath
                  ? html`
                      <iframe
                        class="panel-frame"
                        data-testid="panel-frame"
                        title="${this._panelTitle()}"
                        src="${this._panelUrl()}"
                      ></iframe>
                    `
                  : html`
                      <div class="panel-empty" data-testid="panel-empty">
                        This file is not inside a workspace folder, so there is
                        nothing to show here.
                      </div>
                    `}
              </div>
            `
          : nothing}
        ${this.contextMenu
          ? html`
              <div
                class="contextmenu"
                style="left: ${this.contextMenu.x}px; top: ${this.contextMenu
                  .y}px"
                @click="${() => (this.contextMenu = null)}"
              >
                ${this.contextMenu.isDir
                  ? html`
                      <button
                        data-testid="ctx-new-file"
                        @click="${() => this._ctxAction('newfile')}"
                      >
                        New file
                      </button>
                      <button
                        data-testid="ctx-new-folder"
                        @click="${() => this._ctxAction('newfolder')}"
                      >
                        New folder
                      </button>
                      <button
                        data-testid="ctx-rename"
                        @click="${() => this._ctxAction('rename')}"
                      >
                        Rename
                      </button>
                      <button
                        data-testid="ctx-delete"
                        @click="${() => this._ctxAction('delete')}"
                      >
                        Delete
                      </button>
                    `
                  : html`
                      <button
                        data-testid="ctx-rename"
                        @click="${() => this._ctxAction('rename')}"
                      >
                        Rename
                      </button>
                      <button
                        data-testid="ctx-delete"
                        @click="${() => this._ctxAction('delete')}"
                      >
                        Delete
                      </button>
                    `}
              </div>
            `
          : nothing}
      </div>
      <div class="statusbar">
        <span
          class="badge ${this.lspStatus === 'connected'
            ? 'success'
            : ''}"
          data-testid="lsp-badge"
        >
          LSP ${this.lspStatus}
        </span>
      </div>
    `;
  }
}

customElements.define('text-editor-page', TextEditorPage);
