// Text Widget Base Class for text-based sources
// Provides common text styling configuration and rendering

import { Source, SourceData, SourceConfig } from "./source-type";

export interface TextWidgetConfig extends SourceConfig {
  text_color?: string;
  text_size?: number;
  font_family?: string;
  text_shadow_offset_x?: number;
  text_shadow_offset_y?: number;
  text_shadow_blur?: number;
  text_shadow_color?: string;
  text_alignment?: "left" | "center" | "right";
  transition_duration?: number;
}

/**
 * Base class for text-based sources (clock, text, etc)
 * Handles common text styling and configuration
 */
export abstract class TextWidgetSource extends Source {
  private displayElementA: HTMLElement | null = null;
  private displayElementB: HTMLElement | null = null;
  private currentElement: "A" | "B" = "A";

  private oldHtml = "";
  constructor(data: SourceData) {
    super(data);
  }

  /**
   * Get typed config
   */
  get textConfig(): TextWidgetConfig {
    return this.config as TextWidgetConfig;
  }

  /**
   * Initialize A/B display elements within a container
   */
  protected initializeABElements(container: HTMLElement): void {
    if (this.displayElementA) {
      return; // Already initialized
    }

    this.displayElementA = document.createElement("div");
    this.displayElementA.style.position = "absolute";
    this.displayElementA.style.top = "0";
    this.displayElementA.style.left = "0";
    this.displayElementA.style.width = "100%";
    this.displayElementA.style.height = "100%";
    this.displayElementA.style.opacity = "1";
    container.appendChild(this.displayElementA);

    this.displayElementB = document.createElement("div");
    this.displayElementB.style.position = "absolute";
    this.displayElementB.style.top = "0";
    this.displayElementB.style.left = "0";
    this.displayElementB.style.width = "100%";
    this.displayElementB.style.height = "100%";
    this.displayElementB.style.opacity = "0";
    container.appendChild(this.displayElementB);
  }

  /**
   * Subclasses call this to set the innerHTML of a display element with crossfade
   */
  protected setHTML(container: HTMLElement, html: string): void {
    this.initializeABElements(container);

    const currentElement =
      this.currentElement === "A" ? this.displayElementA : this.displayElementB;
    const nextElement =
      this.currentElement === "A" ? this.displayElementB : this.displayElementA;
    if (!nextElement) {
      return;
    }
    if (!currentElement) {
      return;
    }

    // Always apply text styles to both elements to ensure styling is current
    this.applyTextStyles(currentElement!);
    this.applyTextStyles(nextElement);

    const contentChanged = this.oldHtml!== html;

    // Only transition if content actually changed
    if (!contentChanged) {
      return;
    }
    this.oldHtml = html;
    nextElement.innerHTML = html;

    const config = this.textConfig;
    const duration = config.transition_duration || 0;

    if (duration > 0) {
      // Animate out current element
      currentElement.animate(
        [{ opacity: "1" }, { opacity: "0" }],
        {
          duration,
          easing: "ease-in-out",
          fill: "forwards",
        }
      );

      // Animate in next element
      nextElement.animate(
        [{ opacity: "0" }, { opacity: "1" }],
        {
          duration,
          easing: "linear",
          fill: "forwards",
        }
      );

      // Switch current element after animation completes
      setTimeout(() => {
        this.currentElement = this.currentElement === "A" ? "B" : "A";
      }, duration);
    } else {
      // No transition, just swap
      currentElement!.style.opacity = "0";
      nextElement.style.opacity = "1";
      this.currentElement = this.currentElement === "A" ? "B" : "A";
    }
  }

  /**
   * Apply text styling to element
   */
  private applyTextStyles(element: HTMLElement): void {
    const config = this.textConfig;

    element.style.color = config.text_color || "#ffffff";
    element.style.fontSize = `${config.text_size || 48}px`;
    element.style.fontFamily = config.font_family || "monospace";
    element.style.textAlign =
      (config.text_alignment as CanvasTextAlign) || "center";
    element.style.justifyContent =
      (config.text_alignment as CanvasTextAlign) || "center";
    element.style.margin = "0";
    element.style.padding = "0px";
    element.style.lineHeight = "1.2";
    element.style.display = "flex";
    element.style.alignItems = "center";
    element.style.justifyContent = "center";

    // Text shadow
    if (
      config.text_shadow_blur !== undefined &&
      config.text_shadow_offset_x !== undefined &&
      config.text_shadow_offset_y !== undefined
    ) {
      element.style.textShadow = `${config.text_shadow_offset_x}px ${config.text_shadow_offset_y}px ${config.text_shadow_blur}px ${config.text_shadow_color || "rgba(0,0,0,0.5)"}`;
    }
  }

