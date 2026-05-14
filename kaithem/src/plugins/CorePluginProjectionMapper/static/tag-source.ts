// Tag Display Source
// Displays numeric and string tag values with C-style formatting

import { Source, SourceData, registerSourceType } from "./source-type";
import { TextWidgetSource, TextWidgetConfig } from "./text-widget-source";

interface TagConfig extends TextWidgetConfig {
  tag_name?: string;
  format_string?: string;
}

/**
 * Simple C-style format string support
 * Supports: %s (string/number), %d (integer), %f (float), %e (exponential)
 * Modifiers: %.2f, %5d, etc.
 */
function formatValue(value: unknown, format: string): string {
  // Handle %s - default string/number format
  if (format === "%s") {
    return String(value);
  }

  const number_ = Number(value);
  if (Number.isNaN(number_)) {
    // For non-numeric values with numeric format, just return string
    return String(value);
  }

  // Match format specifier patterns like %5d, %.2f, %e, etc.
  const match = format.match(/^%(-)?(\d+)?(?:\.(\d+))?([dfe])$/);
  if (!match) {
    return String(value);
  }

  const [, leftAlign, width, precision, type] = match;
  const w = width ? Number.parseInt(width) : 0;
  const p = precision ? Number.parseInt(precision) : 6;
  let result = "";

  switch (type) {
    case "d": {
      result = Math.floor(number_).toString();
      break;
    }
    case "f": {
      result = number_.toFixed(p);
      break;
    }
    case "e": {
      result = number_.toExponential(p);
      break;
    }
    default: {
      result = String(value);
    }
  }

  // Handle width padding
  if (w > 0) {
    result = leftAlign ? result.padEnd(w, " ") : result.padStart(w, " ");
  }

  return result;
}

/**
 * Tag display source showing current value of a tag
 * Uses subscriptions to update in real-time
 */
export class TagSource extends TextWidgetSource {
  private container: HTMLElement | null = null;
  private currentValue: unknown = null;

  constructor(data: SourceData) {
    super(data);
    this.registerTagHandler("tag_value", (value) => {
      this.currentValue = value;
      this.updateDisplay();
    });
  }

  get tagConfig(): TagConfig {
    return this.config as TagConfig;
  }

  protected collectDesiredSubscriptions(desired: Record<string, string>): void {
    // Subscribe to the tag specified in config
    if (this.tagConfig.tag_name?.trim()) {
      desired.tag_value = this.tagConfig.tag_name.trim();
    }
  }

  updateContent(container: HTMLElement): void {
    // Store container for updates
    if (!this.container) {
      this.container = container;
      container.style.position = "relative";
      container.style.overflow = "hidden";
    }
    this.updateDisplay();
  }

  private updateDisplay(): void {
    if (!this.container) return;

    // Allow display to update even if currentValue is null (shows empty)
    const displayText = this.currentValue === null ? "" : formatValue(this.currentValue, this.tagConfig.format_string || "%s");
    this.setHTML(this.container, displayText);
  }

  renderConfigUI(
    container: HTMLElement,
    onUpdate: (source: Source) => void
  ): void {
    const config = this.tagConfig;

    container.innerHTML = `
      <h3>Tag Display Config</h3>
      <div class="form-group">
        <label>Tag Name</label>
        <input type="text" id="tag-name" data-testid="tag-name"
               list="available-tags"
               placeholder="Enter tag name"
               value="${config.tag_name || ""}">
      </div>

      <div class="form-group">
        <label>Format String</label>
        <input type="text" id="format-string" data-testid="tag-format-string"
               placeholder="%s"
               value="${config.format_string || "%s"}">
        <p style="font-size: 0.85rem; color: #999; margin-top: 0.5rem;">
          Examples: %s (default), %d (integer), %.2f (float),
          %e (exponential), %5d (padded)
        </p>
      </div>
    `;

    // Append text widget controls
    this.renderTextWidgetConfigControls(container, onUpdate);

    // Wire up tag name
    const tagNameInput = container.querySelector(
      "#tag-name"
    ) as HTMLInputElement;
    tagNameInput?.addEventListener("input", (eventObject) => {
      config.tag_name = (eventObject.target as HTMLInputElement).value;
      onUpdate(this);
    });

    // Wire up format string
    const formatStringInput = container.querySelector(
      "#format-string"
    ) as HTMLInputElement;
    formatStringInput?.addEventListener("input", (eventObject) => {
      config.format_string = (eventObject.target as HTMLInputElement).value;
      onUpdate(this);
    });
  }
}

// Register the tag source type
registerSourceType("tag", TagSource);
