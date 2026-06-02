// SPDX-License-Identifier: GPL-3.0-or-later

/**
 * YJS Provider for Kaithem
 * Provides access to YJS documents through Kaithem's widget system
 */

import * as Y from 'yjs';

import { kaithemapi } from './widget.mjs';

/**
 * Cache of YJS documents by name
 */
const documentCache = new Map<string, Y.Doc>();

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
    subscribeToDocument(documentName, document_);

    // Wait for WebSocket subscription to establish, then fetch initial state
    setTimeout(() => {
        fetchInitialState(documentName, document_);
    }, 60);

    return document_;
}

/**
 * Fetch initial state from server after WebSocket connection is established
 */
async function fetchInitialState(documentName: string, document_: Y.Doc): Promise<void> {
    try {
        // Get our current state vector
        const stateVector = Y.encodeStateVector(document_);

        const response = await fetch(`/api/syncdb/${encodeURIComponent(documentName)}/sync`, {
            method: 'POST',
            body: stateVector,
            headers: {
                'Content-Type': 'application/octet-stream',
            },
        });

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
    }
}

/**
 * Subscribe to a document's updates from the server
 */
function subscribeToDocument(documentName: string, document_: Y.Doc): void {
    const widgetId = `syncdb:${documentName}`;

    kaithemapi.subscribe(widgetId, (value: unknown) => {
        if (!value) return;

        try {
            let update: Uint8Array | null = null;

            if (value instanceof Uint8Array) {
                update = value;
            }else if (typeof value === 'object' && value !== null) {
                const val = value as Record<string, unknown>;
                if (val.data && val.data instanceof Uint8Array) {
                    update = val.data as Uint8Array;
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
 * Broadcast a YJS update to the server
 *
 * @param documentName - The document name
 * @param update - The YJS update to broadcast
 */
export function broadcastUpdate(documentName: string, update: Uint8Array): void {

    const widgetId = `syncdb:${documentName}`;

    kaithemapi.sendValue(widgetId, update);
}

/**
 * Observe changes to a document
 *
 * @param documentName - The document name
 * @param observer - Callback receiving (transaction, context)
 * @returns Unsubscribe function
 */
export function observeDocument(
    documentName: string,
    observer: (update: Uint8Array, origin: unknown) => void
): () => void {
    const document_ = getDocument(documentName);

    document_.on('update', observer);

    return () => {
        document_.off('update', observer);
    };
}

/**
 * Get the current state vector for a document
 *
 * @param documentName - The document name
 * @returns The state vector
 */
export function getStateVector(documentName: string): Uint8Array {
    const document_ = getDocument(documentName);
    return Y.encodeStateVector(document_);
}

/**
 * Get the full document state
 *
 * @param documentName - The document name
 * @returns The encoded document state
 */
export function getDocumentState(documentName: string): Uint8Array {
    const document_ = getDocument(documentName);
    return Y.encodeStateAsUpdate(document_);
}

export default {
    getDocument,
    broadcastUpdate,
    observeDocument,
    getStateVector,
    getDocumentState,
};