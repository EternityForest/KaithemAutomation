// Projection Mapper Editor
// Real-time collaborative editing with WebSocket sync

import { VFX } from "/static/js/thirdparty/vfx-js/vfx.esm.js";

const EFFECT_SCHEMAS = {
  glitch: {
    type: "object",
    title: "Glitch Effect",
    properties: {
      amount: {
        type: "number",
        title: "Amount",
        default: 0.05,
        minimum: 0,
        maximum: 1,
        description: "Intensity of glitch lines",
      },
    },
  },
  crt: {
    type: "object",
    title: "CRT Scanlines",
    properties: {
      intensity: {
        type: "number",
        title: "Intensity",
        default: 0.15,
        minimum: 0,
        maximum: 1,
        description: "Darkness of scanlines",
      },
      lineWidth: {
        type: "number",
        title: "Line Width",
        default: 2,
        minimum: 1,
        maximum: 10,
        description: "Pixels between scanlines",
      },
    },
  },
  film_grain: {
    type: "object",
    title: "Film Grain",
    properties: {
      intensity: {
        type: "number",
        title: "Intensity",
        default: 0.1,
        minimum: 0,
        maximum: 1,
        description: "Amount of noise",
      },
    },
  },
  rgb_shift: {
    type: "object",
    title: "RGB Shift",
    properties: {
      offset: {
        type: "number",
        title: "Offset",
        default: 3,
        minimum: 0,
        maximum: 20,
        description: "Pixel offset for color channels",
      },
    },
  },
  kaleidoscope: {
    type: "object",
    title: "Kaleidoscope",
    properties: {
      segments: {
        type: "number",
        title: "Segments",
        default: 6,
        minimum: 3,
        maximum: 12,
        description: "Number of symmetry segments",
      },
    },
  },
  pixelate: {
    type: "object",
    title: "Pixelate",
    properties: {
      pixelSize: {
        type: "number",
        title: "Pixel Size",
        default: 5,
        minimum: 1,
        maximum: 50,
        description: "Size of pixelation blocks",
      },
    },
  },
};

