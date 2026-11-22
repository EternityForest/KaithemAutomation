// Shared xterm.js setup for Kaithem consoles.
//
// Both the system web console and the container app script consoles build
// their terminals through this helper, so they share one colour theme and
// addon set.  xterm is imported from npm and bundled by Vite rather than
// vendored as a static file in the repo.

import { Terminal } from '@xterm/xterm';
import type { ITerminalOptions } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { ImageAddon } from '@xterm/addon-image';
import '@xterm/xterm/css/xterm.css';

/** VS Code-like dark theme shared by every Kaithem terminal. */
export const KAITHEM_TERMINAL_THEME: ITerminalOptions['theme'] = {
  background: '#1e1e1e',
  foreground: '#d4d4d4',
  cursor: '#ffffff',
  cursorAccent: '#000000',
  selectionBackground: '#264f78',
  black: '#000000',
  red: '#cd3131',
  green: '#0dbc79',
  yellow: '#e5e510',
  blue: '#2472c8',
  magenta: '#bc3fbc',
  cyan: '#11a8cd',
  white: '#e5e5e5',
  brightBlack: '#666666',
  brightRed: '#f14c4c',
  brightGreen: '#23d18b',
  brightYellow: '#f5f543',
  brightBlue: '#3b8eea',
  brightMagenta: '#d670d6',
  brightCyan: '#29b8db',
  brightWhite: '#ffffff',
};

const DEFAULT_FONT_FAMILY =
  '"Cascadia Code", "Fira Code", "Courier New", monospace';

export interface TerminalBundle {
  term: Terminal;
  fit: FitAddon;
  image: ImageAddon | null;
}

export interface CreateTerminalOptions {
  /** xterm options, merged over the shared defaults. */
  term?: ITerminalOptions;
  /** Load the image addon (sixel / iTerm IIP).  Off by default. */
  images?: boolean;
}

/**
 * Create an xterm terminal with the shared theme and the fit and web-links
 * addons already loaded.  The caller opens it into the DOM and, for an
 * interactive shell, wires up input and resize handling.
 */
export function createTerminal(
  options: CreateTerminalOptions = {}
): TerminalBundle {
  const term = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: DEFAULT_FONT_FAMILY,
    theme: KAITHEM_TERMINAL_THEME,
    allowProposedApi: true,
    ...options.term,
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  term.loadAddon(new WebLinksAddon());
  let image: ImageAddon | null = null;
  if (options.images) {
    image = new ImageAddon({
      enableSizeReports: true,
      pixelLimit: 16_777_216,
      sixelSupport: true,
      sixelScrolling: true,
      sixelPaletteLimit: 256,
      sixelSizeLimit: 25_000_000,
      storageLimit: 128,
      showPlaceholder: true,
      iipSupport: true,
      iipSizeLimit: 20_000_000,
    });
    term.loadAddon(image);
  }
  return { term, fit, image };
}
