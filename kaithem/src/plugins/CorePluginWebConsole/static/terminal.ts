// Interactive system web console.
//
// Renders an xterm terminal and bridges it to the backend PTY over a
// WebSocket.  xterm and its addons come from npm and are bundled by Vite
// rather than vendored as static files in the repo.

import { createTerminal } from '../../../js/xterm-terminal.ts';

const { term, fit } = createTerminal({
  term: { fontSize: 14 },
  images: true,
});

term.open(document.querySelector('#terminal') as HTMLElement);
fit.fit();

const protocol = globalThis.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsPath =
  new URLSearchParams(globalThis.location.search).get('ws') ??
  '/webconsole/terminal';
const wsUrl = `${protocol}//${globalThis.location.host}${wsPath}`;

const errorBanner = document.querySelector('#error-banner') as HTMLElement;
const MAX_RECONNECT_ATTEMPTS = 5;
let reconnectAttempts = 0;

function showError(message: string): void {
  errorBanner.textContent = message;
  errorBanner.classList.add('show');
  globalThis.setTimeout(() => {
    errorBanner.classList.remove('show');
  }, 5000);
}

let ws: WebSocket | null = null;

function connect(): void {
  ws = new WebSocket(wsUrl);

  ws.addEventListener('open', () => {
    reconnectAttempts = 0;
    // Send initial terminal size.
    term.focus();
    ws?.send(`resize:${term.cols}:${term.rows}`);
  });

  ws.addEventListener('message', (event) => {
    if (event.data instanceof Blob) {
      void event.data.arrayBuffer().then((buffer) => {
        term.write(new Uint8Array(buffer));
      });
    } else {
      term.write(event.data as string);
    }
  });

  ws.addEventListener('error', () => {
    showError('WebSocket connection error');
  });

  ws.addEventListener('close', () => {
    ws = null;
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      showError(
        `Connection lost. Reconnecting... (Attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`
      );
      globalThis.setTimeout(connect, 2000);
    } else {
      showError('Connection lost. Please refresh the page.');
      term.write('\r\n\u001B[1;31mConnection to server lost.\u001B[0m\r\n');
    }
  });
}

// Forward terminal input to the backend.
term.onData((data) => {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(data);
  }
});

// Forward resizes to the backend PTY.
term.onResize(({ cols, rows }) => {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(`resize:${cols}:${rows}`);
  }
});

globalThis.addEventListener('resize', () => {
  fit.fit();
});

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    fit.fit();
  }
});

globalThis.addEventListener('beforeunload', () => {
  ws?.close();
});

connect();
term.focus();
