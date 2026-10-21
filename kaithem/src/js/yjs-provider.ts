// SPDX-License-Identifier: GPL-3.0-or-later

/**
 * YJS Provider for Kaithem
 *
 * Provides access to YJS documents through Kaithem's widget system.
 *
 * Documents are synchronised over the widget websocket using a small
 * typed framing protocol. Every message starts with a 4 byte big endian
 * type code:
 *
 *   MSG_UPDATE    (0x01) A regular YJS document update.
 *   MSG_AWARENESS (0x02) A YJS awareness update.
 *   MSG_VERSION   (0x03) A database version handshake.
 *
 * The version message is always the very first message sent on a
 * connection, and is re-sent after a successful migration. Traffic from
 * a remote that is not on the same version is ignored. When a remote
 * reports a higher version we migrate to it.
 *
 * Versions are millisecond timestamps stored as unsigned 64 bit
 * integers, or 0 if no migration has ever happened. They may exceed the
 * safe range of a JavaScript number, so they are held as bigints.
 */

import * as Y from 'yjs';
import { Awareness } from 'y-protocols/awareness';

import { kaithemapi } from './widget.mjs';
import picodash from '/static/js/thirdparty/picodash/picodash-base.esm.js';

// Message type codes (4 byte big endian)
const MSG_UPDATE = new Uint8Array([0x00, 0x00, 0x00, 0x01]);
const MSG_AWARENESS = new Uint8Array([0x00, 0x00, 0x00, 0x02]);
const MSG_VERSION = new Uint8Array([0x00, 0x00, 0x00, 0x03]);

// Versions are encoded as unsigned 64 bit integers.
const VERSION_BYTE_LENGTH = 8;

// Anything an hour or more ahead of the local clock is an error.
const MAX_VERSION_FUTURE_MS = 60n * 60n * 1000n;

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
  for (const [i, element] of a.entries()) {
    if (element !== b[i]) return false;
  }
  return true;
};

/**
 * Combine a type code with a payload
 */
const _makeTypedMessage = (
  type: Uint8Array,
  payload: Uint8Array
): Uint8Array => {
  const result = new Uint8Array(type.length + payload.length);
  result.set(type, 0);
  result.set(payload, type.length);
  return result;
};

/**
 * Encode a version as 8 big endian bytes.
 *
 * Versions are millisecond timestamps that may exceed 32 bits, so they
 * are always encoded as unsigned 64 bit integers.
 */
function encodeVersion(version: bigint): Uint8Array {
  if (version < 0n) {
    throw new Error('Version cannot be negative');
  }
  const bytes = new Uint8Array(VERSION_BYTE_LENGTH);
  new DataView(bytes.buffer).setBigUint64(0, version, false);
  return bytes;
}

/**
 * Decode an 8 byte big endian version number.
 */
function decodeVersion(payload: Uint8Array): bigint {
  if (payload.byteLength !== VERSION_BYTE_LENGTH) {
    throw new Error(
      `Version payload must be ${VERSION_BYTE_LENGTH} bytes`
    );
  }
  return new DataView(
    payload.buffer,
    payload.byteOffset,
    payload.byteLength
  ).getBigUint64(0, false);
}

/**
 * Check that a version is not implausibly far in the future.
 *
 * Versions are millisecond timestamps. Anything one hour or more ahead
 * of the local clock is treated as an error.
 */
function versionIsSane(version: bigint): boolean {
  return version < BigInt(Date.now()) + MAX_VERSION_FUTURE_MS;
}

/**
 * Convert a JSON-like value into mergeable YJS shared types.
 *
 * Maps become Y.Map and arrays become Y.Array so that they can merge
 * across documents. Other values are returned unchanged.
 */
function toSharedValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    const array = new Y.Array<unknown>();
    array.insert(0, value.map((item) => toSharedValue(item)));
    return array;
  }
  if (value !== null && typeof value === 'object') {
    const map = new Y.Map<unknown>();
    for (const [key, item] of Object.entries(value)) {
      map.set(key, toSharedValue(item));
    }
    return map;
  }
  return value;
}

/**
 * Populate a document from a JSON-like map of top level keys.
 *
 * Top level YJS values must be shared types (maps or arrays), so scalar
 * values are rejected rather than silently stored in an unmergeable
 * way.
 */
function seedDocument(
  doc: Y.Doc,
  snapshot: Record<string, unknown>
): void {
  if (
    snapshot === null ||
    typeof snapshot !== 'object' ||
    Array.isArray(snapshot)
  ) {
    throw new TypeError('Migration snapshot must be a map object');
  }

  for (const [key, value] of Object.entries(snapshot)) {
    if (Array.isArray(value)) {
      doc.getArray<unknown>(key).insert(
        0,
        value.map((item) => toSharedValue(item))
      );
    } else if (value !== null && typeof value === 'object') {
      const target = doc.getMap<unknown>(key);
      for (const [itemKey, item] of Object.entries(value)) {
        target.set(itemKey, toSharedValue(item));
      }
    } else {
      throw new TypeError(
        `Top level migration value for ${key} must be a map or list`
      );
    }
  }
}