  /**
   * Render configuration UI for text widget styling
   */
  renderTextWidgetConfigControls(
    container: HTMLElement,
    onUpdate: (source: Source) => void
  ): void {
    const config = this.textConfig;

    const html = `
      <h3>Text Widget Config</h3>

      <div class="form-group">
        <label>Text Color</label>
        <input type="color" id="text-color"
               value="${config.text_color || "#ffffff"}">
      </div>

      <div class="form-group">
        <label>Font Size (px)</label>
        <input type="number" id="text-size"
               min="8" max="200" step="1"
               value="${config.text_size || 48}">
      </div>

      <div class="form-group">
        <label>Font Family</label>
        <input type="text" id="font-family"
               list="available-fonts"
               placeholder="monospace"
               value="${config.font_family || "monospace"}">

               <p>Add new fonts as file resources in the module, in /public_resources/fonts</p>
      </div>

      <div class="form-group">
        <label>Text Alignment</label>
        <select id="text-alignment">
          <option value="left" ${config.text_alignment === "left" ? "selected" : ""}>Left</option>
          <option value="center" ${config.text_alignment === "center" || !config.text_alignment ? "selected" : ""}>Center</option>
          <option value="right" ${config.text_alignment === "right" ? "selected" : ""}>Right</option>
        </select>
      </div>

      <div class="form-group">
        <label>Window Size (px)</label>
        <p style="font-size: 0.85rem; color: #999; margin-top: 0rem; margin-bottom: 0.5rem;">
          Size of the text display area before transformation
        </p>
        <div class="size-input-row">
          <input type="number" id="window-width"
                 placeholder="Width" min="1"
                 value="${config.window_width || 800}">
          <input type="number" id="window-height"
                 placeholder="Height" min="1"
                 value="${config.window_height || 200}">
        </div>
      </div>

      <div class="form-group">
        <label>Text Shadow</label>
        <div class="form-group">
          <label>Shadow Offset X (px)</label>
          <input type="number" id="shadow-offset-x"
                 step="1"
                 value="${config.text_shadow_offset_x || 2}">
        </div>
        <div class="form-group">
          <label>Shadow Offset Y (px)</label>
          <input type="number" id="shadow-offset-y"
                 step="1"
                 value="${config.text_shadow_offset_y || 2}">
        </div>
        <div class="form-group">
          <label>Shadow Blur (px)</label>
          <input type="number" id="shadow-blur"
                 min="0" max="50" step="1"
                 value="${config.text_shadow_blur || 4}">
        </div>
        <div class="form-group">
          <label>Shadow Color</label>
          <input type="color" id="shadow-color"
                 value="${config.text_shadow_color || "#000000"}">
        </div>
      </div>

      <div class="form-group">
        <label>Transition Duration (ms)</label>
        <input type="number" id="transition-duration"
               min="0" max="5000" step="50"
               value="${config.transition_duration || 0}">
        <p style="font-size: 0.85rem; color: #999; margin-top: 0.5rem;">
          Time in milliseconds for fade transition when text content changes. Set to 0 for no transition.
        </p>
      </div>
    `;

    container.innerHTML += html;

    // Wire up event listeners
    const textColor = container.querySelector(
      "#text-color"
    ) as HTMLInputElement;
    textColor?.addEventListener("input", (e) => {
      config.text_color = (e.target as HTMLInputElement).value;
      onUpdate(this);
    });

    const textSize = container.querySelector("#text-size") as HTMLInputElement;
    textSize?.addEventListener("input", (e) => {
      config.text_size = Number.parseInt((e.target as HTMLInputElement).value);
      onUpdate(this);
    });

    const fontFamily = container.querySelector(
      "#font-family"
    ) as HTMLInputElement;
    fontFamily?.addEventListener("input", (e) => {
      config.font_family = (e.target as HTMLInputElement).value;
      onUpdate(this);
    });

    const textAlignment = container.querySelector(
      "#text-alignment"
    ) as HTMLSelectElement;
    textAlignment?.addEventListener("change", (e) => {
      config.text_alignment = (e.target as HTMLSelectElement).value as
        | "left"
        | "center"
        | "right";
      onUpdate(this);
    });

    const windowWidth = container.querySelector(
      "#window-width"
    ) as HTMLInputElement;
    windowWidth?.addEventListener("input", (e) => {
      config.window_width = Number.parseInt(
        (e.target as HTMLInputElement).value
      );
      onUpdate(this);
    });

    const windowHeight = container.querySelector(
      "#window-height"
    ) as HTMLInputElement;
    windowHeight?.addEventListener("input", (e) => {
      config.window_height = Number.parseInt(
        (e.target as HTMLInputElement).value
      );
      onUpdate(this);
    });

    const shadowOffsetX = container.querySelector(
      "#shadow-offset-x"
    ) as HTMLInputElement;
    shadowOffsetX?.addEventListener("input", (e) => {
      config.text_shadow_offset_x = Number.parseInt(
        (e.target as HTMLInputElement).value
      );
      onUpdate(this);
    });

    const shadowOffsetY = container.querySelector(
      "#shadow-offset-y"
    ) as HTMLInputElement;
    shadowOffsetY?.addEventListener("input", (e) => {
      config.text_shadow_offset_y = Number.parseInt(
        (e.target as HTMLInputElement).value
      );
      onUpdate(this);
    });

    const shadowBlur = container.querySelector(
      "#shadow-blur"
    ) as HTMLInputElement;
    shadowBlur?.addEventListener("input", (e) => {
      config.text_shadow_blur = Number.parseInt(
        (e.target as HTMLInputElement).value
      );
      onUpdate(this);
    });

    const shadowColor = container.querySelector(
      "#shadow-color"
    ) as HTMLInputElement;
    shadowColor?.addEventListener("input", (e) => {
      config.text_shadow_color = (e.target as HTMLInputElement).value;
      onUpdate(this);
    });

    const transitionDuration = container.querySelector(
      "#transition-duration"
    ) as HTMLInputElement;
    transitionDuration?.addEventListener("input", (e) => {
      config.transition_duration = Number.parseInt(
        (e.target as HTMLInputElement).value
      );
      onUpdate(this);
    });
  }
}
