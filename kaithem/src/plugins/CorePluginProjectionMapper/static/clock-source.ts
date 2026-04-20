// Digital Clock Source
// Renders a strftime-formatted clock using text widget styling

import {
  Source,
  SourceData,
  registerSourceType,
} from "./source-type";
import {
  TextWidgetSource,
  TextWidgetConfig,
} from "./text-widget-source";
import  strftime from "strftime";

interface ClockConfig extends TextWidgetConfig {
  clock_format?: string;
}

/**
 * Digital clock source using strftime formatting
 */
export class ClockSource extends TextWidgetSource {
  private updateIntervalId: number | null = null;
  private container: HTMLElement | null = null;

  constructor(data: SourceData) {
    super(data);
  }

  get clockConfig(): ClockConfig {
    return this.config as ClockConfig;
  }

  updateContent(container: HTMLElement): void {
    // Store container for updates
    if (!this.container) {
      this.container = container;
      container.style.position = "relative";
      container.style.overflow = "hidden";
    }

    // Start update loop if not running
    if (!this.updateIntervalId) {
      this.updateClock();
      this.updateIntervalId = window.setInterval(() => this.updateClock(), 100);
    }
  }

  private updateClock(): void {
    if (!this.container) return;

    const format = this.clockConfig.clock_format || "%H:%M:%S";
    const now = new Date();
    const timeString = strftime(format, now);

    this.setHTML(this.container, timeString);
  }

  cleanup(): void {
    if (this.updateIntervalId) {
      clearInterval(this.updateIntervalId);
      this.updateIntervalId = null;
    }
  }

  renderConfigUI(
    container: HTMLElement,
    onUpdate: (source: Source) => void
  ): void {
    const config = this.clockConfig;

    container.innerHTML = `
      <h3>Clock Config</h3>
      <div class="form-group">
        <label>Time Format (strftime)</label>
        <input type="text" id="clock-format"
               placeholder="%H:%M:%S"
               value="${config.clock_format || "%H:%M:%S"}">
        <p style="font-size: 0.85rem; color: #999; margin-top: 0.5rem;">
          Examples: %H:%M:%S (24h), %I:%M:%S %p (12h),
          %Y-%m-%d %H:%M (date+time)
        </p>
      </div>
    `;

    // Append text widget controls
    this.renderTextWidgetConfigControls(container, onUpdate);

    // Wire up clock format
    const clockFormat = container.querySelector(
      "#clock-format"
    ) as HTMLInputElement;
    clockFormat?.addEventListener("input", (e) => {
      config.clock_format = (e.target as HTMLInputElement).value;
      onUpdate(this);
    });
  }
}

// Register the clock source type
registerSourceType("clock", ClockSource);