/**
 * Callback invoked when a database is migrated.
 *
 * It receives the old document, the old version, a fresh document it
 * should populate with any application level data worth keeping, and
 * the new version.
 */
export type OnMigration = (
  oldDB: Y.Doc,
  oldVersion: bigint,
  newDb: Y.Doc,
  newVersion: bigint
) => void;

export interface SyncDatabaseOptions {
  onMigration?: OnMigration;
}

/**
 * A synchronised YJS document, its version, and its awareness state.
 *
 * Acquire one with {@link getSyncDatabase} rather than constructing
 * directly, so a single instance is shared per name.
 */
export class SyncDatabase {
  readonly name: string;
  readonly channel: string;
  doc: Y.Doc;
  awareness: Awareness;
  version: bigint = 0n;
  onMigration: OnMigration | null;

  private remoteVersion: bigint | null = null;
  private serverSessionId: string | null = null;
  private readonly _onConnected: () => void;

  constructor(name: string, options: SyncDatabaseOptions = {}) {
    this.name = name;
    this.channel = `syncdb:${name}`;
    this.onMigration = options.onMigration ?? null;
    this.doc = new Y.Doc();
    this.awareness = new Awareness(this.doc);

    this._onConnected = () => this._handleConnected();

    // When the server is down it forgets the client IDs it handed out.
    kaithemapi.subscribe('__SERVER_DISCONNECTED__', () => {
      this.doc.clientID = getRandom52BitInt();
      console.log(
        'Disconnected from server, resetting client ID to:',
        this.doc.clientID
      );
    });

    kaithemapi.subscribe(this.channel, (value: unknown) => {
      this._handleMessage(value);
    });

    this._bindAwareness();

    globalThis.addEventListener('kaithemapi_connected', this._onConnected);

    // If we are already connected the event will not fire again, so do
    // the handshake now. It is harmless if we are not connected yet
    // because the handshake is repeated when the connection opens.
    this._handleConnected();
  }

  private _bindAwareness(): void {
    this.awareness.on(
      'update',
      ({
        added,
        updated,
        removed,
      }: {
        added: number[];
        updated: number[];
        removed: number[];
      }) => {
        const changedClients = [...added, ...updated, ...removed];
        if (changedClients.length === 0) {
          return;
        }
        const update = Awareness.encodeAwarenessUpdate(
          this.awareness,
          changedClients
        );
        if (update.byteLength > 0) {
          kaithemapi.sendValue(
            this.channel,
            _makeTypedMessage(MSG_AWARENESS, update)
          );
        }
      }
    );
  }

  private _handleConnected(): void {
    // We do not know the remote's version until it tells us.
    this.remoteVersion = null;
    // The version message must always be the first thing the remote
    // sees, before any document state.
    this._sendVersion();
    void this._fetchInitialState();
  }

  private _sendVersion(): void {
    kaithemapi.sendValue(
      this.channel,
      _makeTypedMessage(MSG_VERSION, encodeVersion(this.version))
    );
  }

  private _handleVersionMessage(payload: Uint8Array): void {
    let remoteVersion: bigint;
    try {
      remoteVersion = decodeVersion(payload);
    } catch (error) {
      console.warn('Ignoring malformed version message:', error);
      return;
    }

    if (!versionIsSane(remoteVersion)) {
      console.error(
        'Ignoring version too far in the future:',
        remoteVersion
      );
      return;
    }

    this.remoteVersion = remoteVersion;

    if (remoteVersion > this.version) {
      console.info(
        'Remote reported a newer version, migrating:',
        remoteVersion
      );
      this._incomingMigration(remoteVersion);
    } else if (remoteVersion < this.version) {
      // We are ahead of the remote; let it know so it can migrate.
      this._sendVersion();
    }
  }

  private _handleMessage(value: unknown): void {
    if (!value) {
      return;
    }

    try {
      if (value instanceof Uint8Array && value.byteLength >= 4) {
        const msgType = value.slice(0, 4);
        const payload = value.slice(4);

        if (_bytesEqual(msgType, MSG_VERSION)) {
          this._handleVersionMessage(payload);
          return;
        }

        // Ignore traffic from a remote that is not on our version.
        if (
          this.remoteVersion === null ||
          this.remoteVersion !== this.version
        ) {
          return;
        }

        if (_bytesEqual(msgType, MSG_UPDATE)) {
          Y.applyUpdate(this.doc, payload);
        } else if (_bytesEqual(msgType, MSG_AWARENESS)) {
          Awareness.applyUpdate(this.awareness, payload);
        }
        return;
      }

      if (typeof value === 'object' && value !== null) {
        const session = (value as { session?: string }).session;
        if (session !== undefined) {
          this._handleSession(session);
        }
      }
    } catch (error) {
      console.error('Failed to apply YJS message:', error);
    }
  }

  private _handleSession(session: string): void {
    if (this.serverSessionId !== null && this.serverSessionId !== session) {
      // The server replaced the underlying document, so reload the
      // page to pick it up cleanly.
      globalThis.location.reload();
      return;
    }
    this.serverSessionId = session;
  }

