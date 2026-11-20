// SPDX-License-Identifier: GPL-3.0-or-later
// Breakpoint gutter for the text editor.
//
// Adds a CodeMirror gutter whose dots mark breakpoints.  Clicking the
// gutter toggles a breakpoint on that line.  Breakpoints live in a
// state field as a range set so they move with the document as it is
// edited; ``getBreakpointLines`` reads the current set back out for the
// debugger.

import {
  EditorState,
  RangeSet,
  StateEffect,
  StateField,
} from '@codemirror/state';
import { GutterMarker, gutter } from '@codemirror/view';

class BreakpointMarker extends GutterMarker {
  override toDOM() {
    const dot = document.createElement('span');
    dot.className = 'cm-breakpoint-dot';
    dot.textContent = '●';
    return dot;
  }
}

const breakpointMarker = new BreakpointMarker();

/** Toggle a breakpoint at a document position. */
export const toggleBreakpoint = StateEffect.define<number>({
  // Keep the position pinned to the same text across edits.
  map: (pos, mapping) => mapping.mapPos(pos),
});

const breakpointField = StateField.define<RangeSet<GutterMarker>>({
  create: () => RangeSet.empty,
  update(set, transaction) {
    set = set.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (effect.is(toggleBreakpoint)) {
        const pos = effect.value;
        let present = false;
        set.between(pos, pos, () => {
          present = true;
        });
        set = present
          ? set.update({ filter: (from) => from !== pos })
          : set.update({ add: [breakpointMarker.range(pos)] });
      }
    }
    return set;
  },
});

/** The gutter extension, to be added to an editor's extensions. */
export const breakpointGutter = [
  breakpointField,
  gutter({
    class: 'cm-breakpoint-gutter',
    markers: (view) => view.state.field(breakpointField),
    initialSpacer: () => breakpointMarker,
    domEventHandlers: {
      mousedown(view, line) {
        view.dispatch({ effects: toggleBreakpoint.of(line.from) });
        return true;
      },
    },
  }),
];

/** The 1-based line numbers that currently carry a breakpoint. */
export function getBreakpointLines(state: EditorState): number[] {
  const set = state.field(breakpointField, false);
  if (!set) return [];
  const lines: number[] = [];
  const iter = set.iter();
  while (iter.value) {
    lines.push(state.doc.lineAt(iter.from).number);
    iter.next();
  }
  return lines.sort((a, b) => a - b);
}