const EFFECT_NAMES = {
  glitch: "Glitch",
  crt: "CRT Scanlines",
  film_grain: "Film Grain",
  rgb_shift: "RGB Shift",
  kaleidoscope: "Kaleidoscope",
  pixelate: "Pixelate",
};

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
    this.previewIframes = {};
    this.currentScale = 1;
    this.effectEditors = {};
    this.renderCanvases = {};
    this.vfxInstances = {};

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
    this.container.innerHTML = `
            <div class="projection-editor">
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
                             id="vfx-section"
                             style="display: none;">
                            <h3>VFX Effects</h3>
                            <div class="form-group">
                                <label>Effect Type</label>
                                <select id="effect-type-select">
                                    <option value="glitch">
                                        Glitch
                                    </option>
                                    <option value="crt">
                                        CRT Scanlines
                                    </option>
                                    <option value="film_grain">
                                        Film Grain
                                    </option>
                                    <option value="rgb_shift">
                                        RGB Shift
                                    </option>
                                    <option value="kaleidoscope">
                                        Kaleidoscope
                                    </option>
                                    <option value="pixelate">
                                        Pixelate
                                    </option>
                                </select>
                            </div>
                            <button id="add-effect-btn"
                                    class="btn btn-sm">
                                + Add Effect
                            </button>
                            <div id="effects-list"
                                 class="effects-list">
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

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
    if (Object.keys(this.previewIframes).length === 0) {
      sourcesContainer.innerHTML = "";
    }

    for (const source of this.data.sources) {
      if (!source.visible) continue;

      if (source.type === "iframe") {
        // Reuse existing wrapper if present
        if (this.previewIframes[source.id]) {
          this.applyPreviewTransform(this.previewIframes[source.id], source);
          this.applySourceEffects(source);
          continue;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "preview-source";
        wrapper.id = `source-${source.id}`;
        wrapper.dataset.sourceId = source.id;

        const iframe = document.createElement("iframe");
        iframe.src = source.config.url;
        iframe.style.border = "none";
        iframe.style.pointerEvents = "none";
        iframe.style.width = "100%";
        iframe.style.height = "100%";
        iframe.style.display = "block";
        iframe.sandbox.add("allow-same-origin", "allow-scripts", "allow-forms");

        // Re-render effects when iframe loads
        iframe.addEventListener("load", () => {
          this.applySourceEffects(source);
        });

        wrapper.append(iframe);

        this.applyPreviewTransform(wrapper, source);
        this.applySourceEffects(source);
        sourcesContainer.append(wrapper);
        this.previewIframes[source.id] = wrapper;
      }
    }

    // Auto-select first source if none selected
    if (!this.selectedSourceId && this.data.sources.length > 0) {
      this.selectSource(this.data.sources[0].id);
    }

    this.drawCornerHandles();
  }

  applyPreviewTransform(element, source) {
    const transform = source.transform || {};
    const corners = transform.corners;

    element.style.position = "absolute";

    if (corners) {
      element.style.width = "100%";
      element.style.height = "100%";
      element.style.top = "0";
      element.style.left = "0";

      const matrix = this.calculatePerspectiveMatrix(corners);
      element.style.transformOrigin = "0 0";
      element.style.transform = `matrix3d(${matrix.join(",")})`;
    } else {
      element.style.top = "0";
      element.style.left = "0";
      element.style.width = "100%";
      element.style.height = "100%";
    }

    if (transform.opacity !== undefined) {
      element.style.opacity = transform.opacity.toString();
    }

    if (transform.blend_mode) {
      element.style.mixBlendMode = transform.blend_mode;
    }

    if (transform.rotation && corners) {
      const matrix = this.calculatePerspectiveMatrix(corners);
      element.style.transform =
        `matrix3d(${matrix.join(",")})` + ` rotate(${transform.rotation}deg)`;
    } else if (transform.rotation && !corners) {
      element.style.transform = `rotate(${transform.rotation}deg)`;
    }
  }

  updatePreviewTransform(source) {
    // Smoothly update just the transform without
    // recreating DOM
    if (!this.previewIframes[source.id]) return;

    const element = this.previewIframes[source.id];
    this.applyPreviewTransform(element, source);
    this.applySourceEffects(source);
  }

  applySourceEffects(source) {
    // Apply VFX effects to iframe content
    if (!source.vfx || source.vfx.length === 0) {
      return;
    }

    const wrapper = this.previewIframes[source.id];
    if (!wrapper) return;

    const iframe = wrapper.querySelector("iframe");
    if (!iframe || !iframe.contentDocument) return;

    // Create or reuse render canvas
    let renderCanvas = this.renderCanvases[source.id];
    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    if (!renderCanvas) {
      renderCanvas = document.createElement("canvas");
      renderCanvas.width = w;
      renderCanvas.height = h;
      renderCanvas.style.position = "absolute";
      renderCanvas.style.top = "0";
      renderCanvas.style.left = "0";
      renderCanvas.style.pointerEvents = "none";
      renderCanvas.style.width = "100%";
      renderCanvas.style.height = "100%";
      wrapper.append(renderCanvas);
      this.renderCanvases[source.id] = renderCanvas;
    }

    // Draw iframe content to canvas
    const context = renderCanvas.getContext("2d");
    try {
      context.drawImage(iframe, 0, 0);
    } catch {
      // CORS or other errors silently continue
      return;
    }

    // Create or reuse VFX instance and apply effects
    let vfx = this.vfxInstances[source.id];
    if (!vfx) {
      vfx = new VFX(renderCanvas);
      this.vfxInstances[source.id] = vfx;
    }

    // Clear previous effects and add new ones
    vfx.effects = [];
    for (const effect of source.vfx) {
      vfx.addEffect(effect.shader, effect.params);
    }

    // Apply all effects to canvas
    vfx.apply();
  }

  calculatePerspectiveMatrix(corners) {
    // Get projection size
    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    // Use perspective-transform library
    // Source is the full virtual screen (where iframe content comes from)
    const sourceCorners = [0, 0, w, 0, 0, h, w, h];

    // Destination is where user has positioned the corners
    const destinationCorners = [
      corners.tl.x,
      corners.tl.y,
      corners.tr.x,
      corners.tr.y,
      corners.bl.x,
      corners.bl.y,
      corners.br.x,
      corners.br.y,
    ];

    // Get perspective-transform from global scope
    // It was loaded as a non-module script
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
    // Save button
    document
      .querySelector("#save-btn")
      .addEventListener("click", () => this.save());

    // Add source button
    document
      .querySelector("#add-source-btn")
      .addEventListener("click", () => this.addSource());

    // Add effect button
    const addEffectButton = document.querySelector("#add-effect-btn");
    if (addEffectButton) {
      addEffectButton.addEventListener("click", () => this.addEffect());
    }

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

    // Canvas dragging
    this.canvasElement.addEventListener("mousedown", (e) =>
      this.onCanvasMouseDown(e)
    );
    this.canvasElement.addEventListener("mousemove", (e) =>
      this.onCanvasMouseMove(e)
    );
    this.canvasElement.addEventListener("mouseup", () =>
      this.onCanvasMouseUp()
    );

    // Touch events
    this.canvasElement.addEventListener("touchstart", (e) =>
      this.onCanvasTouchStart(e)
    );
    this.canvasElement.addEventListener("touchmove", (e) =>
      this.onCanvasTouchMove(e)
    );
    this.canvasElement.addEventListener("touchend", () =>
      this.onCanvasTouchEnd()
    );

    // Transform controls
    document.querySelector("#opacity")?.addEventListener("input", (e) => {
      const source = this.getSelectedSource();
      if (source) {
        source.transform.opacity = Number.parseFloat(e.target.value);
        document.querySelector("#opacity-val").textContent = Number.parseFloat(
          e.target.value
        ).toFixed(2);
        this.renderPreview();
      }
    });

    document.querySelector("#blend-mode")?.addEventListener("change", (e) => {
      const source = this.getSelectedSource();
      if (source) {
        source.transform.blend_mode = e.target.value;
        this.renderPreview();
      }
    });

    document.querySelector("#rotation")?.addEventListener("input", (e) => {
      const source = this.getSelectedSource();
      if (source) {
        source.transform.rotation = Number.parseInt(e.target.value);
        this.renderPreview();
      }
    });

    // Corner inputs
    for (const input of document.querySelectorAll(
      "input.corner-x, input.corner-y"
    )) {
      input.addEventListener("input", (e) => {
        const source = this.getSelectedSource();
        if (source) {
          const corner = e.target.dataset.corner;
          const isX = e.target.className.includes("corner-x");

          if (!source.transform.corners) {
            source.transform.corners = this.getDefaultCorners();
          }

          if (isX) {
            source.transform.corners[corner].x = Number.parseFloat(
              e.target.value
            );
          } else {
            source.transform.corners[corner].y = Number.parseFloat(
              e.target.value
            );
          }

          this.broadcastTransform(source);
          this.updatePreviewTransform(source);
          this.drawCornerHandles();
        }
      });
    }
  }

  onCanvasMouseDown(e) {
    this.isDragging = true;
    this.checkCornerClick(e);
  }

  onCanvasMouseMove(e) {
    if (!this.isDragging || !this.draggingCorner) return;

    const source = this.getSelectedSource();
    if (!source || !source.transform?.corners) return;

    const { x, y } = this.getCanvasPixel(e);

    source.transform.corners[this.draggingCorner] = { x, y };

    this.broadcastTransform(source);
    this.updatePreviewTransform(source);
    this.updateTransformInputs();
    this.drawCornerHandles();
  }

  onCanvasMouseUp() {
    this.isDragging = false;
    this.draggingCorner = null;
  }

  onCanvasTouchStart(e) {
    const touch = e.touches[0];
    const mouseEvent = new MouseEvent("mousedown", {
      clientX: touch.clientX,
      clientY: touch.clientY,
    });
    this.canvasElement.dispatchEvent(mouseEvent);
  }

  onCanvasTouchMove(e) {
    e.preventDefault();
    const touch = e.touches[0];
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

  checkCornerClick(e) {
    const source = this.getSelectedSource();
    if (!source || !source.transform?.corners) return;

    const { x, y } = this.getCanvasPixel(e);

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

  broadcastTransform(source) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

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
      if (message.type === "transform_update") {
        const source = this.data.sources.find(
          (s) => s.id === message.source_id
        );
        if (source) {
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

  updateEffectsList() {
    const list = document.querySelector("#effects-list");
    if (!list) return;

    const source = this.getSelectedSource();
    if (!source) return;

    list.innerHTML = "";

    const effects = source.vfx || [];
    for (const [index, effect] of effects.entries()) {
      const item = document.createElement("div");
      item.className = "effect-item";

      const header = document.createElement("div");
      header.className = "effect-item-header";
      header.innerHTML = `
                <strong>
                    ${EFFECT_NAMES[effect.shader]}
                </strong>
                <button class="btn-small del-effect"
                        data-effect-index="${index}">
                    Delete
                </button>
            `;

      item.append(header);

      const parametersContainer = document.createElement("div");
      parametersContainer.className = "effect-params-container";
      parametersContainer.id = `effect-params-${source.id}-${index}`;
      item.append(parametersContainer);

      list.append(item);

      // Create JSONEditor for this effect
      const editorKey = `${source.id}_${index}`;
      if (this.effectEditors[editorKey]) {
        this.effectEditors[editorKey].destroy();
      }

      const schema = EFFECT_SCHEMAS[effect.shader];
      this.effectEditors[editorKey] = new globalThis.JSONEditor(
        parametersContainer,
        {
          schema: schema,
          startval: effect.params,
          disable_collapse: true,
          disable_edit_json: true,
          theme: "barebones",
        }
      );

      // Update effect params when editor changes
      this.effectEditors[editorKey].on("change", () => {
        effect.params = this.effectEditors[editorKey].getValue();
        // Re-render preview with new params
        this.applySourceEffects(source);
      });

      // Add delete button listener
      header
        .querySelector(".del-effect")
        ?.addEventListener("click", (event_) => {
          event_.stopPropagation();
          this.deleteEffect(index);
        });
    }
  }

  selectSource(sourceId) {
    this.selectedSourceId = sourceId;
    this.updateSourcesList();
    this.updateTransformInputs();
    this.updateEffectsList();

    const transformSection = document.querySelector("#transform-section");
    const vfxSection = document.querySelector("#vfx-section");

    if (transformSection) transformSection.style.display = "block";
    if (vfxSection) vfxSection.style.display = "block";

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
      config: { url },
      transform: {
        corners: this.getDefaultCorners(),
        opacity: 1,
        blend_mode: "normal",
        rotation: 0,
      },
      vfx: [],
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
      document.querySelector("#vfx-section").style.display = "none";
    }

    this.updateSourcesList();
    this.renderPreview();
  }

  addEffect() {
    const source = this.getSelectedSource();
    if (!source) return;

    const effectType = document.querySelector("#effect-type-select")?.value;
    if (!effectType) return;

    if (!source.vfx) source.vfx = [];

    // Get default params from schema
    const schema = EFFECT_SCHEMAS[effectType];
    const parameters = {};
    for (const [key, property] of Object.entries(schema.properties)) {
      parameters[key] = property.default;
    }

    source.vfx.push({
      shader: effectType,
      params: parameters,
    });

    this.updateEffectsList();
  }

  deleteEffect(effectIndex) {
    const source = this.getSelectedSource();
    if (!source || !source.vfx) return;

    // Destroy editor instance
    const editorKey = `${source.id}_${effectIndex}`;
    if (this.effectEditors[editorKey]) {
      this.effectEditors[editorKey].destroy();
      delete this.effectEditors[editorKey];
    }

    source.vfx.splice(effectIndex, 1);
    this.updateEffectsList();
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
