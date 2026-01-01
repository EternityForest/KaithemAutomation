// Projection Mapper Editor
// Real-time collaborative editing with WebSocket sync

class ProjectionEditor {
    constructor(container, module, resource, initialData) {
        this.container = container;
        this.module = module;
        this.resource = resource;
        this.data = JSON.parse(JSON.stringify(initialData));
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
        this.setupCanvas();
        this.setupWebSocket();
        this.setupEventListeners();
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
            document.getElementById('preview-canvas');
        const rect = this.canvasElement
            .parentElement
            .getBoundingClientRect();

        this.canvasElement.width = rect.width;
        this.canvasElement.height = rect.height;

        // Setup preview container
        const container =
            document.getElementById('preview-container');
        container.style.position = 'relative';
        container.style.width = '100%';
        container.style.height = '100%';

        this.renderPreview();
    }

    renderPreview() {
        const container =
            document.getElementById('preview-container');
        container.innerHTML = '';

        this.previewIframes = {};

        this.data.sources.forEach((source) => {
            if (!source.visible) return;

            if (source.type === 'iframe') {
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

                wrapper.appendChild(iframe);

                this.applyPreviewTransform(wrapper, source);
                container.appendChild(wrapper);
                this.previewIframes[source.id] = wrapper;
            }
        });

        this.drawCornerHandles();
    }

    applyPreviewTransform(element, source) {
        const transform = source.transform || {};
        const corners = transform.corners;

        element.style.position = 'absolute';

        if (!corners) {
            element.style.top = '0';
            element.style.left = '0';
            element.style.width = '100%';
            element.style.height = '100%';
        } else {
            element.style.width = '100%';
            element.style.height = '100%';
            element.style.top = '0';
            element.style.left = '0';

            const matrix = this.calculateMatrix(corners);
            element.style.transformOrigin = '0 0';
            element.style.transform =
                `matrix3d(${matrix.join(',')})`;
        }

        if (transform.opacity !== undefined) {
            element.style.opacity =
                transform.opacity.toString();
        }

        if (transform.blend_mode) {
            element.style.mixBlendMode =
                transform.blend_mode;
        }

        if (transform.rotation) {
            element.style.transform +=
                ` rotate(${transform.rotation}deg)`;
        }
    }

    calculateMatrix(corners) {
        // Simplified: identity matrix
        // TODO: Implement proper perspective transform
        return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
    }

    drawCornerHandles() {
        const canvas = this.canvasElement;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

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
        cornerKeys.forEach((key) => {
            const corner = corners[key];
            if (!corner) return;

            const x = corner.x * scaleX;
            const y = corner.y * scaleY;

            ctx.fillStyle = '#00ff00';
            ctx.beginPath();
            ctx.arc(x, y, 10, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = '#000';
            ctx.font = '12px Arial';
            ctx.fillText(key, x + 15, y + 15);
        });
    }

    setupEventListeners() {
        // Save button
        document.getElementById('save-btn')
            .addEventListener('click', () =>
                this.save()
            );

        // Add source button
        document.getElementById('add-source-btn')
            .addEventListener('click', () =>
                this.addSource()
            );

        // Add effect button
        const addEffectBtn =
            document.getElementById('add-effect-btn');
        if (addEffectBtn) {
            addEffectBtn.addEventListener('click', () =>
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
        document.getElementById('opacity')
            ?.addEventListener('input', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    source.transform.opacity =
                        parseFloat(e.target.value);
                    document
                        .getElementById('opacity-val')
                        .textContent =
                        parseFloat(e.target.value)
                            .toFixed(2);
                    this.renderPreview();
                }
            });

        document.getElementById('blend-mode')
            ?.addEventListener('change', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    source.transform.blend_mode =
                        e.target.value;
                    this.renderPreview();
                }
            });

        document.getElementById('rotation')
            ?.addEventListener('input', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    source.transform.rotation =
                        parseInt(e.target.value);
                    this.renderPreview();
                }
            });

        // Corner inputs
        document.querySelectorAll(
            'input.corner-x, input.corner-y'
        ).forEach((input) => {
            input.addEventListener('input', (e) => {
                const source = this.getSelectedSource();
                if (source) {
                    const corner =
                        e.target.dataset.corner;
                    const isX = e.target.className
                        .includes('corner-x');

                    if (!source.transform.corners) {
                        source.transform.corners = {
                            tl: { x: 0, y: 0 },
                            tr: {
                                x: window.innerWidth,
                                y: 0,
                            },
                            bl: {
                                x: 0,
                                y: window.innerHeight,
                            },
                            br: {
                                x: window.innerWidth,
                                y: window.innerHeight,
                            },
                        };
                    }

                    if (isX) {
                        source.transform.corners[
                            corner
                        ].x = parseFloat(e.target.value);
                    } else {
                        source.transform.corners[
                            corner
                        ].y = parseFloat(e.target.value);
                    }

                    this.broadcastTransform(source);
                    this.renderPreview();
                }
            });
        });
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
        this.renderPreview();
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
            const dist = Math.hypot(
                x - corner.x,
                y - corner.y
            );
            if (dist < hitRadius) {
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
        const protocol = window.location.protocol ===
            'https:' ? 'wss' : 'ws';
        this.ws = new WebSocket(
            `${protocol}://${window.location.host}` +
            `/projection-mapper/ws/${this.module}/${this.resource}`
        );

        this.ws.onmessage = (event) => {
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
        };
    }

    updateSourcesList() {
        const list =
            document.getElementById('sources-list');
        if (!list) return;

        list.innerHTML = '';

        this.data.sources.forEach((source) => {
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

            list.appendChild(item);
        });
    }

    selectSource(sourceId) {
        this.selectedSourceId = sourceId;
        this.updateSourcesList();
        this.updateTransformInputs();

        const transformSection =
            document.getElementById('transform-section');
        const vfxSection =
            document.getElementById('vfx-section');

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
            document.getElementById('opacity');
        if (opacitySlider) {
            opacitySlider.value =
                transform.opacity ?? 1;
            document
                .getElementById('opacity-val')
                .textContent =
                (transform.opacity ?? 1).toFixed(2);
        }

        const blendSelect =
            document.getElementById('blend-mode');
        if (blendSelect) {
            blendSelect.value =
                transform.blend_mode ?? 'normal';
        }

        const rotationInput =
            document.getElementById('rotation');
        if (rotationInput) {
            rotationInput.value =
                transform.rotation ?? 0;
        }

        if (transform.corners) {
            const cornerKeys =
                ['tl', 'tr', 'bl', 'br'];
            cornerKeys.forEach((key) => {
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
            });
        }
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
                corners: null,
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
            document.getElementById(
                'transform-section'
            ).style.display = 'none';
            document.getElementById(
                'vfx-section'
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
                alert('Save failed');
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
                .substr(2, 9);
    }
}

export default ProjectionEditor;
