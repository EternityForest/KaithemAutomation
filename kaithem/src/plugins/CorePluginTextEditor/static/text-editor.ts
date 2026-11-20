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
import {
  breakpointGutter,
  getBreakpointLines,
  toggleBreakpoint,
} from './breakpoints.ts';
import { execLineExtension, setExecLine } from './exec-line.ts';
import { DebuggerClient } from './dap.ts';
import type {
  DapEventBody,
  DapSource,
  DapStackFrame,
  DapStatus,
  DapThread,
} from './dap.ts';

// How a tab was opened.  Workspace files are editable and watched; disk
// files (absolute paths outside the workspace) and virtual sources (DAP
// ``source`` references) are read-only and never saved or watched.
type TabKind = 'workspace' | 'disk' | 'virtual';

interface Tab {
  path: string;
  content: string;
  dirty: boolean;
  view: EditorView | null;
  kind: TabKind;
  readonly: boolean;
  // Set for virtual sources so their content can be re-fetched and
  // breakpoints can be set against the right source.
  sourceReference?: number;
  // Reconfigured once the language has been lazily loaded and, later, once
  // an LSP client for the language is available.
  langCompartment: Compartment;
  lspCompartment: Compartment;
  lspAttached: boolean;
}

// One thread the debugger is stopped in, with its call stack.
interface StoppedThread {
  id: number;
  name: string;
  frames: DapStackFrame[];
}

// One line in the debug console.
interface ConsoleLine {
  kind: 'input' | 'output' | 'error';
  text: string;
}

// One breakpoint shown in the sidebar list.
interface BreakpointView {
  path: string;
  line: number;
  // Set for breakpoints in a virtual source, so they can be sent to the
  // adapter by reference instead of by path.
  sourceReference?: number;
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
// Raw DAP websocket address of a debug adapter.  When present the
// debugger sidebar is enabled and the editor connects to it.
const DAP_URL = params.get('dap') || '';

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

// Collapse "." and ".." segments and duplicate slashes so the same file
// always compares equal no matter how its path was written. Absolute and
// relative paths are kept distinct; a trailing slash is dropped.
function normalizePath(path: string): string {
  const absolute = path.startsWith('/');
  const out: string[] = [];
  for (const part of path.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') {
      // Never step above the root of an absolute path.
      if (out.length > 0 && out.at(-1) !== '..') out.pop();
      else if (!absolute) out.push('..');
      continue;
    }
    out.push(part);
  }
  const joined = out.join('/');
  if (absolute) return '/' + joined;
  return joined || '.';
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
    collapsed: { state: true },
    lspStatus: { state: true },
    contextMenu: { state: true },
    authRequired: { state: true },
    panel: { state: true },
    debuggerOpen: { state: true },
    dapStatus: { state: true },
    debugThreads: { state: true },
    consoleLines: { state: true },
    breakpoints: { state: true },
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
  // Workspace-relative paths of folders the user has collapsed in the
  // sidebar. Folders are expanded unless their path is in here, so new
  // folders appear expanded by default.
  declare collapsed: Set<string>;
  declare lspStatus: 'connected' | 'unavailable' | 'connecting';
  declare contextMenu: {
    x: number;
    y: number;
    path: string;
    isDir: boolean;
  } | null;
  declare authRequired: boolean;
  declare panel: 'chat' | 'snapshots' | null;
  declare debuggerOpen: boolean;
  declare dapStatus: DapStatus;
  declare debugThreads: StoppedThread[];
  declare consoleLines: ConsoleLine[];
  declare breakpoints: BreakpointView[];

