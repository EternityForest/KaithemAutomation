/* eslint-disable unicorn/no-lonely-if */
// SPDX-License-Identifier: GPL-3.0-or-later

/**
 * YJS Provider for Kaithem
 * Provides access to YJS documents through Kaithem's widget system
 */

import * as Y from 'yjs';

import { kaithemapi } from './widget.mjs';
import picodash from '/static/js/thirdparty/picodash/picodash-base.esm.js';

const getRandom52BitInt = () => {
  // Create an array to hold 2 32-bit unsigned integers (to cover 52 bits)
  const array = new Uint32Array(2);
  globalThis.crypto.getRandomValues(array);

  // Combine the two 32-bit chunks using BigInt for precision
  const combined = (BigInt(array[0]) << 32n) + BigInt(array[1]);

  return Number(combined & 0xf_ff_ff_ff_ff_ff_ffn);
};

/**
 * Cache of YJS documents by name
 */
const documentCache = new Map<string, Y.Doc>();

/*Persistent name to what the server says it its session ID for that doc*/
const serverSessionIdMap = new Map<string, string>();

/**
 * Get a YJS document by name. Creates a new one or returns existing from cache.
 * Will fetch initial state after WebSocket subscription is established.
 *
 * @param documentName - The name of the document to get
 * @returns The YJS document
 */
export function getDocument(documentName: string): Y.Doc {
  if (documentCache.has(documentName)) {
    return documentCache.get(documentName)!;
  }

  const document_ = new Y.Doc();
  documentCache.set(documentName, document_);

  // Subscribe to the syncdb widget to receive updates
  _subscribeToDocument(documentName, document_);
  return document_;
}

/**
 * Fetch initial state from server after WebSocket connection is established
 */
async function _fetchInitialState(
  documentName: string,
  document_: Y.Doc
): Promise<void> {
  try {
    // s
    const server_vector = await fetch(
      `/api/syncdb/${encodeURIComponent(documentName)}/state_vector`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/octet-stream',
        },
      }
    );

    const updates_for_server = Y.encodeStateAsUpdate(
      document_,
      new Uint8Array(await server_vector.arrayBuffer())
    );

    kaithemapi.sendValue(`syncdb:${documentName}`, updates_for_server);

    // Get our current state vector
    const stateVector = Y.encodeStateVector(document_);

    const response = await fetch(
      `/api/syncdb/${encodeURIComponent(documentName)}/sync`,
      {
        method: 'POST',
        body: stateVector,
        headers: {
          'Content-Type': 'application/octet-stream',
        },
      }
    );

    if (!response.ok) {
      console.error('Failed to fetch initial state:', response.status);
      return;
    }

    const update = await response.arrayBuffer();
    if (update.byteLength > 0) {
      Y.applyUpdate(document_, new Uint8Array(update));
      console.log('Synced initial state for:', documentName);
    }
  } catch (error) {
    console.error('Error fetching initial state:', error);
    picodash.snackbar.createSnackbar(
      'Failed to fetch CRDT state. Refresh page or look for a newer version of this document.',
      {
        timeout: 60_000,
        accent: 'error',
      }
    );
  }
}

/**
 * Subscribe to a document's updates from the server
 */
function _subscribeToDocument(documentName: string, document_: Y.Doc): void {
  const widgetId = `syncdb:${documentName}`;

  // This is needed because when the server is down, it
  // loses all information on assigned IDs
  kaithemapi.subscribe('__SERVER_DISCONNECTED__', () => {
    document_.clientID = getRandom52BitInt();
    console.log(
      'Disconnected from server, resetting client ID to:',
      document_.clientID
    );
  });

  kaithemapi.subscribe(widgetId, (value: unknown) => {
    if (!value) return;

    try {
      let update: Uint8Array | null = null;

      if (value instanceof Uint8Array) {
        update = value;
      } else if (typeof value === 'object' && value !== null) {
        if ('crdt_id' in value) {
          console.log(
            'Received update for document:',
            documentName,
            'with client ID:',
            value.crdt_id
          );
          document_.clientID = value.crdt_id as number;
        }

        // The server always sends this when we connect.
        // If the server changes the session ID, we need to reload everything.
        
        if ('session_id' in value) {
          const oldSessionId = serverSessionIdMap.get(documentName);

          if (oldSessionId === undefined) {
              serverSessionIdMap.set(documentName, value.session_id as string);
              _fetchInitialState(documentName, document_);
          } else if (oldSessionId !== value.session_id) {
            console.log('Session ID changed for document, reloading.', documentName);
            globalThis.location.reload();
          }
        }
      }

      if (update) {
        Y.applyUpdate(document_, update);
      }
    } catch (error) {
      console.error('Failed to apply YJS update:', error);
    }
  });
}

export default {
  getDocument,
};
