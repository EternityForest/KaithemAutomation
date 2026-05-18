/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Compact tag description returned by /tag_api/list
 * Used as the parameter type for populateTagsDatalist filter function
 */
export interface CompactTagDescription {
  /** Tag point name (e.g., "/my/tag") */
  name: string;
  /** Tag type: "number", "string", "object", "binary" */
  type: string;
  /** Additional subtype information */
  subtype: string;
  /** Whether the tag is writable */
  writable: boolean;
  /** Whether the current user can write to this tag */
  canWrite: boolean;
}

/**
 * Full tag description returned by /tag_api/info
 * Contains complete metadata about a tag point including current value
 */
export interface FullTagDescription {
  /** Whether the current user can write to this tag */
  writePermission: boolean;
  /** Tag type: "number", "string", "object", "binary" */
  type: string;
  /** Additional subtype information */
  subtype: string;
  /** Current value of the tag (type varies based on tag type) */
  lastVal: any;
  /** Minimum value (numeric tags only) */
  min?: number;
  /** Maximum value (numeric tags only) */
  max?: number;
  /** High threshold (numeric tags only) */
  high?: number;
  /** Low threshold (numeric tags only) */
  low?: number;
  /** Unit of measurement (numeric tags only) */
  unit?: string;
}

export interface KaithemAPI {
  subscribe(key: string, callback: (value: any) => void): void;
  unsubscribe(key: string, callback: (value: any) => void): void;
  checkPermission(perm: string): Promise<any>;
  setValue(key: string, value: any): void;
  sendValue(key: string, value: any): void;
  sendTrigger(key: string, value: any): void;
}

export interface APIWidget {
  uuid: string;
  value: any;
  connect(): void;
  set(value: any): void;
  send(value: any): void;
  upd(value: any): void;
  now(): number;
}

export class TagSubscriptionManager {
  setSubscription(
    name: string,
    tagname: string | null,
    callback: ((value: any) => void) | null,
    callWithInitialState?: boolean
  ): void;
  destroy(): void;
}

/**
 * Fetch available tag points and populate an HTML `<datalist>` element.
 * @param datalist The HTMLDataListElement to populate
 * @param filterFunction Optional filter function receiving CompactTagDescription. Return true to include the tag.
 */
export function populateTagsDatalist(
  datalist: HTMLDataListElement,
  filterFunction?: (tag: CompactTagDescription) => boolean
): Promise<void>;

/**
 * Fetch full metadata for a specific tag point.
 * @param tagname Tag point name (e.g., "/my/tag")
 * @returns Promise resolving to FullTagDescription with tag metadata including current value
 */
export function getTagMetadata(tagname: string): Promise<FullTagDescription>;

export declare const kaithemapi: KaithemAPI;
