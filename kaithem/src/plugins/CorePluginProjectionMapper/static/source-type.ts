
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
  url?: string;
  window_width?: number;
  window_height?: number;
  render_width?: number;
  render_height?: number;
  crop_x?: number;
  crop_y?: number;
  source_id?: string;
}

export interface Source {
  id: string;
  name: string;
  type: string;
  config: SourceConfig;
  transform: SourceTransform;
  visible: boolean;
}


/**
 * Base class for source type implementations
 * Handles tag subscriptions and common opacity logic
 */
export abstract class SourceType {
  protected tagSubscriptions: Record<
    string,
    { tag: string; callback: (value: number) => void }
  > = {};
  protected tagOpacityMultipliers: Record<string, number> = {};

  /**
   * Setup or update tag subscriptions for this source
   * Default implementation handles opacity tag
   */
  updateSubscriptions(
    source: Source,
    subscribe: (sourceId: string, tagName: string) => void,
    unsubscribe: (sourceId: string) => void
  ): void {
    const opacityTag = source.transform.opacity_tag?.trim();

    if (!opacityTag) {
      if (this.tagSubscriptions[source.id]) {
        unsubscribe(source.id);
      }
      return;
    }

    const existing = this.tagSubscriptions[source.id];
    if (existing && existing.tag === opacityTag) {
      return; // Already subscribed
    }

    if (existing) unsubscribe(source.id);
    subscribe(source.id, opacityTag);
  }

  /**
   * Create DOM elements for the preview window
   * Returns the window-container div for type-specific setup
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
   * Called when source is first created or updated
   * Subclasses override to add specific content
   */
  abstract updateContent(container: HTMLElement, source: Source): void;

  /**
   * Apply transforms and opacity to the preview window
   * Called before rendering; base class handles opacity and blend mode
   */
  applyTransforms(
    windowElement: HTMLElement,
    source: Source,
    getOpacityMultiplier: (sourceId: string) => number
  ): void {
    const config = source.config || {};
    const transform = source.transform || {};

    windowElement.style.position = "absolute";

    // Window size
    const windowWidth = config.window_width || 800;
    const windowHeight = config.window_height || 600;
    windowElement.style.width = `${windowWidth}px`;
    windowElement.style.height = `${windowHeight}px`;

    // Position and perspective (if corners provided)
    const corners = transform.corners;
    if (corners) {
      windowElement.style.left = `${corners.tl.x}px`;
      windowElement.style.top = `${corners.tl.y}px`;
    } else {
      windowElement.style.left = "0";
      windowElement.style.top = "0";
    }

    // Opacity (manual * tag multiplier)
    if (transform.opacity !== undefined) {
      const manualOpacity = transform.opacity;
      const tagMultiplier = getOpacityMultiplier(source.id);
      const finalOpacity = manualOpacity * tagMultiplier;
      windowElement.style.opacity = finalOpacity.toString();
    }

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
    source: Source,
    container: HTMLElement,
    _onUpdate: (source: Source) => void
  ): void {
    container.innerHTML = `<h3>Source Config</h3>
       <p>No configuration available for source type: ${source.type}</p>`;
  }

  /**
   * Cleanup when source is deleted
   * Default is empty; subclasses override if needed
   */
  cleanup(): void {
    // Override in subclasses
  }
}

// Source type registry
export const sourceTypeRegistry: Record<string, SourceType> = {};

export function getSourceType(type: string): SourceType {
  return sourceTypeRegistry[type];
}
