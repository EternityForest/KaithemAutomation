// Projection Mapper Editor
// Real-time collaborative editing with WebSocket sync
// Uses CSS perspective transforms instead of VFX for cross-browser
// compatibility
// Built with Lit for lightweight, self-contained rendering

import { LitElement, html, css } from "lit";
import { kaithemapi } from "/static/js/widget.mjs";
import { PerspT } from "./perspective-transform.mjs";
import { createSourceAdapter } from "./source-type";
import type {
  Position,
  Corners,
  SourceConfig,
  SourceTransform,
  SourceData,
  Source,
} from "./source-type";
import "./iframe-source";
import "./clock-source";
import "./tag-source";

interface ProjectionData {
  title: string;
  size: { width: number; height: number };
  sources: SourceData[];
}

class PositionFilter {
  timeConstant: number;
  currentPos: Position | null = null;
  targetPos: Position | null = null;
  lastUpdateTime: number | null = null;
  instantThresholdMm = 5;

  constructor(timeConstant = 5) {
    this.timeConstant = timeConstant;
  }

  // Convert mm to pixels (assume 96 DPI standard)
  mmToPixels(mm: number): number {
    return (mm / 25.4) * 96;
  }

  update(targetX: number, targetY: number, timestamp = Date.now()): Position {
    // Initialize on first call
    if (this.currentPos === null) {
      this.currentPos = { x: targetX, y: targetY };
      this.targetPos = { x: targetX, y: targetY };
      this.lastUpdateTime = timestamp;
      return this.currentPos;
    }

    // Calculate distance from current to target
    const dx = targetX - this.currentPos.x;
    const dy = targetY - this.currentPos.y;
    const distancePixels = Math.hypot(dx, dy);
    const thresholdPixels = this.mmToPixels(this.instantThresholdMm);

    const inputDx = targetX - this.targetPos!.x;
    const inputDy = targetY - this.targetPos!.y;

    // If movement >= 5mm: instant response,
    // simulate dragging with a string,
    // get a movement vector, subtract threshhold from magnitude
    if (distancePixels >= thresholdPixels) {
      let moveVector = Math.hypot(inputDx, inputDy);
      moveVector = moveVector - thresholdPixels;
      const moveX = moveVector * (inputDx / moveVector);
      const moveY = moveVector * (inputDy / moveVector);

      this.currentPos = {
        x: this.currentPos.x + moveX,
        y: this.currentPos.y + moveY,
      };
      this.targetPos = { x: targetX, y: targetY };
      this.lastUpdateTime = timestamp;
      return this.currentPos;
    }

    // If movement < 5mm: apply first-order lowpass
    this.targetPos = { x: targetX, y: targetY };

    const dt = (timestamp - this.lastUpdateTime!) / 1000; // seconds
    this.lastUpdateTime = timestamp;

    // First-order lowpass: y[n] = y[n-1] + (dt / tau) * (x[n] - y[n-1])
    const alpha = dt / this.timeConstant;

    this.currentPos.x += alpha * (this.targetPos.x - this.currentPos.x);
    this.currentPos.y += alpha * (this.targetPos.y - this.currentPos.y);

    // Converge to target if within 1 pixel
    const remainingDistribution = Math.sqrt(
      Math.pow(this.targetPos.x - this.currentPos.x, 2) +
        Math.pow(this.targetPos.y - this.currentPos.y, 2)
    );
    if (remainingDistribution < 1) {
      this.currentPos.x = this.targetPos.x;
      this.currentPos.y = this.targetPos.y;
    }

    return this.currentPos;
  }

  reset(): void {
    this.currentPos = null;
    this.targetPos = null;
    this.lastUpdateTime = null;
  }
}

