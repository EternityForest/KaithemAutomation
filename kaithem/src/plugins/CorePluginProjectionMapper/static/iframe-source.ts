/**
 * Iframe source type implementation
 */

import type { Source } from "./source-type";
import { SourceType, sourceTypeRegistry } from "./source-type";

class IframeSourceType extends SourceType {
  updateContent(container: HTMLElement, source: Source): void {
    // Clear any existing content
    if (container.children.length === 0) {
      const iframe = document.createElement("iframe");
      container.append(iframe);
      iframe.sandbox.add("allow-same-origin", "allow-scripts", "allow-forms");
    }
    const iframe = container.querySelector("iframe")!;
    if (iframe.src !== source.config.url) {
      iframe.src = source.config.url || "";
    }
    iframe.style.border = "none";
    iframe.style.pointerEvents = "none";
    iframe.style.display = "block";
    iframe.style.position = "absolute";
    iframe.style.top = "0";
    iframe.style.left = "0";
  }

  applyTransforms(
    windowElement: HTMLElement,
    source: Source,
    getOpacityMultiplier: (sourceId: string) => number
  ): void {
    super.applyTransforms(windowElement, source, getOpacityMultiplier);

    // Apply container sizing and cropping
    const config = source.config || {};
    const container = windowElement.querySelector(
      ".window-container"
    ) as HTMLElement;
    if (container) {
      const windowWidth = config.window_width || 800;
      const windowHeight = config.window_height || 600;
      const renderWidth = config.render_width || windowWidth;
      const renderHeight = config.render_height || windowHeight;
      const cropX = config.crop_x || 0;
      const cropY = config.crop_y || 0;

      container.style.width = `${windowWidth}px`;
      container.style.height = `${windowHeight}px`;

      const iframe = container.querySelector("iframe") as HTMLIFrameElement;
      if (iframe) {
        iframe.style.width = `${renderWidth}px`;
        iframe.style.height = `${renderHeight}px`;
        iframe.style.left = `${-cropX}px`;
        iframe.style.top = `${-cropY}px`;
      }
    }
  }

  renderConfigUI(
    source: Source,
    container: HTMLElement,
    onUpdate: (source: Source) => void
  ): void {
    container.innerHTML = `
      <h3>Source Config</h3>
      <div class="form-group">
        <label>URL</label>
        <input type="text" id="source-url"
               placeholder="https://example.com"
               value="${source.config.url || ""}">
      </div>
      <div class="form-group">
        <label>Window Size (px)</label>
        <div class="size-input-row">
          <input type="number" id="window-width"
                 placeholder="Width" min="1"
                 value="${source.config.window_width || 800}">
          <input type="number" id="window-height"
                 placeholder="Height" min="1"
                 value="${source.config.window_height || 600}">
        </div>
      </div>
      <div class="form-group">
        <label>Render Size (px)</label>
        <div class="size-input-row">
          <input type="number" id="render-width"
                 placeholder="Width" min="1"
                 value="${source.config.render_width || 800}">
          <input type="number" id="render-height"
                 placeholder="Height" min="1"
                 value="${source.config.render_height || 600}">
        </div>
      </div>
      <div class="form-group">
        <label>Crop Position (px)</label>
        <div class="size-input-row">
          <input type="number" id="crop-x"
                 placeholder="X" min="0"
                 value="${source.config.crop_x || 0}">
          <input type="number" id="crop-y"
                 placeholder="Y" min="0"
                 value="${source.config.crop_y || 0}">
        </div>
      </div>
    `;

    const sourceUrlInput = container.querySelector(
      "#source-url"
    ) as HTMLInputElement;
    if (sourceUrlInput) {
      sourceUrlInput.addEventListener("input", (event) => {
        source.config.url = (event.target as HTMLInputElement).value;
        onUpdate(source);
      });
    }

    const windowWidthInput = container.querySelector(
      "#window-width"
    ) as HTMLInputElement;
    if (windowWidthInput) {
      windowWidthInput.addEventListener("input", (event) => {
        source.config.window_width = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(source);
      });
    }

    const windowHeightInput = container.querySelector(
      "#window-height"
    ) as HTMLInputElement;
    if (windowHeightInput) {
      windowHeightInput.addEventListener("input", (event) => {
        source.config.window_height = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(source);
      });
    }

    const renderWidthInput = container.querySelector(
      "#render-width"
    ) as HTMLInputElement;
    if (renderWidthInput) {
      renderWidthInput.addEventListener("input", (event) => {
        source.config.render_width = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(source);
      });
    }

    const renderHeightInput = container.querySelector(
      "#render-height"
    ) as HTMLInputElement;
    if (renderHeightInput) {
      renderHeightInput.addEventListener("input", (event) => {
        source.config.render_height = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(source);
      });
    }

    const cropXInput = container.querySelector("#crop-x") as HTMLInputElement;
    if (cropXInput) {
      cropXInput.addEventListener("input", (event) => {
        source.config.crop_x = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(source);
      });
    }

    const cropYInput = container.querySelector("#crop-y") as HTMLInputElement;
    if (cropYInput) {
      cropYInput.addEventListener("input", (event) => {
        source.config.crop_y = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(source);
      });
    }
  }
}

sourceTypeRegistry["iframe"] = new IframeSourceType();
