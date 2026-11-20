// SPDX-License-Identifier: GPL-3.0-or-later
// Current-execution-line decoration for the text editor.
//
// When the debugger stops, the line it stopped on is highlighted with a
// line decoration.  The position is held in a state field so it moves
// with the document if it is edited, and ``setExecLine`` (with a null
// value) clears it when execution resumes.

import { StateEffect, StateField } from '@codemirror/state';
import { Decoration, DecorationSet, EditorView } from '@codemirror/view';

/** Move (or clear, with a null value) the highlighted execution line. */
export const setExecLine = StateEffect.define<number | null>();

const execLineDecoration = Decoration.line({ class: 'cm-exec-line' });

const execLineField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(set, transaction) {
    set = set.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (effect.is(setExecLine)) {
        if (effect.value === null) return Decoration.none;
        const line = transaction.state.doc.line(
          Math.min(Math.max(effect.value, 1), transaction.state.doc.lines)
        );
        return Decoration.set([execLineDecoration.range(line.from)]);
      }
    }
    return set;
  },
  provide: (field) => EditorView.decorations.from(field),
});

/** The decoration extension, to be added to an editor's extensions. */
export const execLineExtension = [execLineField];
