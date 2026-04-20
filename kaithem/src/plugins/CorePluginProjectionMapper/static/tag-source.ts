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

  const num = Number(value);
  if (Number.isNaN(num)) {
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
      result = Math.floor(num).toString();
      break;
    }
    case "f": {
      result = num.toFixed(p);
      break;
    }
    case "e": {
      result = num.toExponential(p);
      break;
    }
    default:
      result = String(value);
  }

  // Handle width padding
  if (w > 0) {
    if (leftAlign) {
      result = result.padEnd(w, " ");
    } else {
      result = result.padStart(w, " ");
    }
  }

  return result;
}

/**
 * Tag display source showing current value of a tag
 * Uses subscriptions to update in real-time
 */
export class TagSource extends TextWidgetSource {
  private displayElement: HTMLElement | null = null;
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
    // Create display element if needed
    if (!this.displayElement) {
      this.displayElement = document.createElement("div");
      this.displayElement.style.width = "100%";
      this.displayElement.style.height = "100%";
      this.displayElement.style.display = "flex";
      this.displayElement.style.alignItems = "center";
      this.displayElement.style.justifyContent = "center";
      container.append(this.displayElement);
    }
    this.updateDisplay();
  }

  private updateDisplay(): void {
    if (!this.displayElement || this.currentValue === null) return;

    const format = this.tagConfig.format_string || "%s";
    const displayText = formatValue(this.currentValue, format);
    this.setHTML(this.displayElement, displayText);
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
        <input type="text" id="tag-name"
               list="available-tags"
               placeholder="Enter tag name"
               value="${config.tag_name || ""}">
      </div>

      <div class="form-group">
        <label>Format String</label>
        <input type="text" id="format-string"
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
    tagNameInput?.addEventListener("input", (e) => {
      config.tag_name = (e.target as HTMLInputElement).value;
      onUpdate(this);
    });

    // Wire up format string
    const formatStringInput = container.querySelector(
      "#format-string"
    ) as HTMLInputElement;
    formatStringInput?.addEventListener("input", (e) => {
      config.format_string = (e.target as HTMLInputElement).value;
      onUpdate(this);
    });
  }
}

// Register the tag source type
registerSourceType("tag", TagSource);
