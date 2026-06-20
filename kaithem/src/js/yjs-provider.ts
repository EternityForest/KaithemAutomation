/* eslint-disable unicorn/no-lonely-if */
// SPDX-License-Identifier: GPL-3.0-or-later

/**
 * YJS Provider for Kaithem
 * Provides access to YJS documents through Kaithem's widget system
 */

import * as Y from 'yjs';
import { Awareness } from 'y-protocols/awareness';

import { kaithemapi } from './widget.mjs';
import picodash from '/static/js/thirdparty/picodash/picodash-base.esm.js';

// Message type codes (4-byte big-endian)
const MSG_UPDATE = new Uint8Array([0x00, 0x00, 0x00, 0x01]);
const MSG_AWARENESS = new Uint8Array([0x00, 0x00, 0x00, 0x02]);

const getRandom52BitInt = () => {
  // Create an array to hold 2 32-bit unsigned integers (to cover 52 bits)
  const array = new Uint32Array(2);
  globalThis.crypto.getRandomValues(array);

  // Combine the two 32-bit chunks using BigInt for precision
  const combined = (BigInt(array[0]) << 32n) + BigInt(array[1]);

  return Number(combined & 0xf_ff_ff_ff_ff_ff_ffn);
};

/**
 * Compare two Uint8Arrays for equality
 */
const _bytesEqual = (a: Uint8Array, b: Uint8Array): boolean => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
};

/**
 * Combine type code with payload
 */
const _makeTypedMessage = (type: Uint8Array, payload: Uint8Array): Uint8Array => {
  const result = new Uint8Array(type.length + payload.length);
  result.set(type, 0);
  result.set(payload, type.length);
  return result;
};

/**
 * Cache of YJS documents by name
 */
const documentCache = new Map<string, Y.Doc>();

/*Persistent name to what the server says it its session ID for that doc*/
const serverSessionIdMap = new Map<string, string>();

/**
 * Cache of YJS Awareness instances by document name
 */
const awarenessMap = new Map<string, Awareness>();

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

    // Send update with type code prefix
    kaithemapi.sendValue(
      `syncdb:${documentName}`,
      _makeTypedMessage(MSG_UPDATE, updates_for_server)
    );

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
      // Handle typed messages (with 4-byte type code prefix)
      if (value instanceof Uint8Array && value.byteLength >= 4) {
        const msgType = value.slice(0, 4);
        const payload = value.slice(4);

        // Check message type
        if (_bytesEqual(msgType, MSG_UPDATE)) {
          // Regular YJS update
          Y.applyUpdate(document_, payload);
        } else if (_bytesEqual(msgType, MSG_AWARENESS)) {
          // Awareness update - apply to awareness if available
          const awareness = awarenessMap.get(documentName);
          if (awareness) {
            Awareness.applyUpdate(awareness, payload);
          }
        }
        return;
      }

      // Handle legacy messages without type code
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

/**
 * Get or create a YJS Awareness instance for a document.
 * Awareness is used for presence, cursor positions, and other
 * ephemeral user state.
 *
 * @param documentName - The name of the document
 * @returns The YJS Awareness instance
 */
export function getAwareness(documentName: string): Awareness {
  if (awarenessMap.has(documentName)) {
    return awarenessMap.get(documentName)!;
  }

  // Get or create the document
  const document_ = getDocument(documentName);

  // Create awareness instance
  const awareness = new Awareness(document_);

  // Listen for local awareness changes and send to server
  awareness.on('update', ({ added, updated, removed }: { added: number[]; updated: number[]; removed: number[] }) => {
    const changedClients = added.concat(updated).concat(removed);
    const update = Awareness.encodeAwarenessUpdate(awareness, changedClients);

    if (update.byteLength > 0) {
      kaithemapi.sendValue(
        `syncdb:${documentName}`,
        _makeTypedMessage(MSG_AWARENESS, update)
      );
    }
  });

  awarenessMap.set(documentName, awareness);
  return awareness;
}

export default {
  getDocument,
  getAwareness,
};