  constructor() {
    super();
    this.tabs = [];
    this.activeTab = null;
    this.sidebarOpen = false;
    this.tree = [];
    this.collapsed = new Set();
    this.lspStatus = 'unavailable';
    this.contextMenu = null;
    this.authRequired = false;
    this.panel = null;
    // A DAP address in the URL turns the debugger sidebar on by default.
    this.debuggerOpen = Boolean(DAP_URL);
    this.dapStatus = 'disconnected';
    this.debugThreads = [];
    this.consoleLines = [];
    this.breakpoints = [];
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
  private _watchedPaths = new Set<string>();
  private _applyingRemote = false;
  private _contextMenuOpenedAt = 0;
  // The debug adapter connection, plus the console's input history.
  private _dap: DebuggerClient | null = null;
  private _dapInitialized = false;
  // Bumped every time a new connection is opened so late events and status
  // changes from a torn-down client are ignored.
  private _dapGeneration = 0;
  private _consoleHistory: string[] = [];
  private _consoleIndex = 0;
  private _consoleDraft = '';
  // Debounces pushing breakpoints to the adapter while the document is
  // edited, so a burst of keystrokes sends a single setBreakpoints.
  private _bpTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
  // The sources the adapter currently knows breakpoints for, keyed the
  // same way as the setBreakpoints request.  When a source drops out of
  // the current set we still have to send it an empty list to clear it.
  private _bpSentSources = new Map<string, DapSource>();
  // A trailing line fragment from the adapter's streamed output, held
  // until its newline arrives so the console does not show blank lines.
  private _consolePartial = '';

  override firstUpdated() {
    window.addEventListener('beforeunload', this._beforeUnload);
    document.addEventListener('click', this._onDocumentClick);
    if (!WORKSPACE) return;
    this._refreshTree();
    this._openFile(FILE);
    this._connectWatch();
    // The debug adapter is a plain websocket, so connect straight away.
    if (DAP_URL) this._connectDap();
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
    this._dapGeneration++;
    this._dap?.disconnect();
    this._dap = null;
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
    // The right side of the window is shared, so the debugger and a side
    // panel are never open at once.
    if (this.panel) this.debuggerOpen = false;
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
    const tab = this.tabs.find((t) => t.path === this._canonicalPath(path));
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

  // Resolve a path to the editor's canonical form: a path that lies inside
  // the workspace collapses to workspace-relative, so the same file opened
  // as a workspace file or reached through an absolute path (e.g. a
  // debugger stack frame) maps to one tab and one breakpoint source.
  private _canonicalPath(path: string): string {
    const normalized = normalizePath(path);
    if (!normalized.startsWith('/')) return normalized;
    const root = normalizePath(this._workspacePath);
    if (root && root !== '/') {
      if (normalized === root) return '';
      if (normalized.startsWith(root + '/'))
        return normalized.slice(root.length + 1);
    }
    return normalized;
  }

  private async _openFile(
    path: string,
    options: { line?: number; silent?: boolean } = {}
  ) {
    const key = this._canonicalPath(path);
    if (!key) return;
    const existing = this.tabs.find((t) => t.path === key);
    if (existing) {
      this.activeTab = key;
      if (options.line === undefined) this._focusTab();
      else this._revealLine(existing, options.line, !options.silent);
      return;
    }

    try {
      const j = await this._api('GET', 'read', {
        workspace: WORKSPACE,
        path: key,
      });
      const tab: Tab = {
        path: key,
        content: j.content,
        dirty: false,
        view: null,
        kind: 'workspace',
        readonly: false,
        langCompartment: new Compartment(),
        lspCompartment: new Compartment(),
        lspAttached: false,
      };
      this.tabs = [...this.tabs, tab];
      this.activeTab = key;
      this._watchPath(key);
      await this._mountEditor(key);
      if (options.line !== undefined)
        this._revealLine(tab, options.line, !options.silent);
    } catch (error) {
      if (options.silent) throw error;
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
          // Disk and virtual tabs are read-only; only workspace files can
          // be edited.
          EditorState.readOnly.of(tab.readonly),
          EditorView.editable.of(!tab.readonly),
          breakpointGutter,
          execLineExtension,
          EditorView.updateListener.of((update) => {
            if (this._applyingRemote) return;
            // A breakpoint toggle, or a doc edit that shifts existing
            // breakpoints, means the debug adapter needs a fresh set.
            const breakpointsChanged =
              update.docChanged ||
              update.transactions.some((tr) =>
                tr.effects.some((e) => e.is(toggleBreakpoint))
              );
            if (breakpointsChanged) this._onBreakpointsChanged();
            if (!update.docChanged) return;
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
    // The language server only knows workspace-relative files, so it is
    // never attached to disk or virtual tabs.
    if (!tab.readonly) this._attachLsp(tab);
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
    // Disk and virtual tabs are read-only; only workspace files are saved.
    if (!tab || tab.readonly) return;
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
    // Only workspace files are watched on the server.
    if (tab && tab.kind === 'workspace') this._unwatchPath(path);
    this._refreshBreakpointView();
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
          timeout: 60_000,
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

  // Debugger --------------------------------------------------------------

  private _toggleDebugger() {
    this.debuggerOpen = !this.debuggerOpen;
    if (this.debuggerOpen) this.panel = null;
  }

  // Open (or re-open) the debug adapter connection.  The client owns a
  // single socket, so reconnecting means tearing the old one down and
  // building a fresh client.  Safe to call repeatedly: each connection is
  // tagged with a generation so a torn-down client cannot touch the UI.
  private _connectDap() {
    this._dap?.disconnect();
    this._dapInitialized = false;
    this._bpSentSources.clear();
    const generation = ++this._dapGeneration;
    const client = new DebuggerClient(DAP_URL, {
      onEvent: (event, body) => {
        if (this._dapGeneration !== generation) return;
        this._onDapEvent(event, body);
      },
      onStatus: (status) => {
        if (this._dapGeneration !== generation) return;
        this._onDapStatus(status);
      },
    });
    this._dap = client;
    client
      .initialize()
      .then(() => {
        if (this._dapGeneration !== generation) return;
        this._dapInitialized = true;
        this._syncBreakpoints();
      })
      .catch((error: Error) => {
        if (this._dapGeneration !== generation) return;
        this._appendConsole(
          'error',
          'Debugger failed to start: ' + error.message
        );
      });
  }

  private _onDapStatus(status: DapStatus) {
    this.dapStatus = status;
    // A dropped connection ends the session: forget what the adapter was
    // told so a reconnect sends a clean set of breakpoints, and drop the
    // now-stale call stack and stopped-line highlight.
    if (status === 'disconnected') {
      this._dapInitialized = false;
      this._bpSentSources.clear();
      this.debugThreads = [];
      this._clearExecLine();
    }
  }

  private _onDapEvent(event: string, body: DapEventBody) {
    switch (event) {
      case 'initialized': {
        // The adapter is ready for configuration; the breakpoints have
        // already been pushed, so just tell it we are done.
        this._dap?.send('configurationDone', {}).catch((error: Error) => {
          console.error('configurationDone failed', error);
        });
        break;
      }
      case 'stopped': {
        this._onDapStopped(body);
        break;
      }
      case 'continued':
      case 'terminated':
      case 'exited': {
        this.debugThreads = [];
        this._clearExecLine();
        break;
      }
      case 'output': {
        this._appendOutput(body);
        break;
      }
      // No default
    }
  }

  private async _onDapStopped(body: DapEventBody) {
    if (!this._dap) return;
    try {
      const all =
        (await this._dap.send<{ threads: DapThread[] }>('threads')).threads ??
        [];
      // With allThreadsStopped the whole program is paused; otherwise
      // only the reported thread is.
      const wanted = body.allThreadsStopped
        ? all
        : all.filter((t) => t.id === body.threadId);
      const stopped: StoppedThread[] = [];
      for (const thread of wanted) {
        const stack = await this._dap.send<{
          stackFrames: DapStackFrame[];
        }>('stackTrace', { threadId: thread.id });
        stopped.push({
          id: thread.id,
          name: thread.name,
          frames: stack.stackFrames ?? [],
        });
      }
      this.debugThreads = stopped;
      // Show where execution stopped: reveal and highlight the top frame
      // of the thread that actually hit, if we know which one that is.
      const hit = stopped.find((t) => t.id === body.threadId) ?? stopped[0];
      const top = hit?.frames[0];
      if (top) void this._showFrame(top);
    } catch (error) {
      this._appendConsole('error', (error as Error).message);
    }
  }

  private async _dapRun() {
    if (!this._dap || !this._dapInitialized) return;
    this._syncBreakpoints();
    try {
      if (this.debugThreads.length > 0) {
        const thread = this.debugThreads[0];
        this._clearExecLine();
        await this._dap.send('continue', { threadId: thread.id });
      } else {
        await this._dap.send('launch', {});
      }
    } catch (error) {
      this._appendConsole('error', (error as Error).message);
    }
  }

  private async _dapStep(kind: 'next' | 'stepIn' | 'stepOut') {
    if (!this._dap || !this._dapInitialized) return;
    const thread = this.debugThreads[0];
    if (!thread) return;
    try {
      await this._dap.send(kind, { threadId: thread.id });
    } catch (error) {
      this._appendConsole('error', (error as Error).message);
    }
  }

  // Pause the running program.  The proxy never lets a thread id through
  // that could stop the event loop, so no arguments are needed (and none
  // would be trusted).
  private async _dapPause() {
    if (!this._dap || !this._dapInitialized) return;
    try {
      await this._dap.send('pause', {});
    } catch (error) {
      this._appendConsole('error', (error as Error).message);
    }
  }

  private _onBreakpointsChanged() {
    this._refreshBreakpointView();
    // Debounce the network push so a burst of edits sends one request.
    if (this._bpTimer) globalThis.clearTimeout(this._bpTimer);
    this._bpTimer = globalThis.setTimeout(() => {
      this._bpTimer = null;
      this._syncBreakpoints();
    }, 200);
  }

  private _refreshBreakpointView() {
    const out: BreakpointView[] = [];
    // One entry per file and line, even if the same file is somehow open
    // in more than one tab.
    const seen = new Set<string>();
    for (const tab of this.tabs) {
      if (!tab.view) continue;
      for (const line of getBreakpointLines(tab.view.state)) {
        const key = tab.path + ':' + line;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({
          path: tab.path,
          line,
          sourceReference: tab.sourceReference,
        });
      }
    }
    this.breakpoints = out;
  }

  private _syncBreakpoints() {
    if (!this._dap || !this._dapInitialized) return;
    // Group breakpoints by source: the adapter wants one setBreakpoints
    // request per file, with each line listed once.
    const bySource = new Map<string, { source: DapSource; lines: Set<number> }>();
    for (const tab of this.tabs) {
      if (!tab.view) continue;
      const lines = getBreakpointLines(tab.view.state);
      if (lines.length === 0) continue;
      const source: DapSource =
        tab.sourceReference === undefined
          ? { path: this._absPathFor(tab) }
          : { name: tab.path, sourceReference: tab.sourceReference };
      const key = JSON.stringify(source);
      const entry = bySource.get(key) ?? { source, lines: new Set<number>() };
      for (const line of lines) entry.lines.add(line);
      bySource.set(key, entry);
    }
    // A source we sent before that no longer has breakpoints has to be
    // told to clear them, or the adapter keeps pausing there.
    for (const [key, source] of this._bpSentSources) {
      if (!bySource.has(key)) {
        this._dap
          .send('setBreakpoints', { source, breakpoints: [] })
          .catch((error: Error) => {
            console.error('setBreakpoints failed', error);
          });
      }
    }
    this._bpSentSources = new Map(
      [...bySource].map(([key, entry]) => [key, entry.source])
    );
    for (const { source, lines } of bySource.values()) {
      this._dap
        .send('setBreakpoints', {
          source,
          breakpoints: [...lines]
            .sort((a, b) => a - b)
            .map((line) => ({ line })),
        })
        .catch((error: Error) => {
          console.error('setBreakpoints failed', error);
        });
    }
  }

  private _absPathFor(tab: Tab): string {
    // Workspace tabs are stored relative to the workspace root; the
    // adapter wants a path it can resolve itself.
    if (tab.kind === 'workspace') {
      return this._workspacePath.replace(/\/+$/, '') + '/' + tab.path;
    }
    return tab.path;
  }

  private async _jumpToFrame(frame: DapStackFrame) {
    const source = frame.source;
    // Only a positive sourceReference marks a virtual (decompiled) source;
    // ordinary on-disk files report 0, which is a real path we can open.
    if (source?.sourceReference) {
      await this._openVirtualSource(source, frame.line);
    } else if (source?.path) {
      await this._openDiskFile(source.path, frame.line);
    }
  }

  // Reveal the top frame of a stop automatically.  Unlike a frame click
  // this must never pop an alert or steal focus, so failures are reported
  // in the console and the editor keeps whatever the user was doing.
  private async _showFrame(frame: DapStackFrame) {
    const source = frame.source;
    try {
      if (source?.sourceReference) {
        await this._openVirtualSource(source, frame.line, { silent: true });
      } else if (source?.path) {
        await this._openDiskFile(source.path, frame.line, { silent: true });
      }
    } catch (error) {
      this._appendConsole('error', (error as Error).message);
    }
  }

  // Clear the stopped-line highlight from every open editor.
  private _clearExecLine() {
    for (const tab of this.tabs) {
      tab.view?.dispatch({ effects: setExecLine.of(null) });
    }
  }

  private async _openDiskFile(
    path: string,
    line: number,
    options: { silent?: boolean } = {}
  ) {
    const key = this._canonicalPath(path);
    // A path that resolves inside the workspace is an editable workspace
    // file, so reuse its tab instead of opening a second, read-only one.
    if (key && !key.startsWith('/')) {
      await this._openFile(key, { line, silent: options.silent });
      return;
    }
    const existing = this.tabs.find((t) => t.path === key);
    if (existing) {
      this.activeTab = key;
      this._revealLine(existing, line, !options.silent);
      return;
    }
    try {
      const j = await this._api('GET', 'read_abs', { path: key });
      const tab: Tab = {
        path: key,
        content: j.content,
        dirty: false,
        view: null,
        kind: 'disk',
        readonly: true,
        langCompartment: new Compartment(),
        lspCompartment: new Compartment(),
        lspAttached: false,
      };
      this.tabs = [...this.tabs, tab];
      this.activeTab = key;
      await this._mountEditor(key);
      this._revealLine(tab, line, !options.silent);
    } catch (error) {
      if (options.silent) throw error;
      alert('Could not open source file: ' + (error as Error).message);
    }
  }

  private async _openVirtualSource(
    source: DapSource,
    line: number,
    options: { silent?: boolean } = {}
  ) {
    const ref = source.sourceReference;
    if (ref === undefined || !this._dap) return;
    const path = source.name || 'source-' + ref;
    const existing = this.tabs.find((t) => t.path === path);
    if (existing) {
      this.activeTab = path;
      this._revealLine(existing, line, !options.silent);
      return;
    }
    try {
      const body = await this._dap.send<{ content: string }>('source', {
        sourceReference: ref,
      });
      const tab: Tab = {
        path,
        content: body.content ?? '',
        dirty: false,
        view: null,
        kind: 'virtual',
        readonly: true,
        sourceReference: ref,
        langCompartment: new Compartment(),
        lspCompartment: new Compartment(),
        lspAttached: false,
      };
      this.tabs = [...this.tabs, tab];
      this.activeTab = path;
      await this._mountEditor(path);
      this._revealLine(tab, line, !options.silent);
    } catch (error) {
      if (options.silent) throw error;
      alert('Could not load source: ' + (error as Error).message);
    }
  }

  private _revealLine(tab: Tab, line: number, focus = true) {
    requestAnimationFrame(() => {
      const view = tab.view;
      if (!view) return;
      const number = Math.min(Math.max(line, 1), view.state.doc.lines);
      const info = view.state.doc.line(number);
      view.dispatch({
        selection: { anchor: info.from },
        effects: [
          EditorView.scrollIntoView(info.from, { y: 'center' }),
          setExecLine.of(number),
        ],
      });
      if (focus) view.focus();
    });
  }

  private _appendConsole(kind: ConsoleLine['kind'], text: string) {
    if (!text) return;
    this.consoleLines = [...this.consoleLines, { kind, text }];
    this.updateComplete.then(() => this._scrollConsole());
  }

  // Adapter output arrives in arbitrary chunks that can split a line in
  // the middle; hold the trailing fragment until its newline arrives so
  // the console shows one entry per line instead of a blank line per
  // chunk.  stderr is shown with the error styling.
  private _appendOutput(body: DapEventBody) {
    const text = this._consolePartial + (body.output ?? '');
    const parts = text.split('\n');
    this._consolePartial = parts.pop() ?? '';
    const kind: ConsoleLine['kind'] =
      body.category === 'stderr' ? 'error' : 'output';
    for (const part of parts) {
      if (part.trim()) this._appendConsole(kind, part);
    }
  }

  private _scrollConsole() {
    const el = this.renderRoot.querySelector(
      '[data-testid="dap-console-output"]'
    );
    if (el) el.scrollTop = el.scrollHeight;
  }

  private _onConsoleKey(e: KeyboardEvent) {
    const input = e.target as HTMLInputElement;
    switch (e.key) {
    case 'Enter': {
      e.preventDefault();
      this._consoleSubmit(input);
    
    break;
    }
    case 'ArrowUp': {
      e.preventDefault();
      this._consoleRecall(input, -1);
    
    break;
    }
    case 'ArrowDown': {
      e.preventDefault();
      this._consoleRecall(input, 1);
    
    break;
    }
    // No default
    }
  }

  private _consoleRecall(input: HTMLInputElement, delta: -1 | 1) {
    const count = this._consoleHistory.length;
    if (count === 0) return;
    // Stepping away from the newest entry keeps whatever was typed.
    if (this._consoleIndex >= count) this._consoleDraft = input.value;
    let index = this._consoleIndex + delta;
    index = Math.min(Math.max(index, 0), count);
    this._consoleIndex = index;
    input.value =
      index >= count ? this._consoleDraft : this._consoleHistory[index];
    input.setSelectionRange(input.value.length, input.value.length);
  }

  private async _consoleSubmit(input: HTMLInputElement) {
    const text = input.value.trim();
    if (!text) return;
    this._consoleHistory.push(text);
    this._consoleIndex = this._consoleHistory.length;
    this._consoleDraft = '';
    input.value = '';
    this._appendConsole('input', text);
    if (!this._dap || !this._dapInitialized) {
      this._appendConsole('error', 'Not connected to a debug adapter');
      return;
    }
    try {
      const body = await this._dap.send<{ result: string }>('evaluate', {
        expression: text,
        context: 'repl',
        frameId: this.debugThreads[0]?.frames[0]?.id,
      });
      this._appendConsole('output', body.result ?? '');
    } catch (error) {
      this._appendConsole('error', (error as Error).message);
    }
  }

  private _toggleFolder(path: string) {
    // Reassign so Lit sees the change; Set mutations are not observed.
    const next = new Set(this.collapsed);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    this.collapsed = next;
  }

  private _renderTree(nodes: FileNode[], depth = 0, parentPath = ''): any {
    return nodes.map((n) => {
      const fullPath = parentPath ? parentPath + '/' + n.name : n.name;
      const isDir = n.type === 'dir';
      const collapsed = isDir && this.collapsed.has(fullPath);
      return html`
        <div
          class="tree-item"
          style="padding-left: ${0.5 + depth * 0.75}rem"
          @click="${() => {
            if (isDir) this._toggleFolder(fullPath);
            else this._openFile(fullPath);
          }}"
          @contextmenu="${(e: Event) =>
            this._openContextMenu(e as MouseEvent, fullPath, isDir)}"
        >
          <span class="tree-chevron"
            >${isDir ? (collapsed ? '▸' : '▾') : ''}</span
          >${isDir ? '📁 ' : '📄 '}${n.name}
        </div>
        ${isDir && !collapsed && n.children
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

  private _renderDebugger() {
    return html`
      <div class="panel paper h-pane debugger" data-testid="debugger">
        <div class="panel-head">
          <span class="panel-title">Debugger</span>
          <span
            class="badge ${this.dapStatus === 'connected' ? 'success' : ''}"
            data-testid="dap-badge"
          >
            ${this.dapStatus}
          </span>
          <button
            class="panel-close"
            data-testid="debugger-close"
            @click="${() => (this.debuggerOpen = false)}"
          >
            ✕
          </button>
        </div>
        <div class="debug-controls">
          ${this.dapStatus === 'disconnected'
            ? html`
                <button data-testid="dap-reconnect" title="Reconnect"
                  @click="${this._connectDap}">
                  <span class="mdi mdi-refresh"></span>
                </button>
              `
            : nothing}
          <button data-testid="dap-run" title="Run / Continue"
            @click="${this._dapRun}">
            <span class="mdi mdi-play"></span>
          </button>
          <button data-testid="dap-pause" title="Pause"
            @click="${this._dapPause}">
            <span class="mdi mdi-pause"></span>
          </button>
          <button data-testid="dap-step-over" title="Step over"
            @click="${() => this._dapStep('next')}">
            <span class="mdi mdi-debug-step-over"></span>
          </button>
          <button data-testid="dap-step-in" title="Step in"
            @click="${() => this._dapStep('stepIn')}">
            <span class="mdi mdi-debug-step-into"></span>
          </button>
          <button data-testid="dap-step-out" title="Step out"
            @click="${() => this._dapStep('stepOut')}">
            <span class="mdi mdi-debug-step-out"></span>
          </button>
        </div>
        <div class="debug-section">
          <div class="debug-section-title">Breakpoints</div>
          ${this.breakpoints.length === 0
            ? html`<div class="debug-empty">No breakpoints</div>`
            : this.breakpoints.map(
                (b) => html`
                  <div class="debug-breakpoint" data-testid="dap-breakpoint">
                    ${b.path}:${b.line}
                  </div>
                `
              )}
        </div>
        <div class="debug-section debug-stacks">
          <div class="debug-section-title">Call stack</div>
          ${this.debugThreads.length === 0
            ? html`<div class="debug-empty">Not stopped</div>`
            : this.debugThreads.map(
                (thread) => html`
                  <div class="debug-thread">${thread.name}</div>
                  ${thread.frames.map(
                    (frame) => html`
                      <div
                        class="debug-frame"
                        data-testid="dap-frame"
                        @click="${() => this._jumpToFrame(frame)}"
                      >
                        <span>${frame.name}</span>
                        <span class="debug-frame-loc">
                          ${frame.source?.name || frame.source?.path || ''}:
                          ${frame.line}
                        </span>
                      </div>
                    `
                  )}
                `
              )}
        </div>
        <div class="debug-console" data-testid="dap-console">
          <div
            class="debug-console-output"
            data-testid="dap-console-output"
          >
            ${this.consoleLines.map(
              (line) => html`
                <div class="console-line console-${line.kind}">${line.text}</div>
              `
            )}
          </div>
          <input
            class="debug-console-input"
            data-testid="dap-console-input"
            placeholder="Console"
            @keydown="${this._onConsoleKey}"
          >
        </div>
      </div>
    `;
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
          ${DAP_URL
            ? html`
                <button
                  @click="${this._toggleDebugger}"
                  data-testid="debugger-toggle"
                  title="Debugger"
                >
                  <span class="mdi mdi-bug"></span>Debug
                </button>
              `
            : nothing}
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
                class="sidebar h-pane paper"
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
                class="panel paper h-pane"
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
        ${this.debuggerOpen ? this._renderDebugger() : nothing}
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