class ProjectionEditor extends LitElement {
  static override styles = css`
    /* Projection Mapper Styles */

    body {
      margin: 0;
      padding: 0;
    }

    .viewer-mode {
      cursor: none;
    }

    .projection-editor {
      display: flex;
      flex-direction: column;
      width: 100%;
      height: 100vh;
      background: #1a1a1a;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        sans-serif;
      user-select: none;
      -webkit-user-select: none;
    }

    .editor-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.3rem;
      background: #000;
      border-bottom: 1px solid #333;
    }

    .editor-toolbar h2 {
      margin: 0;
      font-size: 1rem;
    }

    .editor-main {
      display: flex;
      flex: 1;
      gap: 1px;
      overflow: hidden;
      background: #333;
    }

    .editor-canvas-area {
      flex: 1;
      position: relative;
      background: #333;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }

    .editor-canvas-area.viewer-mode {
      background-color: #000;
    }

    #preview-canvas {
      position: absolute;
      top: 0;
      left: 0;
      background: transparent;
      border: 4px dashed #333;
      cursor: crosshair;
      pointer-events: auto;
      z-index: 50;
      opacity: 0.8;
    }

    #preview-sources {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      background: black;
    }

    .preview-window {
      position: absolute;
    }

    .window-container {
      position: relative;
      overflow: hidden;
    }

    .editor-sidebar {
      width: 300px;
      background: #1a1a1a;
      border-left: 1px solid #333;
      overflow-y: auto;
      padding: 1rem;
    }

    .sidebar-section {
      margin-bottom: 2rem;
    }

    .sidebar-section h3 {
      margin: 0 0 1rem 0;
      font-size: 1rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #aaa;
    }

    .sidebar-section h4 {
      margin: 1rem 0 0.5rem 0;
      font-size: 0.9rem;
      color: #999;
    }

    .btn {
      padding: 0.5rem 1rem;
      background: #2a90db;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 500;
      transition: background 0.2s;
    }

    .btn:hover {
      background: #1e6db3;
    }

    .btn-primary {
      background: #27ae60;
    }

    .btn-primary:hover {
      background: #229954;
    }

    .btn-small {
      padding: 0.25rem 0.5rem;
      font-size: 0.8rem;
    }

    .btn-sm {
      display: block;
      width: 100%;
      margin-bottom: 1rem;
    }

    .sources-list {
      margin: 1rem 0;
    }

    .source-item {
      padding: 0.75rem;
      margin-bottom: 0.5rem;
      background: #222;
      border: 2px solid #333;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .source-item:hover {
      background: #2a2a2a;
      border-color: #444;
    }

    .source-item.selected {
      background: #1e3a5f;
      border-color: #2a90db;
    }

    .source-item-content {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .del-source {
      background: #c74a42;
      color: white;
      border: none;
      padding: 0.25rem 0.5rem;
      border-radius: 3px;
      cursor: pointer;
      font-size: 0.75rem;
    }

    .del-source:hover {
      background: #a63d37;
    }

    .form-group {
      margin-bottom: 1rem;
    }

    .form-group label {
      display: block;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
      font-weight: 500;
    }

    .form-group input,
    .form-group select {
      width: 96%;
      padding: 0.5rem;
      background: #222;
      border: 1px solid #333;
      border-radius: 4px;
      color: #fff;
      font-size: 0.9rem;
    }

    .size-input-row {
      display: flex;
      gap: 0.5rem;
    }

    .size-input-row input {
      flex: 1;
      padding: 0.5rem;
      background: #222;
      border: 1px solid #333;
      border-radius: 4px;
      color: #fff;
      font-size: 0.9rem;
    }

    .form-group input[type="range"]:focus,
    .form-group input[type="number"]:focus,
    .form-group select:focus {
      outline: none;
      border-color: #2a90db;
      background: #2a2a2a;
    }

    .form-group span {
      display: inline-block;
      margin-left: 0.5rem;
      color: #aaa;
      font-size: 0.9rem;
    }

    .corners-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      margin-top: 1rem;
    }

    .corners-grid > div {
      padding: 0.75rem;
      background: #222;
      border: 1px solid #333;
      border-radius: 4px;
    }

    .corners-grid label {
      font-size: 0.8rem;
      margin-bottom: 0.5rem;
    }

    .corners-grid input {
      width: 100%;
      padding: 0.4rem;
      margin-bottom: 0.4rem;
      background: #1a1a1a;
      border: 1px solid #333;
      border-radius: 3px;
      color: #fff;
      font-size: 0.8rem;
    }

    .effects-list {
      margin: 1rem 0;
    }

    .effect-item {
      padding: 0.75rem;
      margin-bottom: 0.5rem;
      background: #222;
      border: 1px solid #333;
      border-radius: 4px;
    }

    .effect-item-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
    }

    .effect-item-header strong {
      font-size: 0.9rem;
    }

    /* Responsive */
    @media (max-width: 768px) {
      .editor-main {
        flex-direction: column;
      }

      .editor-sidebar {
        width: 100%;
        border-left: none;
        border-top: 1px solid #333;
        max-height: 40vh;
      }

      .editor-canvas-area {
        flex: 1;
        min-height: 60vh;
      }

      .btn-sm {
        width: auto;
      }

      .corners-grid {
        grid-template-columns: 1fr;
      }
    }
  `;

  module: string = "";
  resource: string = "";

  canvasElement?: HTMLCanvasElement;

  sourceObjects: { [key: string]: Source } = {};

  data: ProjectionData = {
    title: "",
    sources: [],
    size: { width: 1920, height: 1080 },
  };
  selectedSourceId: string | null = null;
  isDragging = false;
  draggingCorner: string | null = null;
  isViewerMode = false;

  private ws: WebSocket | null = null;
  private previewWindows: Record<string, HTMLElement> = {};
  private currentScale = 1;
  private broadcastRateLimitTime = 0;

  // Position filters for each corner
  private cornerFilters = {
    tl: new PositionFilter(3),
    tr: new PositionFilter(3),
    bl: new PositionFilter(3),
    br: new PositionFilter(3),
  };

  private animationFrameId: number | null = null;
  private lastRawMousePos: Position | null = null;

  // Tag subscriptions per source: sourceId -> { tagKey -> { tag, callback } }
  private tagSubscriptions: Record<
    string,
    Record<string, { tag: string; callback: (value: number) => void }>
  > = {};

  override connectedCallback(): void {
    super.connectedCallback();

    // Parse URL params for mode
    const parameters = new URLSearchParams(globalThis.location.search);
    this.isViewerMode =
      parameters.has("fullscreen") ||
      parameters.has("viewer") ||
      parameters.get("edit") != "true";
  }

  setInitialState(
    module: string,
    resource: string,
    initialData: ProjectionData
  ): void {
    this.module = module;
    this.resource = resource;

    this.data = structuredClone(initialData);
    if (this.data.size == undefined) {
      this.data.size = {
        width: 1920,
        height: 1080,
      };
    }
    this.requestUpdate();

    // Setup WebSocket and render preview after state is initialized
    requestAnimationFrame(() => {
      this.updateSourcesList();
      this.renderPreview();
      this.setupWebSocket();
      this.updateTagSubscriptions();
    });
  }

