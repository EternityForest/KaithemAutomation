// Iframe Source Type Implementation

import { Source, SourceData, registerSourceType } from "./source-type";

export class IframeSource extends Source {
  constructor(data: SourceData) {
    super(data);
  }

  updateContent(container: HTMLElement): void {
    // No unecessary refresh

    if (!container.querySelector("iframe")) {
      const iframe = document.createElement("iframe");
      container.append(iframe);
    }

    const iframe = container.querySelector("iframe")!;

    if (iframe.src !== this.config.url || "") {
      iframe.src = this.config.url || "";
    }
    iframe.style.border = "none";
    iframe.style.pointerEvents = "none";
    iframe.style.display = "block";
    iframe.style.position = "absolute";
    iframe.style.top = "0";
    iframe.style.left = "0";

    iframe.sandbox.add("allow-same-origin", "allow-scripts", "allow-forms");
  }

  applyTransforms(windowElement: HTMLElement): void {
    super.applyTransforms(windowElement);

    // Apply container sizing and cropping
    const config = this.config || {};
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
    container: HTMLElement,
    onUpdate: (source: Source) => void
  ): void {
    container.innerHTML = `
      <h3>Source Config</h3>
      <div class="form-group">
        <label>URL</label>
        <input type="text" id="source-url"
               placeholder="https://example.com"
               value="${this.config.url || ""}">
      </div>
      <div class="form-group">
        <label>Window Size (px)</label>
        <div class="size-input-row">
          <input type="number" id="window-width"
                 placeholder="Width" min="1"
                 value="${this.config.window_width || 800}">
          <input type="number" id="window-height"
                 placeholder="Height" min="1"
                 value="${this.config.window_height || 600}">
        </div>
      </div>
      <div class="form-group">
        <label>Render Size (px)</label>
        <div class="size-input-row">
          <input type="number" id="render-width"
                 placeholder="Width" min="1"
                 value="${this.config.render_width || 800}">
          <input type="number" id="render-height"
                 placeholder="Height" min="1"
                 value="${this.config.render_height || 600}">
        </div>
      </div>
      <div class="form-group">
        <label>Crop Position (px)</label>
        <div class="size-input-row">
          <input type="number" id="crop-x"
                 placeholder="X" min="0"
                 value="${this.config.crop_x || 0}">
          <input type="number" id="crop-y"
                 placeholder="Y" min="0"
                 value="${this.config.crop_y || 0}">
        </div>
      </div>
    `;

    const sourceUrlInput = container.querySelector(
      "#source-url"
    ) as HTMLInputElement;
    if (sourceUrlInput) {
      sourceUrlInput.addEventListener("input", (event) => {
        this.config.url = (event.target as HTMLInputElement).value;
        onUpdate(this);
      });
    }

    const windowWidthInput = container.querySelector(
      "#window-width"
    ) as HTMLInputElement;
    if (windowWidthInput) {
      windowWidthInput.addEventListener("input", (event) => {
        this.config.window_width = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(this);
      });
    }

    const windowHeightInput = container.querySelector(
      "#window-height"
    ) as HTMLInputElement;
    if (windowHeightInput) {
      windowHeightInput.addEventListener("input", (event) => {
        this.config.window_height = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(this);
      });
    }

    const renderWidthInput = container.querySelector(
      "#render-width"
    ) as HTMLInputElement;
    if (renderWidthInput) {
      renderWidthInput.addEventListener("input", (event) => {
        this.config.render_width = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(this);
      });
    }

    const renderHeightInput = container.querySelector(
      "#render-height"
    ) as HTMLInputElement;
    if (renderHeightInput) {
      renderHeightInput.addEventListener("input", (event) => {
        this.config.render_height = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(this);
      });
    }

    const cropXInput = container.querySelector("#crop-x") as HTMLInputElement;
    if (cropXInput) {
      cropXInput.addEventListener("input", (event) => {
        this.config.crop_x = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(this);
      });
    }

    const cropYInput = container.querySelector("#crop-y") as HTMLInputElement;
    if (cropYInput) {
      cropYInput.addEventListener("input", (event) => {
        this.config.crop_y = Number.parseInt(
          (event.target as HTMLInputElement).value
        );
        onUpdate(this);
      });
    }
  }
}

// Register iframe source type
registerSourceType("iframe", IframeSource);
