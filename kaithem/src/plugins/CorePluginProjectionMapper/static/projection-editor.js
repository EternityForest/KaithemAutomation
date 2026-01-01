// Projection Mapper Editor
// Real-time collaborative editing with WebSocket sync

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
                        <div id="preview-container"
                             class="preview-container">
                        </div>
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
        this.canvasElement =
            document.querySelector('#preview-canvas');
        const rect = this.canvasElement
            .parentElement
            .getBoundingClientRect();

        this.canvasElement.width = rect.width;
        this.canvasElement.height = rect.height;

        // Setup preview container
        const container =
            document.querySelector('#preview-container');
        container.style.position = 'relative';
        container.style.width = '100%';
        container.style.height = '100%';

        this.renderPreview();
    }

    renderPreview() {
        const container =
            document.querySelector('#preview-container');

        // Only clear and rebuild if sources changed
        if (Object.keys(this.previewIframes).length === 0) {
            container.innerHTML = '';
        }

        for (const source of this.data.sources) {
            if (!source.visible) continue;

            if (source.type === 'iframe') {
                // Reuse existing wrapper if present
                if (this.previewIframes[source.id]) {
                    this.applyPreviewTransform(
                        this.previewIframes[source.id],
                        source
                    );
                    continue;
                }

                const wrapper = document.createElement('div');
                wrapper.className = 'preview-source';
                wrapper.id = `source-${source.id}`;
                wrapper.dataset.sourceId = source.id;

                const iframe = document.createElement('iframe');
                iframe.src = source.config.url;
                iframe.style.border = 'none';
                iframe.style.pointerEvents = 'none';
                iframe.style.width = '100%';
                iframe.style.height = '100%';
                iframe.style.display = 'block';
                iframe.sandbox.add(
                    'allow-same-origin',
                    'allow-scripts',
                    'allow-forms'
                );

                wrapper.append(iframe);

                this.applyPreviewTransform(wrapper, source);
                container.append(wrapper);
                this.previewIframes[source.id] = wrapper;
            }
        }

        // Auto-select first source if none selected
        if (!this.selectedSourceId &&
            this.data.sources.length > 0) {
            this.selectSource(this.data.sources[0].id);
        }

        this.drawCornerHandles();
    }

    applyPreviewTransform(element, source) {
        const transform = source.transform || {};
        const corners = transform.corners;

        element.style.position = 'absolute';

        if (corners) {
            element.style.width = '100%';
            element.style.height = '100%';
            element.style.top = '0';
            element.style.left = '0';

            const matrix =
                this.calculatePerspectiveMatrix(corners);
            element.style.transformOrigin = '0 0';
            element.style.transform =
                `matrix3d(${matrix.join(',')})`;
        } else {
            element.style.top = '0';
            element.style.left = '0';
            element.style.width = '100%';
            element.style.height = '100%';
        }

        if (transform.opacity !== undefined) {
            element.style.opacity =
                transform.opacity.toString();
        }

        if (transform.blend_mode) {
            element.style.mixBlendMode =
                transform.blend_mode;
        }

        if (transform.rotation && corners) {
            const matrix =
                this.calculatePerspectiveMatrix(corners);
            element.style.transform =
                `matrix3d(${matrix.join(',')})` +
                ` rotate(${transform.rotation}deg)`;
        } else if (transform.rotation && !corners) {
            element.style.transform =
                `rotate(${transform.rotation}deg)`;
        }
    }

    updatePreviewTransform(source) {
        // Smoothly update just the transform without
        // recreating DOM
        if (!this.previewIframes[source.id]) return;

        const element = this.previewIframes[source.id];
        this.applyPreviewTransform(element, source);
    }

    calculatePerspectiveMatrix(corners) {
        // Get projection size
        const w = this.data.size?.width || 1920;
        const h = this.data.size?.height || 1080;

        const sourceCorners = [
            [0, 0],
            [w, 0],
            [0, h],
            [w, h],
        ];

        const destinationCorners = [
            [corners.tl.x, corners.tl.y],
            [corners.tr.x, corners.tr.y],
            [corners.bl.x, corners.bl.y],
            [corners.br.x, corners.br.y],
        ];

        return this.computeHomography(
            sourceCorners,
            destinationCorners
        );
    }

    computeHomography(source, destination) {
        // Compute homography using DLT
        // (Direct Linear Transformation)
        const A = [];

        for (let i = 0; i < 4; i++) {
            const x = source[i][0];
            const y = source[i][1];
            const xp = destination[i][0];
            const yp = destination[i][1];

            A.push(
                [x, y, 1, 0, 0, 0, -xp * x, -xp * y, -xp],
                [0, 0, 0, x, y, 1, -yp * x, -yp * y, -yp]
            );
        }

        // Solve using SVD approximation (power iteration)
        const h = this.solveHomography(A);

        // Convert 3x3 homography to matrix3d format
        return this.homographyToMatrix3d(h);
    }

    solveHomography(A) {
        // Use power iteration to find eigenvector
        // corresponding to smallest eigenvalue
        const n = 9;
        let x = [];
        for (let i = 0; i < n; i++) {
            x[i] = Math.random();
        }

        // Power iteration (simplified SVD)
        for (let iter = 0; iter < 10; iter++) {
            let Ax = [];
            for (const element of A) {
                let sum = 0;
                for (let j = 0; j < n; j++) {
                    sum += element[j] * x[j];
                }
                Ax.push(sum);
            }

            // Compute A^T * A * x approximation
            let ATAx = [];
            for (let i = 0; i < n; i++) {
                let sum = 0;
                for (const [k, element] of A.entries()) {
                    sum += element[i] * Ax[k];
                }
                ATAx[i] = sum;
            }

            // Normalize
            let norm = 0;
            for (let i = 0; i < n; i++) {
                norm += ATAx[i] * ATAx[i];
            }
            norm = Math.sqrt(norm);

            if (norm > 1e-10) {
                for (let i = 0; i < n; i++) {
                    x[i] = ATAx[i] / norm;
                }
            }
        }

        return x;
    }

    homographyToMatrix3d(h) {
        // Convert 3x3 homography to 4x4 matrix3d
        // h = [h00, h01, h02, h10, h11, h12, h20, h21, h22]
        const H = [
            [h[0], h[1], h[2]],
            [h[3], h[4], h[5]],
            [h[6], h[7], h[8]],
        ];

        // Normalize by h22
        if (Math.abs(H[2][2]) > 1e-10) {
            for (let i = 0; i < 3; i++) {
                for (let j = 0; j < 3; j++) {
                    H[i][j] /= H[2][2];
                }
            }
        }

        // matrix3d format (column-major):
        // [scaleX, skewY, 0, perspectiveY,
        //  skewX, scaleY, 0, perspectiveX,
        //  0, 0, 1, 0,
        //  translateX, translateY, 0, 1]
        const matrix = [
            H[0][0], H[1][0], 0, H[2][0],
            H[0][1], H[1][1], 0, H[2][1],
            0, 0, 1, 0,
            H[0][2], H[1][2], 0, H[2][2],
        ];

        return matrix;
    }

    drawCornerHandles() {
        const canvas = this.canvasElement;
        if (!canvas) return;

        const context = canvas.getContext('2d');
        context.clearRect(0, 0, canvas.width, canvas.height);

        if (!this.selectedSourceId) return;

        const source = this.data.sources.find(
            (s) => s.id === this.selectedSourceId
        );
        if (!source || !source.transform?.corners) return;

        const corners = source.transform.corners;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;

        // Draw corner handles
        const cornerKeys = ['tl', 'tr', 'bl', 'br'];
        for (const key of cornerKeys) {
            const corner = corners[key];
            if (!corner) continue;

            const x = corner.x * scaleX;
            const y = corner.y * scaleY;

            context.fillStyle = '#00ff00';
            context.beginPath();
            context.arc(x, y, 10, 0, Math.PI * 2);
            context.fill();

            context.fillStyle = '#000';
            context.font = '12px Arial';
            context.fillText(key, x + 15, y + 15);
        }
    }

    setupEventListeners() {
        // Save button
        document.querySelector('#save-btn')
            .addEventListener('click', () =>
                this.save()
            );

        // Add source button
        document.querySelector('#add-source-btn')
            .addEventListener('click', () =>
                this.addSource()
            );

        // Add effect button
        const addEffectButton =
            document.querySelector('#add-effect-btn');
        if (addEffectButton) {
            addEffectButton.addEventListener('click', () =>
                this.addEffect()
            );
        }

        // Canvas dragging
        this.canvasElement.addEventListener(
            'mousedown',
            (e) => this.onCanvasMouseDown(e)
        );
        this.canvasElement.addEventListener(
            'mousemove',
            (e) => this.onCanvasMouseMove(e)
        );
        this.canvasElement.addEventListener(
            'mouseup',
            () => this.onCanvasMouseUp()
        );

        // Touch events
        this.canvasElement.addEventListener(
            'touchstart',
            (e) => this.onCanvasTouchStart(e)
        );
        this.canvasElement.addEventListener(
            'touchmove',
            (e) => this.onCanvasTouchMove(e)
        );
        this.canvasElement.addEventListener(
            'touchend',
            () => this.onCanvasTouchEnd()
        );

        // Transform controls
        document.querySelector('#opacity')
            ?.addEventListener('input', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    source.transform.opacity =
                        Number.parseFloat(e.target.value);
                    document
                        .querySelector('#opacity-val')
                        .textContent =
                        Number.parseFloat(e.target.value)
                            .toFixed(2);
                    this.renderPreview();
                }
            });

        document.querySelector('#blend-mode')
            ?.addEventListener('change', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    source.transform.blend_mode =
                        e.target.value;
                    this.renderPreview();
                }
            });

        document.querySelector('#rotation')
            ?.addEventListener('input', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    source.transform.rotation =
                        Number.parseInt(e.target.value);
                    this.renderPreview();
                }
            });

        // Corner inputs
        for (const input of document.querySelectorAll(
            'input.corner-x, input.corner-y'
        )) {
            input.addEventListener('input', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    const corner =
                        e.target.dataset.corner;
                    const isX = e.target.className
                        .includes('corner-x');

                    if (!source.transform.corners) {
                        source.transform.corners = this
                            .getDefaultCorners();
                    }

                    if (isX) {
                        source.transform.corners[
                            corner
                        ].x = Number.parseFloat(e.target.value);
                    } else {
                        source.transform.corners[
                            corner
                        ].y = Number.parseFloat(e.target.value);
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
        if (!this.isDragging || !this.draggingCorner)
            return;

        const source = this.getSelectedSource();
        if (!source || !source.transform?.corners) return;

        const canvas = this.canvasElement;
        const rect = canvas.getBoundingClientRect();

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        source.transform.corners[
            this.draggingCorner
        ] = { x, y };

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
        const mouseEvent = new MouseEvent(
            'mousedown',
            {
                clientX: touch.clientX,
                clientY: touch.clientY,
            }
        );
        this.canvasElement.dispatchEvent(mouseEvent);
    }

    onCanvasTouchMove(e) {
        e.preventDefault();
        const touch = e.touches[0];
        const mouseEvent = new MouseEvent(
            'mousemove',
            {
                clientX: touch.clientX,
                clientY: touch.clientY,
            }
        );
        this.canvasElement.dispatchEvent(mouseEvent);
    }

    onCanvasTouchEnd() {
        const mouseEvent = new MouseEvent('mouseup');
        this.canvasElement.dispatchEvent(mouseEvent);
    }

    checkCornerClick(e) {
        const source = this.getSelectedSource();
        if (!source || !source.transform?.corners) return;

        const canvas = this.canvasElement;
        const rect = canvas.getBoundingClientRect();

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const corners = source.transform.corners;
        const hitRadius = 15;

        for (const [key, corner] of Object.entries(
            corners
        )) {
            const distribution = Math.hypot(
                x - corner.x,
                y - corner.y
            );
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
        const protocol = globalThis.location.protocol ===
            'https:' ? 'wss' : 'ws';
        this.ws = new WebSocket(
            `${protocol}://${globalThis.location.host}` +
            `/projection-mapper/ws/${this.module}/${this.resource}`
        );

        this.ws.addEventListener('message', (event) => {
            const message = JSON.parse(event.data);
            if (message.type === 'transform_update') {
                const source = this.data.sources.find(
                    (s) => s.id === message.source_id
                );
                if (source) {
                    source.transform.corners =
                        message.corners;
                    this.renderPreview();
                    this.updateTransformInputs();
                }
            }
        });
    }

    updateSourcesList() {
        const list =
            document.querySelector('#sources-list');
        if (!list) return;

        list.innerHTML = '';

        for (const source of this.data.sources) {
            const item = document.createElement('div');
            item.className = 'source-item';
            if (source.id === this.selectedSourceId) {
                item.classList.add('selected');
            }

            item.innerHTML = `
                <div class="source-item-content">
                    <span>${source.name}</span>
                    <button class="btn-small del-source">
                        Delete
                    </button>
                </div>
            `;

            item.addEventListener('click', () => {
                this.selectSource(source.id);
            });

            item.querySelector('.del-source')
                ?.addEventListener('click',
                    (e) => {
                        e.stopPropagation();
                        this.deleteSource(source.id);
                    }
                );

            list.append(item);
        }
    }

    selectSource(sourceId) {
        this.selectedSourceId = sourceId;
        this.updateSourcesList();
        this.updateTransformInputs();

        const transformSection =
            document.querySelector('#transform-section');
        const vfxSection =
            document.querySelector('#vfx-section');

        if (transformSection)
            transformSection.style.display = 'block';
        if (vfxSection)
            vfxSection.style.display = 'block';

        this.renderPreview();
    }

    getSelectedSource() {
        return this.data.sources.find(
            (s) => s.id === this.selectedSourceId
        );
    }

    updateTransformInputs() {
        const source = this.getSelectedSource();
        if (!source) return;

        const transform = source.transform || {};

        const opacitySlider =
            document.querySelector('#opacity');
        if (opacitySlider) {
            opacitySlider.value =
                transform.opacity ?? 1;
            document
                .querySelector('#opacity-val')
                .textContent =
                (transform.opacity ?? 1).toFixed(2);
        }

        const blendSelect =
            document.querySelector('#blend-mode');
        if (blendSelect) {
            blendSelect.value =
                transform.blend_mode ?? 'normal';
        }

        const rotationInput =
            document.querySelector('#rotation');
        if (rotationInput) {
            rotationInput.value =
                transform.rotation ?? 0;
        }

        if (transform.corners) {
            const cornerKeys =
                ['tl', 'tr', 'bl', 'br'];
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
        const name = prompt('Source name:');
        if (!name) return;

        const url = prompt('URL:');
        if (!url) return;

        const source = {
            id: this.generateId(),
            name,
            type: 'iframe',
            config: { url },
            transform: {
                corners: this.getDefaultCorners(),
                opacity: 1,
                blend_mode: 'normal',
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
        this.data.sources = this.data.sources.filter(
            (s) => s.id !== sourceId
        );

        if (this.selectedSourceId === sourceId) {
            this.selectedSourceId = null;
            document.querySelector(
                '#transform-section'
            ).style.display = 'none';
            document.querySelector(
                '#vfx-section'
            ).style.display = 'none';
        }

        this.updateSourcesList();
        this.renderPreview();
    }

    addEffect() {
        const source = this.getSelectedSource();
        if (!source) return;

        const shader = prompt('Shader name:');
        if (!shader) return;

        source.vfx.push({
            shader,
            params: {},
        });

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
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(this.data),
                }
            );

            if (response.ok) {
                await response.json();
                alert('Saved successfully');

                // Broadcast reload to viewers
                if (this.ws &&
                    this.ws.readyState === WebSocket.OPEN
                ) {
                    this.ws.send(
                        JSON.stringify({
                            type: 'reload',
                        })
                    );
                }
            } else {
                const errorData = await response.json();
                alert(
                    'Save failed: ' +
                    (errorData.message || 'Unknown error')
                );
            }
        } catch (error) {
            console.error('Save error:', error);
            alert('Save failed: ' + error.message);
        }
    }

    generateId() {
        return 'src_' +
            Math.random()
                .toString(36)
                .slice(2, 11);
    }
}

export default ProjectionEditor;