  override firstUpdated(): void {
    // Setup after initial render
    requestAnimationFrame(() => {
      this.setupCanvas();
      this.setupEventListeners();
      this.populateTagDatalist();
    });
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();

    // Cleanup
    if (this.ws) {
      this.ws.close();
    }

    // Unsubscribe all tags
    for (const sourceId of Object.keys(this.tagSubscriptions)) {
      const subs = this.tagSubscriptions[sourceId];
      for (const tagKey of Object.keys(subs)) {
        this.unsubscribeTag(sourceId, tagKey);
      }
    }

    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  private setupCanvas(): void {
    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    this.canvasElement = this.shadowRoot?.querySelector(
      "#preview-canvas"
    ) as HTMLCanvasElement;

    // Canvas is exactly the virtual screen size
    this.canvasElement!.width = w;
    this.canvasElement!.height = h;
    this.canvasElement!.style.width = `${w}px`;
    this.canvasElement!.style.height = `${h}px`;

    // Set preview-sources to same size
    const sources = this.shadowRoot?.querySelector(
      "#preview-sources"
    ) as HTMLElement;
    if (sources) {
      sources.style.width = `${w}px`;
      sources.style.height = `${h}px`;
    }

    // Setup scaling to fit viewport
    this.updateVirtualScreenScale();

    this.renderPreview();

    // Update size inputs
    const sizeWidth = this.shadowRoot?.querySelector(
      "#size-width"
    ) as HTMLInputElement;
    const sizeHeight = this.shadowRoot?.querySelector(
      "#size-height"
    ) as HTMLInputElement;
    if (sizeWidth) sizeWidth.value = String(w);
    if (sizeHeight) sizeHeight.value = String(h);
  }

  private updateVirtualScreenScale(): void {
    if (!this.canvasElement) return;

    const sources = this.shadowRoot?.querySelector(
      "#preview-sources"
    ) as HTMLElement;
    const canvasArea = this.shadowRoot?.querySelector(
      ".editor-canvas-area"
    ) as HTMLElement;

    if (!canvasArea) return;

    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    // Calculate scale to fit viewport while maintaining aspect ratio
    const viewportWidth = canvasArea.clientWidth;
    const viewportHeight = canvasArea.clientHeight;

    const scaleX = viewportWidth / w;
    const scaleY = viewportHeight / h;
    const scale = Math.min(scaleX, scaleY);

    // Apply scale to both canvas and sources
    const scaleStyle = `scale(${scale})`;
    this.canvasElement!.style.transform = scaleStyle;
    this.canvasElement!.style.transformOrigin = "0 0";
    if (sources) {
      sources.style.transform = scaleStyle;
      sources.style.transformOrigin = "0 0";
    }
  }

  private getCanvasPixel(event_: MouseEvent | TouchEvent): Position {
    const canvas = this.canvasElement!;
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
    let clientX: number;
    let clientY: number;

    if (event_ instanceof MouseEvent) {
      clientX = event_.clientX - rect.left;
      clientY = event_.clientY - rect.top;
    } else {
      clientX = event_.touches[0].clientX - rect.left;
      clientY = event_.touches[0].clientY - rect.top;
    }

    // Convert to canvas virtual coordinates
    const x = Math.floor(clientX * scaleX);
    const y = Math.floor(clientY * scaleY);

    return { x, y };
  }

  private getSourceObject(sourceData: SourceData) {
    if (this.sourceObjects[sourceData.id] === undefined) {
      const sourceAdapter = createSourceAdapter(sourceData);

      this.sourceObjects[sourceData.id] = sourceAdapter;
    }
    return this.sourceObjects[sourceData.id];
  }

  private renderPreview(): void {
    const sourcesContainer = this.shadowRoot?.querySelector(
      "#preview-sources"
    ) as HTMLElement;
    if (!sourcesContainer) return;

    // Only clear and rebuild if sources changed
    if (Object.keys(this.previewWindows).length === 0) {
      sourcesContainer.innerHTML = "";
    }

    for (const sourceData of this?.data?.sources||[] ) {
      if (!sourceData.visible) continue;
      // Reuse existing window if present
      const sourceAdapter = this.getSourceObject(sourceData);

      if (this.previewWindows[sourceData.id]) {
        sourceAdapter.updateContent(
          this.previewWindows[sourceData.id].querySelector(
            ".window-container"
          ) as HTMLElement
        );
        this.updatePreviewTransform(sourceData);
        continue;
      }

      // Create new preview window
      const { window: window_, container } =
        sourceAdapter.createPreviewElements();
      window_.id = `window-${sourceData.id}`;
      window_.dataset.sourceId = sourceData.id;

      sourceAdapter.updateContent(container);

      sourcesContainer.append(window_);
      this.previewWindows[sourceData.id] = window_;
      sourceAdapter.applyTransforms(window_);

    }

    // Auto-select first source if none selected
    if (!this.selectedSourceId && this.data.sources.length > 0) {
      this.selectSource(this.data.sources[0].id);
    }

    this.drawCornerHandles();
  }

  private updatePreviewTransform(sourceData: SourceData): void {
    // Smoothly update just the transform without recreating DOM
    if (!this.previewWindows[sourceData.id]) return;

    const element = this.previewWindows[sourceData.id];
    const sourceAdapter = this.getSourceObject(sourceData);

    // Apply perspective matrix if corners are available
    const transform = sourceData.transform || {};
    const config = sourceData.config || {};
    const corners = transform.corners;

    if (corners) {
      const windowWidth = config.window_width || 1920;
      const windowHeight = config.window_height || 1080;
      const matrix = this.calculatePerspectiveMatrix(
        corners,
        windowWidth,
        windowHeight
      );
      element.style.transformOrigin = "0 0";
      element.style.transform = `matrix3d(${matrix.join(",")})`;
    } else {
      element.style.transform = "none";
    }

    // Let source handle its specific transforms
    sourceAdapter.applyTransforms(element);
  }

  private calculatePerspectiveMatrix(
    corners: Corners,
    windowWidth: number,
    windowHeight: number
  ): number[] {
    // Source is the window itself (0,0 to width, height)
    const sourceCorners = [
      0,
      0,
      windowWidth,
      0,
      0,
      windowHeight,
      windowWidth,
      windowHeight,
    ];

    // Destination is relative to top-left corner
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

    // Create perspective transform instance
    const perspT = new PerspT(sourceCorners, destinationCorners);

    // Get the coefficients matrix
    const coeffs = perspT.coeffs;

    // Convert 3x3 matrix to matrix3d format
    return this.coeffsToMatrix3d(coeffs);
  }

  private coeffsToMatrix3d(coeffs: number[]): number[] {
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

  private drawCornerHandles(): void {
    const canvas = this.canvasElement;
    if (!canvas) return;

    if (this.isViewerMode) {
      canvas.style.display = "none";
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);

    if (!this.selectedSourceId) return;

    const source = this.data.sources.find(
      (s) => s.id === this.selectedSourceId
    );
    if (!source || !source.transform?.corners) return;

    const corners = source.transform.corners;

    // Draw corner handles
    const cornerKeys = ["tl", "tr", "bl", "br"] as const;
    for (const key of cornerKeys) {
      const corner = corners[key];
      if (!corner) continue;

      context.fillStyle = "#167f16ff";
      context.beginPath();
      context.arc(corner.x, corner.y, 30, 0, Math.PI * 2);
      context.fill();

      context.strokeStyle = "#dff6ebff";
      context.lineWidth = 8;
      context.beginPath();
      context.arc(corner.x, corner.y, 30, 0, Math.PI * 2);
      context.stroke();

      context.fillStyle = "#000";
      context.font = "12px Arial";
      context.fillText(key, corner.x + 15, corner.y + 15);
    }
  }

  private setupEventListeners(): void {
    // Skip editor-specific listeners in viewer mode
    if (!this.isViewerMode) {
      // Save button
      this.shadowRoot
        ?.querySelector("#save-btn")
        ?.addEventListener("click", () => this.save());

      // Add source button
      this.shadowRoot
        ?.querySelector("#add-source-btn")
        ?.addEventListener("click", () => this.addSource());

      // Size inputs
      const sizeWidth = this.shadowRoot?.querySelector(
        "#size-width"
      ) as HTMLInputElement;
      sizeWidth?.addEventListener("input", (event_) => {
        this.data.size.width = Number.parseInt(
          (event_.target as HTMLInputElement).value
        );
        this.canvasElement!.width = this.data.size.width;
        this.canvasElement!.style.width = `${this.data.size.width}px`;
        const sources = this.shadowRoot?.querySelector(
          "#preview-sources"
        ) as HTMLElement;
        if (sources) sources.style.width = `${this.data.size.width}px`;
        this.updateVirtualScreenScale();
        this.renderPreview();
      });

      const sizeHeight = this.shadowRoot?.querySelector(
        "#size-height"
      ) as HTMLInputElement;
      sizeHeight?.addEventListener("input", (event_) => {
        // if (this.data.size === 0 || this.data.size === 0) {
        //   this.data.size = { width: 0, height: 0 };
        // }
        this.data.size.height = Number.parseInt(
          (event_.target as HTMLInputElement).value
        );
        this.canvasElement!.height = this.data.size.height;
        this.canvasElement!.style.height = `${this.data.size.height}px`;
        const sources = this.shadowRoot?.querySelector(
          "#preview-sources"
        ) as HTMLElement;
        if (sources) sources.style.height = `${this.data.size.height}px`;
        this.updateVirtualScreenScale();
        this.renderPreview();
      });

      // Transform controls
      const opacityInput = this.shadowRoot?.querySelector(
        "#opacity"
      ) as HTMLInputElement;
      opacityInput?.addEventListener("input", (event_) => {
        const source = this.getSelectedSource();
        if (source) {
          source.transform.opacity = Number.parseFloat(
            (event_.target as HTMLInputElement).value
          );
          const opacityVal = this.shadowRoot?.querySelector("#opacity-val");
          if (opacityVal) {
            opacityVal.textContent = Number.parseFloat(
              (event_.target as HTMLInputElement).value
            ).toFixed(2);
          }
          this.broadcastOpacity(source);
          this.renderPreview();
        }
      });

      const opacityTag = this.shadowRoot?.querySelector(
        "#opacity-tag"
      ) as HTMLInputElement;
      opacityTag?.addEventListener("input", (event_) => {
        const source = this.getSelectedSource();
        if (source) {
          source.transform.opacity_tag = (
            event_.target as HTMLInputElement
          ).value;
          this.updateTagSubscriptions();
        }
      });

      const blendMode = this.shadowRoot?.querySelector(
        "#blend-mode"
      ) as HTMLSelectElement;
      blendMode?.addEventListener("change", (event_) => {
        const source = this.getSelectedSource();
        if (source) {
          source.transform.blend_mode = (
            event_.target as HTMLSelectElement
          ).value;
          this.renderPreview();
        }
      });

      const rotation = this.shadowRoot?.querySelector(
        "#rotation"
      ) as HTMLInputElement;
      rotation?.addEventListener("input", (event_) => {
        const source = this.getSelectedSource();
        if (source) {
          source.transform.rotation = Number.parseInt(
            (event_.target as HTMLInputElement).value
          );
          this.renderPreview();
        }
      });

      // Corner inputs
      const cornerInputs = this.shadowRoot?.querySelectorAll(
        "input.corner-x, input.corner-y"
      );
      if (cornerInputs)
        for (const input of cornerInputs) {
          input.addEventListener("input", (event_) => {
            const source = this.getSelectedSource();
            if (source) {
              const corner = (event_.target as HTMLInputElement).dataset.corner;
              const isX = (
                event_.target as HTMLInputElement
              ).className.includes("corner-x");

              if (!source.transform.corners) {
                source.transform.corners = this.getDefaultCorners();
              }

              if (isX) {
                (source.transform.corners[corner as keyof Corners] as any).x =
                  Number.parseFloat((event_.target as HTMLInputElement).value);
              } else {
                (source.transform.corners[corner as keyof Corners] as any).y =
                  Number.parseFloat((event_.target as HTMLInputElement).value);
              }

              this.broadcastTransform(source);
              this.updatePreviewTransform(source);
              this.drawCornerHandles();
            }
          });
        }
    }

    // Canvas interactions (always available)
    this.canvasElement!.addEventListener("mousedown", (event_) =>
      this.onCanvasMouseDown(event_)
    );
    this.canvasElement!.addEventListener("mousemove", (event_) =>
      this.onCanvasMouseMove(event_)
    );
    this.canvasElement!.addEventListener("mouseup", () =>
      this.onCanvasMouseUp()
    );

    this.canvasElement!.addEventListener("mouseleave", () =>
      this.onCanvasMouseUp()
    );

    // Touch events
    this.canvasElement!.addEventListener("touchstart", (event_) =>
      this.onCanvasTouchStart(event_)
    );
    this.canvasElement!.addEventListener("touchmove", (event_) =>
      this.onCanvasTouchMove(event_)
    );
    this.canvasElement!.addEventListener("touchend", () =>
      this.onCanvasTouchEnd()
    );

    this.canvasElement!.addEventListener("touchcancel", () =>
      this.onCanvasTouchEnd()
    );

    this.canvasElement!.addEventListener("touchleave", () => {
      this.onCanvasTouchEnd();
    });
  }

  private onCanvasMouseDown(event_: MouseEvent): void {
    this.isDragging = true;
    this.checkCornerClick(event_);
  }

  private onCanvasMouseMove(event_: MouseEvent): void {
    if (!this.isDragging || !this.draggingCorner) return;

    const { x, y } = this.getCanvasPixel(event_);

    // Store raw mouse position
    this.lastRawMousePos = { x, y };

    // Start animation loop if not running
    if (!this.animationFrameId) {
      this.animationFrameId = requestAnimationFrame(() =>
        this.updateDragAnimation()
      );
    }
  }

  private updateDragAnimation(): void {
    if (!this.isDragging || !this.draggingCorner || !this.lastRawMousePos) {
      this.animationFrameId = null;
      return;
    }

    const source = this.getSelectedSource();
    if (!source || !source.transform?.corners) {
      this.animationFrameId = null;
      return;
    }

    // Apply position filtering
    const filter =
      this.cornerFilters[
        this.draggingCorner as keyof typeof this.cornerFilters
      ];
    const filtered = filter.update(
      this.lastRawMousePos.x,
      this.lastRawMousePos.y
    );

    (source.transform.corners[this.draggingCorner as keyof Corners] as any) = {
      x: filtered.x,
      y: filtered.y,
    };

    this.broadcastTransform(source);
    this.updatePreviewTransform(source);
    this.updateTransformInputs();
    this.drawCornerHandles();

    // Continue animation loop
    this.animationFrameId = requestAnimationFrame(() =>
      this.updateDragAnimation()
    );
  }

  private onCanvasMouseUp(): void {
    if (!this.isDragging) return;

    this.isDragging = false;
    this.draggingCorner = null;
    this.lastRawMousePos = null;

    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    const source = this.getSelectedSource();

    this.broadcastTransform(source, true);
  }

  private onCanvasTouchStart(event_: TouchEvent): void {
    const touch = event_.touches[0];
    const mouseEvent = new MouseEvent("mousedown", {
      clientX: touch.clientX,
      clientY: touch.clientY,
    });
    this.canvasElement!.dispatchEvent(mouseEvent);
  }

  private onCanvasTouchMove(event_: TouchEvent): void {
    event_.preventDefault();
    const touch = event_.touches[0];
    const mouseEvent = new MouseEvent("mousemove", {
      clientX: touch.clientX,
      clientY: touch.clientY,
    });
    this.canvasElement!.dispatchEvent(mouseEvent);
  }

  private onCanvasTouchEnd(): void {
    const mouseEvent = new MouseEvent("mouseup");
    this.canvasElement!.dispatchEvent(mouseEvent);
  }

  private checkCornerClick(event_: MouseEvent): void {
    const source = this.getSelectedSource();
    if (!source || !source.transform?.corners) return;

    const { x, y } = this.getCanvasPixel(event_);

    const corners = source.transform.corners;
    const hitRadius = 30;

    for (const [key, corner] of Object.entries(corners)) {
      const distribution = Math.hypot(x - corner.x, y - corner.y);
      if (distribution < hitRadius) {
        this.draggingCorner = key;

        // Reset filter to current corner position
        this.cornerFilters[key as keyof typeof this.cornerFilters].reset();
        this.cornerFilters[key as keyof typeof this.cornerFilters].update(
          corner.x,
          corner.y
        );

        return;
      }
    }
  }

  private broadcastTransform(
    source: SourceData | undefined,
    force = false
  ): void {
    if (!source || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    if (Date.now() - this.broadcastRateLimitTime < 120 && !force) {
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

  private broadcastOpacity(source: SourceData): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    this.ws.send(
      JSON.stringify({
        source_id: source.id,
        opacity: source.transform.opacity,
      })
    );
  }

  private async populateTagDatalist(): Promise<void> {
    try {
      const response = await fetch("/tag_api/list");
      const data = await response.json();
      const tags = Object.keys(data).sort();

      const datalist = this.shadowRoot?.querySelector("#available-tags");
      if (!datalist) return;

      datalist.innerHTML = "";
      for (const tagidx of tags) {
        const tag = data[tagidx];
        if (tag.type === "number" || tag.type === "string") {
          const option = document.createElement("option");
          option.value = tag.name;
          datalist.append(option);
        }
      }
    } catch (error) {
      console.error("Failed to fetch tags:", error);
    }
  }

  private updateTagSubscriptions(): void {
    const currentSources = new Set(this.data.sources.map((s) => s.id));

    // Unsubscribe removed sources
    for (const sourceId of Object.keys(this.tagSubscriptions)) {
      if (!currentSources.has(sourceId)) {
        const subs = this.tagSubscriptions[sourceId];
        for (const tagKey of Object.keys(subs)) {
          this.unsubscribeTag(sourceId, tagKey);
        }
      }
    }

    // Update subscriptions for existing sources
    for (const source of this.data.sources) {
      const sourceAdapter = this.getSourceObject(source);

      sourceAdapter.updateSubscriptions(
        (sourceId, tagName, tagKey) => this.subscribeTag(sourceId, tagName, tagKey),
        (sourceId, tagKey) => this.unsubscribeTag(sourceId, tagKey)
      );
    }
  }

  private subscribeTag(sourceId: string, tagName: string, tagKey: string): void {
    // Ensure tag: prefix
    const fullTag = tagName.startsWith("tag:") ? tagName : `tag:${tagName}`;
    const infourl = "/tag_api/info" + tagName;

    const source = this.data.sources.find((s) => s.id === sourceId);
    if (!source) return;

    const sourceObject = this.getSourceObject(source);

    // Fetch initial tag value
    fetch(infourl)
      .then((response) => response.json())
      .then((data) => {
        sourceObject.handleTagUpdate(tagKey, data.lastVal);
        this.renderPreview();
      });

    // Subscribe to future updates
    const callback = (value: number) => {
      sourceObject.handleTagUpdate(tagKey, value);
      this.renderPreview();
    };

    if (!this.tagSubscriptions[sourceId]) {
      this.tagSubscriptions[sourceId] = {};
    }
    this.tagSubscriptions[sourceId][tagKey] = { tag: fullTag, callback };
    kaithemapi.subscribe(fullTag, callback);
  }

  private unsubscribeTag(sourceId: string, tagKey: string): void {
    const subs = this.tagSubscriptions[sourceId];
    if (subs && subs[tagKey]) {
      const sub = subs[tagKey];
      kaithemapi.unsubscribe(sub.tag, sub.callback);
      delete subs[tagKey];
      if (Object.keys(subs).length === 0) {
        delete this.tagSubscriptions[sourceId];
      }
    }
  }

  private setupWebSocket(): void {
    const protocol = globalThis.location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(
      `${protocol}://${globalThis.location.host}` +
        `/projection-mapper/ws/${this.module}/${this.resource}`
    );

    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "refresh_page") {
        // eslint-disable-next-line unicorn/prefer-global-this
        window.location.reload();
      }

      const source = this.data.sources.find((s) => s.id === message.source_id);
      if (!source) return;

      // Don't apply updates from other clients while dragging the same source
      if (this.isDragging && this.selectedSourceId === source.id) {
        return;
      }

      // Apply any transform properties sent in the message
      if (message.corners) {
        source.transform.corners = message.corners;
      }
      if (message.opacity !== undefined) {
        source.transform.opacity = message.opacity;
      }

      this.renderPreview();
      this.updateTransformInputs();
    });
  }

  private updateSourcesList(): void {
    this.requestUpdate();
  }

  private selectSource(sourceId: string): void {
    this.selectedSourceId = sourceId;
    this.updateSourcesList();
    this.updateTransformInputs();
    this.renderSourceTypeSpecificOptions();
    this.updateTagSubscriptions();

    const transformSection = this.shadowRoot?.querySelector(
      "#transform-section"
    ) as HTMLElement;
    if (transformSection) transformSection.style.display = "block";

    this.renderPreview();
  }

  private getSelectedSource(): SourceData | undefined {
    return this.data.sources.find((s) => s.id === this.selectedSourceId);
  }

  private updateTransformInputs(): void {
    const source = this.getSelectedSource();
    if (!source) return;

    const transform = source.transform || {};

    const opacitySlider = this.shadowRoot?.querySelector(
      "#opacity"
    ) as HTMLInputElement;
    if (opacitySlider) {
      opacitySlider.value = String(transform.opacity ?? 1);
      const opacityVal = this.shadowRoot?.querySelector("#opacity-val");
      if (opacityVal) {
        opacityVal.textContent = (transform.opacity ?? 1).toFixed(2);
      }
    }

    const opacityTagInput = this.shadowRoot?.querySelector(
      "#opacity-tag"
    ) as HTMLInputElement;
    if (opacityTagInput) {
      opacityTagInput.value = transform.opacity_tag ?? "";
    }

    const blendSelect = this.shadowRoot?.querySelector(
      "#blend-mode"
    ) as HTMLSelectElement;
    if (blendSelect) {
      blendSelect.value = transform.blend_mode ?? "normal";
    }

    const rotationInput = this.shadowRoot?.querySelector(
      "#rotation"
    ) as HTMLInputElement;
    if (rotationInput) {
      rotationInput.value = String(transform.rotation ?? 0);
    }

    if (transform.corners) {
      const cornerKeys = ["tl", "tr", "bl", "br"] as const;
      for (const key of cornerKeys) {
        const corner = transform.corners[key];
        const xInputs = this.shadowRoot?.querySelectorAll(
          `input.corner-x[data-corner="${key}"]`
        );
        const yInputs = this.shadowRoot?.querySelectorAll(
          `input.corner-y[data-corner="${key}"]`
        );

        const xInput = xInputs?.[0] as HTMLInputElement;
        const yInput = yInputs?.[0] as HTMLInputElement;

        if (xInput) {
          xInput.value = String(corner.x);
        }
        if (yInput) {
          yInput.value = String(corner.y);
        }
      }
    }
  }

  private getDefaultCorners(): Corners {
    const w = this.data.size?.width || 1920;
    const h = this.data.size?.height || 1080;

    return {
      tl: { x: 0, y: 0 },
      tr: { x: w, y: 0 },
      bl: { x: 0, y: h },
      br: { x: w, y: h },
    };
  }

  private showSourceTypeDialog(): void {
    const container = document.createElement("div");
    container.style.cssText =
      "position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); " +
      "background: white; padding: 20px; border-radius: 8px; " +
      "box-shadow: 0 4px 6px rgba(0,0,0,0.1); z-index: 10000; " +
      "font-family: system-ui; max-width: 400px;";

    const title = document.createElement("h3");
    title.textContent = "Choose Source Type";
    title.style.margin = "0 0 16px 0";

    const typeSelect = document.createElement("select");
    typeSelect.style.cssText =
      "width: 100%; padding: 8px; margin-bottom: 16px; " +
      "border: 1px solid #ccc; border-radius: 4px; font-size: 14px;";
    typeSelect.innerHTML = `
      <option value="">-- Select a source type --</option>
      <option value="iframe">iFrame (Web Content)</option>
      <option value="clock">Digital Clock</option>
      <option value="tag">Tag Display</option>
    `;

    const buttonContainer = document.createElement("div");
    buttonContainer.style.cssText =
      "display: flex; gap: 8px; justify-content: flex-end;";

    const cancelButton = document.createElement("button");
    cancelButton.textContent = "Cancel";
    cancelButton.className = "btn btn-sm";
    cancelButton.style.marginRight = "8px";
    cancelButton.addEventListener("click", () => {
      container.remove();
    });

    const nextButton = document.createElement("button");
    nextButton.textContent = "Next";
    nextButton.className = "btn btn-primary btn-sm";
    nextButton.addEventListener("click", () => {
      const type = typeSelect.value;
      if (!type) return;
      container.remove();
      this.promptSourceName(type);
    });

    buttonContainer.append(cancelButton, nextButton);
    container.append(title, typeSelect, buttonContainer);
    document.body.append(container);
    typeSelect.focus();
  }

  private promptSourceName(sourceType: string): void {
    const name = prompt("Source name:");
    if (!name) return;

    const id = this.generateId();
    const config = this.getDefaultConfig(sourceType);
    const transform: SourceTransform = {
      corners: this.getDefaultCorners(),
      opacity: 1,
      opacity_tag: "",
      blend_mode: "normal",
      rotation: 0,
    };

    const sourceData: SourceData = {
      id,
      name,
      type: sourceType,
      config,
      transform,
      visible: true,
    };
    this.data.sources.push(sourceData);
    this.selectSource(id);
    this.updateSourcesList();
    this.renderPreview();
  }

  private getDefaultConfig(sourceType: string): SourceConfig {
    const configs: Record<string, SourceConfig> = {
      iframe: {
        url: "",
        window_width: 1920,
        window_height: 1080,
        render_width: 1920,
        render_height: 1080,
        crop_x: 0,
        crop_y: 0,
      },
      clock: {
        window_width: 800,
        window_height: 200,
        clock_format: "%H:%M:%S",
        text_color: "#ffffff",
        text_size: 72,
        font_family: "monospace",
        text_alignment: "center",
        text_shadow_offset_x: 2,
        text_shadow_offset_y: 2,
        text_shadow_blur: 4,
        text_shadow_color: "rgba(0,0,0,0.5)",
      },
      tag: {
        window_width: 800,
        window_height: 200,
        tag_name: "",
        format_string: "%s",
        text_color: "#ffffff",
        text_size: 48,
        font_family: "monospace",
        text_alignment: "center",
        text_shadow_offset_x: 2,
        text_shadow_offset_y: 2,
        text_shadow_blur: 4,
        text_shadow_color: "rgba(0,0,0,0.5)",
      },
    };
    return configs[sourceType] || {};
  }

  private addSource(): void {
    this.showSourceTypeDialog();
  }

  private renderSourceTypeSpecificOptions(): void {
    const sourceData = this.getSelectedSource();
    if (!sourceData) return;

    const configSection = this.shadowRoot?.querySelector(
      "#source-config-section"
    ) as HTMLElement;
    if (!configSection) return;

    const sourceAdapter = this.getSourceObject(sourceData);
    configSection.innerHTML = "";
    sourceAdapter.renderConfigUI(configSection, (adapter) => {
      this.updatePreviewTransform(sourceData);
      this.renderPreview();
    });
    configSection.style.display = "block";
  }

  private deleteSource(sourceId: string): void {
    const subs = this.tagSubscriptions[sourceId];
    if (subs) {
      for (const tagKey of Object.keys(subs)) {
        this.unsubscribeTag(sourceId, tagKey);
      }
    }
    this.data.sources = this.data.sources.filter((s) => s.id !== sourceId);

    if (this.selectedSourceId === sourceId) {
      this.selectedSourceId = null;
      const transformSection = this.shadowRoot?.querySelector(
        "#transform-section"
      ) as HTMLElement;
      if (transformSection) {
        transformSection.style.display = "none";
      }
      const configSection = this.shadowRoot?.querySelector(
        "#source-config-section"
      ) as HTMLElement;
      if (configSection) {
        configSection.style.display = "none";
      }
    }

    delete this.sourceObjects[sourceId];
    this.updateSourcesList();
    this.renderPreview();
  }

  private async save(): Promise<void> {
    try {
      // Ensure size is set
      if (this.data.size === 0 || this.data.size === 0) {
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
      alert("Save failed: " + (error as Error).message);
    }
  }

  private generateId(): string {
    return "src_" + Math.random().toString(36).slice(2, 11);
  }

  override render() {
    if (this.isViewerMode) {
      return html`
        <div class="projection-editor viewer-mode">
          <div
            class="editor-canvas-area viewer-mode"
            style="width: 100%; height: 100vh; overflow: hidden;">
            <canvas id="preview-canvas"></canvas>
            <div id="preview-sources"></div>
          </div>
        </div>
      `;
    }

    return html`
      <div class="projection-editor" id="projection-editor">
        <div class="editor-toolbar">
          <h2>${this.data.title}</h2>
          <button id="save-btn" class="btn btn-primary">Save</button>
        </div>

        <div class="editor-main">
          <div class="editor-canvas-area">
            <canvas id="preview-canvas"></canvas>
            <div id="preview-sources"></div>
          </div>

          <div class="editor-sidebar">
            <div class="sidebar-section">
              <h3>Sources</h3>
              <button id="add-source-btn" class="btn btn-sm">
                + Add Source
              </button>
              <div id="sources-list" class="sources-list">
                ${this.data.sources.map(
                  (source) => html`
                    <div
                      class="source-item ${source.id === this.selectedSourceId
                        ? "selected"
                        : ""}"
                      @click="${() => this.selectSource(source.id)}">
                      <div class="source-item-content">
                        <span>${source.name}</span>
                        <button
                          class="btn-small del-source"
                          @click="${(event: MouseEvent) => {
                            event.stopPropagation();
                            this.deleteSource(source.id);
                          }}">
                          Delete
                        </button>
                      </div>
                    </div>
                  `
                )}
              </div>
            </div>

            <div class="sidebar-section" id="size-section">
              <h3>Projection Size</h3>
              <div class="form-group">
                <label>Width (px)</label>
                <input type="number" id="size-width" min="320" value="1920" />
              </div>
              <div class="form-group">
                <label>Height (px)</label>
                <input type="number" id="size-height" min="240" value="1080" />
              </div>
            </div>

            <div
              class="sidebar-section"
              id="transform-section"
              style="display: none;">
              <h3>Transform</h3>
              <div class="form-group">
                <label>Opacity</label>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <input
                    type="range"
                    id="opacity"
                    min="0"
                    max="1"
                    step="0.01"
                    value="1"
                    style="flex: 1;" />
                  <span id="opacity-val">1.00</span>
                </div>
              </div>

              <div class="form-group">
                <label>Opacity Tag (optional)</label>
                <input
                  type="text"
                  id="opacity-tag"
                  placeholder="/path/to/tag"
                  list="available-tags" />
                <datalist id="available-tags"></datalist>
              </div>

              <div class="form-group">
                <label>Blend Mode</label>
                <select id="blend-mode">
                  <option value="normal">Normal</option>
                  <option value="multiply">Multiply</option>
                  <option value="screen">Screen</option>
                  <option value="overlay">Overlay</option>
                  <option value="darken">Darken</option>
                  <option value="lighten">Lighten</option>
                </select>
              </div>

              <div class="form-group">
                <label>Rotation (deg)</label>
                <input type="number" id="rotation" value="0" step="1" />
              </div>

              <div class="form-group">
                <h4>Corner Points</h4>
                <div class="corners-grid">
                  <div>
                    <label>Top-Left</label>
                    <input
                      type="number"
                      class="corner-x"
                      data-corner="tl"
                      placeholder="X" />
                    <input
                      type="number"
                      class="corner-y"
                      data-corner="tl"
                      placeholder="Y" />
                  </div>
                  <div>
                    <label>Top-Right</label>
                    <input
                      type="number"
                      class="corner-x"
                      data-corner="tr"
                      placeholder="X" />
                    <input
                      type="number"
                      class="corner-y"
                      data-corner="tr"
                      placeholder="Y" />
                  </div>
                  <div>
                    <label>Bottom-Left</label>
                    <input
                      type="number"
                      class="corner-x"
                      data-corner="bl"
                      placeholder="X" />
                    <input
                      type="number"
                      class="corner-y"
                      data-corner="bl"
                      placeholder="Y" />
                  </div>
                  <div>
                    <label>Bottom-Right</label>
                    <input
                      type="number"
                      class="corner-x"
                      data-corner="br"
                      placeholder="X" />
                    <input
                      type="number"
                      class="corner-y"
                      data-corner="br"
                      placeholder="Y" />
                  </div>
                </div>
              </div>
            </div>

            <div
              class="sidebar-section"
              id="source-config-section"
              style="display: none;"></div>
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define("projection-editor", ProjectionEditor);

export default ProjectionEditor;
