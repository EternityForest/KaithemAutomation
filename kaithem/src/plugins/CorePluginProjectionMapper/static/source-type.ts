// Source Type Base Class Architecture
// Each source is an instance of a source type subclass

import { assert } from "console";

export interface Position {
  x: number;
  y: number;
}

export interface Corners {
  tl: Position;
  tr: Position;
  bl: Position;
  br: Position;
}

export interface SourceTransform {
  corners?: Corners;
  opacity?: number;
  opacity_tag?: string;
  blend_mode?: string;
  rotation?: number;
}

export interface SourceConfig {
  window_width?: number;
  window_height?: number;
  url?: string;
  render_width?: number;
  render_height?: number;
  crop_x?: number;
  crop_y?: number;
  [key: string]: any;
}

export interface SourceData {
  id: string;
  name: string;
  type: string;
  config: SourceConfig;
  transform: SourceTransform;
  visible: boolean;
}

/**
 * Base class for all source types
 * Adapter that works with plain source data objects
 */
export abstract class Source {
  protected data: SourceData;

  constructor(data: SourceData) {
    this.data = data;
  }

  // Getters for compatibility
  get id(): string {
    return this.data.id;
  }

  get name(): string {
    return this.data.name;
  }

  get type(): string {
    return this.data.type;
  }

  get config(): SourceConfig {
    return this.data.config;
  }

  get transform(): SourceTransform {
    return this.data.transform;
  }

  get visible(): boolean {
    return this.data.visible;
  }

  set visible(value: boolean) {
    this.data.visible = value;
  }

  // Maps tag name -> handler function
  private tagHandlers: Record<string, (value: number) => void> = {};
  // Tracks which tags should be subscribed based on current state
  private desiredSubscriptions: Record<string, string> = {};

  // Tracks which tags are actually subscribed
  private activeSubscriptions: Record<string, string> = {};

  private tagOpacityVal = 1;

  private activeDestination?: HTMLElement;
  /**
   * Update tag subscriptions to match desired state
   * Compares desired vs active and calls subscribe/unsubscribe as needed
   */
  updateSubscriptions(
    subscribe: (sourceId: string, tagName: string) => void,
    unsubscribe: (sourceId: string) => void
  ): void {
    this.desiredSubscriptions = {};

    // Build desired subscriptions from transform
    if (this.data.transform.opacity_tag?.trim()) {
      this.desiredSubscriptions.opacity_tag =
        this.data.transform.opacity_tag.trim();
      this.registerTagHandler("opacity_tag", (value) => {
        this.tagOpacityVal = value;
        this.applyTransforms();
      });
    } else {
      delete this.desiredSubscriptions.opacity_tag;
    }

    // Allow subclasses to add more desired subscriptions
    this.collectDesiredSubscriptions(this.desiredSubscriptions);

    // Unsubscribe from tags no longer needed
    for (const [tagKey, tagName] of Object.entries(this.activeSubscriptions)) {
      if (!this.desiredSubscriptions[tagKey]) {
        unsubscribe(this.id);
        delete this.activeSubscriptions[tagKey];
      }
    }

    // Subscribe to new tags
    for (const [tagKey, tagName] of Object.entries(this.desiredSubscriptions)) {
      if (this.activeSubscriptions[tagKey] !== tagName) {
        subscribe(this.id, tagName);
        this.activeSubscriptions[tagKey] = tagName;
      }
    }
  }

  /**
   * Hook for subclasses to add additional tag subscriptions
   * Override to add source-type-specific tag handling
   */
  protected collectDesiredSubscriptions(desired: Record<string, string>): void {
    // Override in subclasses to add more subscriptions
  }

  /**
   * Register a tag handler for a specific tag key
   * tagKey: identifier like "opacity_tag", "color_tag", etc
   * handler: function to call with tag value
   */
  protected registerTagHandler(
    tagKey: string,
    handler: (value: number) => void
  ): void {
    this.tagHandlers[tagKey] = handler;
  }

  /**
   * Call the handler for a tag update
   */
  handleTagUpdate(tagKey: string, value: number): void {
    const handler = this.tagHandlers[tagKey];
    if (handler) {
      handler(value);
    }
  }

  /**
   * Create DOM elements for the preview window
   * Returns the window and container elements
   */
  createPreviewElements(): { window: HTMLElement; container: HTMLElement } {
    const window = document.createElement("div");
    window.className = "preview-window";

    const container = document.createElement("div");
    container.className = "window-container";
    container.style.position = "relative";
    container.style.overflow = "hidden";

    window.append(container);
    return { window, container };
  }

  /**
   * Setup or update content within the window-container
   * Subclasses override to add specific content
   */
  abstract updateContent(container: HTMLElement): void;

  /**
   * Apply transforms and opacity to the preview window
   * Subclasses can override to add type-specific transforms
   */
  applyTransforms(windowElement?: HTMLElement): void {
    const config = this.config || {};
    const transform = this.transform || {};

    windowElement = windowElement || this.activeDestination;
    this.activeDestination = windowElement;

    windowElement = windowElement!;

    windowElement.style.position = "absolute";

    // Window size
    const windowWidth = config.window_width || 800;
    const windowHeight = config.window_height || 600;
    windowElement.style.width = `${windowWidth}px`;
    windowElement.style.height = `${windowHeight}px`;

    // Position (set by editor via corners)
    if (transform.corners) {
      windowElement.style.left = `${transform.corners.tl.x}px`;
      windowElement.style.top = `${transform.corners.tl.y}px`;
    } else {
      windowElement.style.left = "0";
      windowElement.style.top = "0";
    }

    // Opacity
    const opacity = (transform.opacity ?? 1) * this.tagOpacityVal;
    windowElement.style.opacity = opacity.toString();

    // Blend mode
    if (transform.blend_mode) {
      windowElement.style.mixBlendMode = transform.blend_mode;
    }
  }

  /**
   * Render UI form for source-specific options
   * Default is empty; subclasses override for custom UI
   */
  renderConfigUI(
    container: HTMLElement,
    onUpdate: (source: Source) => void
  ): void {
    container.innerHTML = `<h3>Source Config</h3>
       <p>No configuration available for source type: ${this.type}</p>`;
  }

  /**
   * Cleanup when source is deleted
   * Override in subclasses if needed
   */
  cleanup(): void {
    // Override in subclasses
  }

  /**
   * Return the underlying data object
   */
  getData(): SourceData {
    return this.data;
  }
}

// Source type registry and factory
const sourceTypeRegistry: Record<string, new (data: SourceData) => Source> = {};

export function registerSourceType(
  type: string,
  constructor: new (data: SourceData) => Source
): void {
  sourceTypeRegistry[type] = constructor;
}

export function createSourceAdapter(data: SourceData): Source {
  const Constructor = sourceTypeRegistry[data.type];
  if (!Constructor) {
    throw new Error(`Unknown source type: ${data.type}`);
  }
  return new Constructor(data);
}