  /**
   * Migrate to a new version using a JSON-like snapshot.
   *
   * Builds a new document from the snapshot, then hands the old and new
   * documents to the migration callback so that any application level
   * data that can be merged is carried over. The new document and
   * version are saved and the migration is advertised to the server,
   * which responds with a new session and triggers a page reload.
   *
   * @param version The new version number (a millisecond timestamp).
   * @param snapshot A JSON-like map of top level keys for the new doc.
   */
  beginMigration(
    version: bigint,
    snapshot: Record<string, unknown>
  ): void {
    if (!versionIsSane(version)) {
      throw new Error(
        `Migration version is too far in the future: ${version}`
      );
    }
    if (version <= this.version) {
      throw new Error(
        `Migration version ${version} must be greater than the ` +
          `current version ${this.version}`
      );
    }

    this._migrate(version, snapshot);
  }

  private _incomingMigration(newVersion: bigint): void {
    if (this.onMigration === null) {
      console.error(
        'Received a migration but no onMigration callback is set, ' +
          'ignoring:',
        newVersion
      );
      return;
    }

    // No snapshot is available locally, so the callback must rebuild
    // whatever application state it can and the remote fills in the
    // rest.
    this._migrate(newVersion, null);
  }

  private _migrate(
    newVersion: bigint,
    snapshot: Record<string, unknown> | null
  ): void {
    const oldDB = this.doc;
    const oldVersion = this.version;

    const newDb = new Y.Doc();
    if (snapshot !== null) {
      seedDocument(newDb, snapshot);
    }

    if (this.onMigration !== null) {
      this.onMigration(oldDB, oldVersion, newDb, newVersion);
    }

    this._applyNewDocument(newDb, newVersion);
  }

  private _applyNewDocument(newDb: Y.Doc, newVersion: bigint): void {
    // The old document is discarded. Components are expected to reload
    // and refetch once the server reports the new session.
    const oldAwareness = this.awareness;
    this.doc = newDb;
    this.version = newVersion;
    this.remoteVersion = null;
    this.awareness = new Awareness(newDb);
    this._bindAwareness();
    oldAwareness.destroy();

    // The version must go out first, then our state, so that the remote
    // trusts the update that follows.
    this._sendVersion();
    kaithemapi.sendValue(
      this.channel,
      _makeTypedMessage(MSG_UPDATE, Y.encodeStateAsUpdate(newDb))
    );
  }

  /**
   * Fetch the initial state from the server over HTTP.
   */
  private async _fetchInitialState(): Promise<void> {
    try {
      const serverVector = await fetch(
        `/api/syncdb/${encodeURIComponent(this.name)}/state_vector`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/octet-stream',
          },
        }
      );

      const updatesForServer = Y.encodeStateAsUpdate(
        this.doc,
        new Uint8Array(await serverVector.arrayBuffer())
      );

      // Send update with type code prefix
      kaithemapi.sendValue(
        this.channel,
        _makeTypedMessage(MSG_UPDATE, updatesForServer)
      );

      // Get our current state vector
      const stateVector = Y.encodeStateVector(this.doc);

      const response = await fetch(
        `/api/syncdb/${encodeURIComponent(this.name)}/sync`,
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
        Y.applyUpdate(this.doc, new Uint8Array(update));
        console.log('Synced initial state for:', this.name);
      }
    } catch (error) {
      console.error('Error fetching initial state:', error);
      picodash.snackbar.createSnackbar(
        'Failed to fetch CRDT state. Refresh page or look for a newer ' +
          'version of this document.',
        {
          timeout: 60_000,
          accent: 'error',
        }
      );
    }
  }
}

/**
 * Cache of SyncDatabase instances by name.
 */
const syncDatabases = new Map<string, SyncDatabase>();

/**
 * Get a SyncDatabase by name, creating it on first use.
 *
 * @param name The name of the database to get.
 * @param options Optional settings. The onMigration callback is set on
 *   an existing database if provided.
 * @returns The shared SyncDatabase for the name.
 */
export function getSyncDatabase(
  name: string,
  options: SyncDatabaseOptions = {}
): SyncDatabase {
  const existing = syncDatabases.get(name);
  if (existing) {
    if (options.onMigration) {
      existing.onMigration = options.onMigration;
    }
    return existing;
  }

  const database = new SyncDatabase(name, options);
  syncDatabases.set(name, database);
  return database;
}

/**
 * Get a YJS document by name, creating it on first use.
 *
 * @param name The name of the document to get.
 * @returns The YJS document.
 */
export function getDocument(name: string): Y.Doc {
  return getSyncDatabase(name).doc;
}

/**
 * Get or create a YJS Awareness instance for a document.
 *
 * Awareness is used for presence, cursor positions, and other
 * ephemeral user state.
 *
 * @param name The name of the document.
 * @returns The YJS Awareness instance.
 */
export function getAwareness(name: string): Awareness {
  return getSyncDatabase(name).awareness;
}

export default {
  getDocument,
  getAwareness,
  getSyncDatabase,
  SyncDatabase,
};