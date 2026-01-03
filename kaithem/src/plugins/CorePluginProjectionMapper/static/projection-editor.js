// Projection Mapper Editor
// Real-time collaborative editing with WebSocket sync
// Uses CSS perspective transforms instead of VFX for cross-browser compatibility

class ProjectionEditor {
  constructor(container, module, resource, initialData) {
    this.container = container;
    this.module = module;
    this.resource = resource;
    this.data = structuredClone(initialData);
    this.selectedSourceId = null;
    this.draggingCorner = null;
    this.isDragging = false;
    this.dragOffset = { x: 0, y: 0 };

    this.ws = null;
    this.canvasElement = null;
    this.previewWindows = {};
    this.currentScale = 1;

    this.broadcastRateLimitTime = 0;

    // Parse URL params for mode
    const parameters = new URLSearchParams(globalThis.location.search);
    this.isViewerMode =
      parameters.has("fullscreen") || parameters.has("viewer");
    this.init();
  }

  init() {
    this.render();
    // Defer setup until layout is calculated
    requestAnimationFrame(() => {
      this.setupCanvas();
      this.setupEventListeners();
      this.setupWebSocket();
    });
    this.updateSourcesList();
    this.renderPreview();
  }

  render() {
    // eslint-disable-next-line unicorn/prefer-ternary
    if (this.isViewerMode) {
      // Fullscreen viewer mode - minimal UI
      this.container.innerHTML = `
            <div class="projection-editor viewer-mode">
                <div class="editor-canvas-area" style="width: 100%; height: 100vh; overflow: hidden;">
                    <canvas id="preview-canvas"></canvas>
                    <div id="preview-sources"></div>
                </div>
            </div>
        `;
    } else {
      // Editor mode - full UI
      this.container.innerHTML = `
            <div class="projection-editor" id="projection-editor">
                <div class="editor-toolbar">
                    <h2>${this.data.title}</h2>
                    <button id="save-btn" class="btn btn-primary">
                        Save
                    </button>
                </div>

                <div class="editor-main">
                    <div class="editor-canvas-area">
                        <canvas id="preview-canvas"></canvas>
                        <div id="preview-sources"></div>
                    </div>

                    <div class="editor-sidebar">
                        <div class="sidebar-section">
                            <h3>Sources</h3>
                            <button id="add-source-btn"
                                    class="btn btn-sm">
                                + Add Source
                            </button>
                            <div id="sources-list"
                                 class="sources-list">
                            </div>
                        </div>

                        <div class="sidebar-section"
                             id="size-section">
                            <h3>Projection Size</h3>
                            <div class="form-group">
                                <label>Width (px)</label>
                                <input type="number" id="size-width"
                                       min="320" value="1920">
                            </div>
                            <div class="form-group">
                                <label>Height (px)</label>
                                <input type="number" id="size-height"
                                       min="240" value="1080">
                            </div>
                        </div>

                        <div class="sidebar-section"
                             id="transform-section"
                             style="display: none;">
                            <h3>Transform</h3>
                            <div class="form-group">
                                <label>Opacity</label>
                                <input type="range" id="opacity"
                                       min="0" max="1"
                                       step="0.01" value="1">
                                <span id="opacity-val">1.00</span>
                            </div>

                            <div class="form-group">
                                <label>Blend Mode</label>
                                <select id="blend-mode">
                                    <option value="normal">
                                        Normal
                                    </option>
                                    <option value="multiply">
                                        Multiply
                                    </option>
                                    <option value="screen">
                                        Screen
                                    </option>
                                    <option value="overlay">
                                        Overlay
                                    </option>
                                    <option value="darken">
                                        Darken
                                    </option>
                                    <option value="lighten">
                                        Lighten
                                    </option>
                                </select>
                            </div>

                            <div class="form-group">
                                <label>Rotation (deg)</label>
                                <input type="number"
                                       id="rotation"
                                       value="0" step="1">
                            </div>

                            <div class="form-group">
                                <h4>Corner Points</h4>
                                <div class="corners-grid">
                                    <div>
                                        <label>Top-Left</label>
                                        <input type="number"
                                               class="corner-x"
                                               data-corner="tl"
                                               placeholder="X">
                                        <input type="number"
                                               class="corner-y"
                                               data-corner="tl"
                                               placeholder="Y">
                                    </div>
                                    <div>
                                        <label>Top-Right</label>
                                        <input type="number"
                                               class="corner-x"
                                               data-corner="tr"
                                               placeholder="X">
                                        <input type="number"
                                               class="corner-y"
                                               data-corner="tr"
                                               placeholder="Y">
                                    </div>
                                    <div>
                                        <label>Bottom-Left
                                        </label>
                                        <input type="number"
                                               class="corner-x"
                                               data-corner="bl"
                                               placeholder="X">
                                        <input type="number"
                                               class="corner-y"
                                               data-corner="bl"
                                               placeholder="Y">
                                    </div>
                                    <div>
                                        <label>Bottom-Right
                                        </label>
                                        <input type="number"
                                               class="corner-x"
                                               data-corner="br"
                                               placeholder="X">
                                        <input type="number"
                                               class="corner-y"
                                               data-corner="br"
                                               placeholder="Y">
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="sidebar-section"
                             id="source-config-section"
                             style="display: none;">
                            <h3>Source Config</h3>
                            <div class="form-group">
                                <label>Window Size (px)</label>
                                <div class="size-input-row">
                                    <input type="number"
                                           id="window-width"
                                           placeholder="Width"
                                           min="1">
                                    <input type="number"
                                           id="window-height"
                                           placeholder="Height"
                                           min="1">
                                </div>
                            </div>
                            <div class="form-group">
                                <label>Render Size (px)</label>
                                <div class="size-input-row">
                                    <input type="number"
                                           id="render-width"
                                           placeholder="Width"
                                           min="1">
                                    <input type="number"
                                           id="render-height"
                                           placeholder="Height"
                                           min="1">
                                </div>
                            </div>
                            <div class="form-group">
                                <label>Crop Position (px)</label>
                                <div class="size-input-row">
                                    <input type="number"
                                           id="crop-x"
                                           placeholder="X"
                                           min="0">
                                    <input type="number"
                                           id="crop-y"
                                           placeholder="Y"
                                           min="0">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    this.updateSourcesList();
  }

  setupCanvas() {
    this.canvasElement = document.querySelector("#preview-canvas");

    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    // Canvas is exactly the virtual screen size
    this.canvasElement.width = w;
    this.canvasElement.height = h;
    this.canvasElement.style.width = `${w}px`;
    this.canvasElement.style.height = `${h}px`;

    // Set preview-sources to same size
    const sources = document.querySelector("#preview-sources");
    sources.style.width = `${w}px`;
    sources.style.height = `${h}px`;

    // Setup scaling to fit viewport
    this.updateVirtualScreenScale();

    this.renderPreview();

    // Update size inputs
    const sizeWidth = document.querySelector("#size-width");
    const sizeHeight = document.querySelector("#size-height");
    if (sizeWidth) sizeWidth.value = w;
    if (sizeHeight) sizeHeight.value = h;
  }

  updateVirtualScreenScale() {
    const canvas = this.canvasElement;
    const sources = document.querySelector("#preview-sources");
    const canvasArea = document.querySelector(".editor-canvas-area");

    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    // Calculate scale to fit viewport while
    // maintaining aspect ratio
    const viewportWidth = canvasArea.clientWidth;
    const viewportHeight = canvasArea.clientHeight;

    const scaleX = viewportWidth / w;
    const scaleY = viewportHeight / h;
    const scale = Math.min(scaleX, scaleY);

    // Apply scale to both canvas and sources
    const scaleStyle = `scale(${scale})`;
    canvas.style.transform = scaleStyle;
    canvas.style.transformOrigin = "0 0";
    sources.style.transform = scaleStyle;
    sources.style.transformOrigin = "0 0";
  }

  getCanvasPixel(event_) {
    const canvas = this.canvasElement;
    const rect = canvas.getBoundingClientRect();

    // Actual canvas resolution
    const canvasWidth = canvas.width;
    const canvasHeight = canvas.height;

    // Display size (affected by CSS transform)
    const displayWidth = rect.width;
    const displayHeight = rect.height;

    // Scale factors for coordinate conversion
    const scaleX = canvasWidth / displayWidth;
    const scaleY = canvasHeight / displayHeight;

    // Coordinates relative to canvas display area
    const clientX = event_.clientX - rect.left;
    const clientY = event_.clientY - rect.top;

    // Convert to canvas virtual coordinates
    const x = Math.floor(clientX * scaleX);
    const y = Math.floor(clientY * scaleY);

    return { x, y };
  }

  renderPreview() {
    const sourcesContainer = document.querySelector("#preview-sources");

    // Only clear and rebuild if sources changed
    if (Object.keys(this.previewWindows).length === 0) {
      sourcesContainer.innerHTML = "";
    }

    for (const source of this.data.sources) {
      if (!source.visible) continue;

      if (source.type === "iframe") {
        // Reuse existing window if present
        if (this.previewWindows[source.id]) {
          this.applyWindowTransform(this.previewWindows[source.id], source);
          continue;
        }

        const window_ = document.createElement("div");
        window_.className = "preview-window";
        window_.id = `window-${source.id}`;
        window_.dataset.sourceId = source.id;

        const container = document.createElement("div");
        container.className = "window-container";
        container.style.position = "relative";
        container.style.overflow = "hidden";

        const iframe = document.createElement("iframe");
        iframe.src = source.config.url;
        iframe.style.border = "none";
        iframe.style.pointerEvents = "none";
        iframe.style.display = "block";
        iframe.style.position = "absolute";
        iframe.style.top = "0";
        iframe.style.left = "0";

        iframe.sandbox.add("allow-same-origin", "allow-scripts",
          "allow-forms");

        container.append(iframe);
        window_.append(container);

        this.applyWindowTransform(window_, source);
        sourcesContainer.append(window_);
        this.previewWindows[source.id] = window_;
      }
    }

    // Auto-select first source if none selected
    if (!this.selectedSourceId && this.data.sources.length > 0) {
      this.selectSource(this.data.sources[0].id);
    }

    this.drawCornerHandles();
  }

  applyWindowTransform(element, source) {
    const config = source.config || {};
    const transform = source.transform || {};
    const corners = transform.corners;

    element.style.position = "absolute";

    // Apply window size
    const windowWidth = config.window_width || 800;
    const windowHeight = config.window_height || 600;
    element.style.width = `${windowWidth}px`;
    element.style.height = `${windowHeight}px`;

    // Apply window position (from corners if available)
    if (corners) {
      // Use top-left corner as position
      element.style.left = `${corners.tl.x}px`;
      element.style.top = `${corners.tl.y}px`;

      const matrix = this.calculatePerspectiveMatrix(corners,
        windowWidth, windowHeight);
      element.style.transformOrigin = "0 0";
      element.style.transform = `matrix3d(${matrix.join(",")})`;
    } else {
      element.style.left = "0";
      element.style.top = "0";
    }

    if (transform.opacity !== undefined) {
      element.style.opacity = transform.opacity.toString();
    }

    if (transform.blend_mode) {
      element.style.mixBlendMode = transform.blend_mode;
    }

    // Apply container sizing and cropping
    const container = element.querySelector(".window-container");
    if (container) {
      const renderWidth = config.render_width || windowWidth;
      const renderHeight = config.render_height || windowHeight;
      const cropX = config.crop_x || 0;
      const cropY = config.crop_y || 0;

      container.style.width = `${windowWidth}px`;
      container.style.height = `${windowHeight}px`;

      const iframe = container.querySelector("iframe");
      if (iframe) {
        iframe.style.width = `${renderWidth}px`;
        iframe.style.height = `${renderHeight}px`;
        iframe.style.left = `${-cropX}px`;
        iframe.style.top = `${-cropY}px`;
      }
    }
  }

  updatePreviewTransform(source) {
    // Smoothly update just the transform without recreating DOM
    if (!this.previewWindows[source.id]) return;

    const element = this.previewWindows[source.id];
    this.applyWindowTransform(element, source);
  }

  calculatePerspectiveMatrix(corners, windowWidth, windowHeight) {
    // Source is the window itself (0,0 to width, height)
    const sourceCorners = [0, 0, windowWidth, 0, 0, windowHeight,
      windowWidth, windowHeight];

    // Destination is relative to top-left corner (since the window
    // is positioned at corners.tl)
    const tlX = corners.tl.x;
    const tlY = corners.tl.y;
    const destinationCorners = [
      corners.tl.x - tlX,
      corners.tl.y - tlY,
      corners.tr.x - tlX,
      corners.tr.y - tlY,
      corners.bl.x - tlX,
      corners.bl.y - tlY,
      corners.br.x - tlX,
      corners.br.y - tlY,
    ];

    // Get perspective-transform from global scope
    const PerspT = globalThis.PerspT;
    const perspT = PerspT(sourceCorners, destinationCorners);

    // Get the coefficients matrix
    const coeffs = perspT.coeffs;

    // Convert 3x3 matrix to matrix3d format
    return this.coeffsToMatrix3d(coeffs);
  }

  coeffsToMatrix3d(coeffs) {
    // coeffs is a 9-element array:
    // [m00, m01, m02, m10, m11, m12, m20, m21, m22]
    // matrix3d format (column-major):
    // [a, d, 0, g,
    //  b, e, 0, h,
    //  0, 0, 1, 0,
    //  c, f, 0, i]
    const matrix = [
      coeffs[0],
      coeffs[3],
      0,
      coeffs[6],
      coeffs[1],
      coeffs[4],
      0,
      coeffs[7],
      0,
      0,
      1,
      0,
      coeffs[2],
      coeffs[5],
      0,
      coeffs[8],
    ];

    return matrix;
  }

  drawCornerHandles() {
    const canvas = this.canvasElement;
    if (!canvas) return;

    if (this.isViewerMode) {
      canvas.style.display = "none";
      return;
    }

    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);

    if (!this.selectedSourceId) return;

    const source = this.data.sources.find(
      (s) => s.id === this.selectedSourceId
    );
    if (!source || !source.transform?.corners) return;

    const corners = source.transform.corners;

    // Draw corner handles
    // Corners are already in canvas virtual coordinates
    const cornerKeys = ["tl", "tr", "bl", "br"];
    for (const key of cornerKeys) {
      const corner = corners[key];
      if (!corner) continue;

      context.fillStyle = "#00ff00";
      context.beginPath();
      context.arc(corner.x, corner.y, 30, 0, Math.PI * 2);
      context.fill();

      context.fillStyle = "#000";
      context.font = "12px Arial";
      context.fillText(key, corner.x + 15, corner.y + 15);
    }
  }

  setupEventListeners() {
    // Skip editor-specific listeners in viewer mode
    if (!this.isViewerMode) {
      // Save button
      document
        .querySelector("#save-btn")
        .addEventListener("click", () => this.save());

      // Add source button
      document
        .querySelector("#add-source-btn")
        .addEventListener("click", () => this.addSource());

      // Source config inputs
      document
        .querySelector("#window-width")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.config.window_width = Number.parseInt(
              event_.target.value
            );
            this.updatePreviewTransform(source);
          }
        });

      document
        .querySelector("#window-height")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.config.window_height = Number.parseInt(
              event_.target.value
            );
            this.updatePreviewTransform(source);
          }
        });

      document
        .querySelector("#render-width")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.config.render_width = Number.parseInt(
              event_.target.value
            );
            this.updatePreviewTransform(source);
          }
        });

      document
        .querySelector("#render-height")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.config.render_height = Number.parseInt(
              event_.target.value
            );
            this.updatePreviewTransform(source);
          }
        });

      document
        .querySelector("#crop-x")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.config.crop_x = Number.parseInt(event_.target.value);
            this.updatePreviewTransform(source);
          }
        });

      document
        .querySelector("#crop-y")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.config.crop_y = Number.parseInt(event_.target.value);
            this.updatePreviewTransform(source);
          }
        });

      // Size inputs
      document
        .querySelector("#size-width")
        ?.addEventListener("input", (event_) => {
          if (this.data.size === 0) {
            this.data.size = {};
          }
          this.data.size.width = Number.parseInt(event_.target.value);
          this.canvasElement.width = this.data.size.width;
          this.canvasElement.style.width = `${this.data.size.width}px`;
          const sources = document.querySelector("#preview-sources");
          sources.style.width = `${this.data.size.width}px`;
          this.updateVirtualScreenScale();
          this.renderPreview();
        });

      document
        .querySelector("#size-height")
        ?.addEventListener("input", (event_) => {
          if (this.data.size === 0) {
            this.data.size = {};
          }
          this.data.size.height = Number.parseInt(event_.target.value);
          this.canvasElement.height = this.data.size.height;
          this.canvasElement.style.height = `${this.data.size.height}px`;
          const sources = document.querySelector("#preview-sources");
          sources.style.height = `${this.data.size.height}px`;
          this.updateVirtualScreenScale();
          this.renderPreview();
        });

      // Transform controls
      document
        .querySelector("#opacity")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.transform.opacity = Number.parseFloat(event_.target.value);
            document.querySelector("#opacity-val").textContent =
              Number.parseFloat(event_.target.value).toFixed(2);
            this.renderPreview();
          }
        });

      document
        .querySelector("#blend-mode")
        ?.addEventListener("change", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.transform.blend_mode = event_.target.value;
            this.renderPreview();
          }
        });

      document
        .querySelector("#rotation")
        ?.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            source.transform.rotation = Number.parseInt(event_.target.value);
            this.renderPreview();
          }
        });

      // Corner inputs
      for (const input of document.querySelectorAll(
        "input.corner-x, input.corner-y"
      )) {
        input.addEventListener("input", (event_) => {
          const source = this.getSelectedSource();
          if (source) {
            const corner = event_.target.dataset.corner;
            const isX = event_.target.className.includes("corner-x");

            if (!source.transform.corners) {
              source.transform.corners = this.getDefaultCorners();
            }

            if (isX) {
              source.transform.corners[corner].x = Number.parseFloat(
                event_.target.value
              );
            } else {
              source.transform.corners[corner].y = Number.parseFloat(
                event_.target.value
              );
            }

            this.broadcastTransform(source);
            this.updatePreviewTransform(source);
            this.drawCornerHandles();
          }
        });
      }
    }

    // Canvas interactions (always available)
    this.canvasElement.addEventListener("mousedown", (event_) =>
      this.onCanvasMouseDown(event_)
    );
    this.canvasElement.addEventListener("mousemove", (event_) =>
      this.onCanvasMouseMove(event_)
    );
    this.canvasElement.addEventListener("mouseup", () =>
      this.onCanvasMouseUp()
    );

    this.canvasElement.addEventListener("mouseleave", () =>
      this.onCanvasMouseUp()
    );

    // Touch events
    this.canvasElement.addEventListener("touchstart", (event_) =>
      this.onCanvasTouchStart(event_)
    );
    this.canvasElement.addEventListener("touchmove", (event_) =>
      this.onCanvasTouchMove(event_)
    );
    this.canvasElement.addEventListener("touchend", () =>
      this.onCanvasTouchEnd()
    );
  }

  onCanvasMouseDown(event_) {
    this.isDragging = true;
    this.checkCornerClick(event_);
  }

  onCanvasMouseMove(event_) {
    if (!this.isDragging || !this.draggingCorner) return;

    const source = this.getSelectedSource();
    if (!source || !source.transform?.corners) return;

    const { x, y } = this.getCanvasPixel(event_);

    source.transform.corners[this.draggingCorner] = { x, y };

    this.broadcastTransform(source);
    this.updatePreviewTransform(source);
    this.updateTransformInputs();
    this.drawCornerHandles();
  }

  onCanvasMouseUp() {
    if (!this.isDragging) return;
    this.isDragging = false;
    this.draggingCorner = null;
    const source = this.getSelectedSource();

    this.broadcastTransform(source, true);
  }

  onCanvasTouchStart(event_) {
    const touch = event_.touches[0];
    const mouseEvent = new MouseEvent("mousedown", {
      clientX: touch.clientX,
      clientY: touch.clientY,
    });
    this.canvasElement.dispatchEvent(mouseEvent);
  }

  onCanvasTouchMove(event_) {
    event_.preventDefault();
    const touch = event_.touches[0];
    const mouseEvent = new MouseEvent("mousemove", {
      clientX: touch.clientX,
      clientY: touch.clientY,
    });
    this.canvasElement.dispatchEvent(mouseEvent);
  }

  onCanvasTouchEnd() {
    const mouseEvent = new MouseEvent("mouseup");
    this.canvasElement.dispatchEvent(mouseEvent);
  }

  checkCornerClick(event_) {
    const source = this.getSelectedSource();
    if (!source || !source.transform?.corners) return;

    const { x, y } = this.getCanvasPixel(event_);

    const corners = source.transform.corners;
    const hitRadius = 30;

    for (const [key, corner] of Object.entries(corners)) {
      const distribution = Math.hypot(x - corner.x, y - corner.y);
      if (distribution < hitRadius) {
        this.draggingCorner = key;
        return;
      }
    }
  }

  broadcastTransform(source, force = false) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    if (Date.now() - this.broadcastRateLimitTime < 60 && !force) {
      return;
    }
    this.broadcastRateLimitTime = Date.now();
    this.ws.send(
      JSON.stringify({
        source_id: source.id,
        corners: source.transform.corners,
      })
    );
  }

  setupWebSocket() {
    const protocol = globalThis.location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(
      `${protocol}://${globalThis.location.host}` +
        `/projection-mapper/ws/${this.module}/${this.resource}`
    );

    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if(message.type === "refresh_page") {
        // eslint-disable-next-line unicorn/prefer-global-this
        window.location.reload();
      }
      if (message.type === "transform_update") {
        const source = this.data.sources.find(
          (s) => s.id === message.source_id
        );
        if (
          source &&
          !(this.isDragging && this.selectedSourceId === source.id)
        ) {
          source.transform.corners = message.corners;
          this.renderPreview();
          this.updateTransformInputs();
        }
      }
    });
  }

  updateSourcesList() {
    const list = document.querySelector("#sources-list");
    if (!list) return;

    list.innerHTML = "";

    for (const source of this.data.sources) {
      const item = document.createElement("div");
      item.className = "source-item";
      if (source.id === this.selectedSourceId) {
        item.classList.add("selected");
      }

      item.innerHTML = `
                <div class="source-item-content">
                    <span>${source.name}</span>
                    <button class="btn-small del-source">
                        Delete
                    </button>
                </div>
            `;

      item.addEventListener("click", () => {
        this.selectSource(source.id);
      });

      item.querySelector(".del-source")?.addEventListener("click", (e) => {
        e.stopPropagation();
        this.deleteSource(source.id);
      });

      list.append(item);
    }
  }

  updateSourceConfigInputs() {
    const source = this.getSelectedSource();
    if (!source) return;

    const config = source.config || {};
    const windowWidthInput = document.querySelector("#window-width");
    const windowHeightInput = document.querySelector("#window-height");
    const renderWidthInput = document.querySelector("#render-width");
    const renderHeightInput = document.querySelector("#render-height");
    const cropXInput = document.querySelector("#crop-x");
    const cropYInput = document.querySelector("#crop-y");

    if (windowWidthInput) windowWidthInput.value = config.window_width || 800;
    if (windowHeightInput) windowHeightInput.value = config.window_height || 600;
    if (renderWidthInput) renderWidthInput.value = config.render_width || 800;
    if (renderHeightInput) renderHeightInput.value = config.render_height || 600;
    if (cropXInput) cropXInput.value = config.crop_x || 0;
    if (cropYInput) cropYInput.value = config.crop_y || 0;
  }

  selectSource(sourceId) {
    this.selectedSourceId = sourceId;
    this.updateSourcesList();
    this.updateTransformInputs();
    this.updateSourceConfigInputs();

    const transformSection = document.querySelector("#transform-section");
    const configSection = document.querySelector("#source-config-section");

    if (transformSection) transformSection.style.display = "block";
    if (configSection) configSection.style.display = "block";

    this.renderPreview();
  }

  getSelectedSource() {
    return this.data.sources.find((s) => s.id === this.selectedSourceId);
  }

  updateTransformInputs() {
    const source = this.getSelectedSource();
    if (!source) return;

    const transform = source.transform || {};

    const opacitySlider = document.querySelector("#opacity");
    if (opacitySlider) {
      opacitySlider.value = transform.opacity ?? 1;
      document.querySelector("#opacity-val").textContent = (
        transform.opacity ?? 1
      ).toFixed(2);
    }

    const blendSelect = document.querySelector("#blend-mode");
    if (blendSelect) {
      blendSelect.value = transform.blend_mode ?? "normal";
    }

    const rotationInput = document.querySelector("#rotation");
    if (rotationInput) {
      rotationInput.value = transform.rotation ?? 0;
    }

    if (transform.corners) {
      const cornerKeys = ["tl", "tr", "bl", "br"];
      for (const key of cornerKeys) {
        const corner = transform.corners[key];
        const xInputs = document.querySelectorAll(
          `input.corner-x[data-corner="${key}"]`
        );
        const yInputs = document.querySelectorAll(
          `input.corner-y[data-corner="${key}"]`
        );

        if (xInputs[0]) {
          xInputs[0].value = corner.x;
        }
        if (yInputs[0]) {
          yInputs[0].value = corner.y;
        }
      }
    }
  }

  getDefaultCorners() {
    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    return {
      tl: { x: 0, y: 0 },
      tr: { x: w, y: 0 },
      bl: { x: 0, y: h },
      br: { x: w, y: h },
    };
  }

  addSource() {
    const name = prompt("Source name:");
    if (!name) return;

    const url = prompt("URL:");
    if (!url) return;

    const source = {
      id: this.generateId(),
      name,
      type: "iframe",
      config: {
        url,
        window_width: 800,
        window_height: 600,
        render_width: 800,
        render_height: 600,
        crop_x: 0,
        crop_y: 0,
      },
      transform: {
        corners: this.getDefaultCorners(),
        opacity: 1,
        blend_mode: "normal",
        rotation: 0,
      },
      visible: true,
    };

    this.data.sources.push(source);
    this.selectSource(source.id);
    this.updateSourcesList();
    this.renderPreview();
  }

  deleteSource(sourceId) {
    this.data.sources = this.data.sources.filter((s) => s.id !== sourceId);

    if (this.selectedSourceId === sourceId) {
      this.selectedSourceId = null;
      document.querySelector("#transform-section").style.display = "none";
      document.querySelector("#source-config-section").style.display = "none";
    }

    this.updateSourcesList();
    this.renderPreview();
  }

  async save() {
    try {
      // Ensure size is set
      if (this.data.size === 0) {
        this.data.size = {
          width: 1920,
          height: 1080,
        };
      }

      const response = await fetch(
        `/projection-mapper/api/save/${this.module}/${this.resource}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(this.data),
        }
      );

      if (response.ok) {
        await response.json();
        alert("Saved successfully");

        // Broadcast reload to viewers
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(
            JSON.stringify({
              type: "reload",
            })
          );
        }
      } else {
        const errorData = await response.json();
        alert("Save failed: " + (errorData.message || "Unknown error"));
      }
    } catch (error) {
      console.error("Save error:", error);
      alert("Save failed: " + error.message);
    }
  }

  generateId() {
    return "src_" + Math.random().toString(36).slice(2, 11);
  }
}

export default ProjectionEditor;
