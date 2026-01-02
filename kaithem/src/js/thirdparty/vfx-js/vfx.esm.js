// VFX-JS Stub - Minimal implementation for projection mapper
// Full VFX-JS can be integrated later: https://github.com/fand/vfx-js

/**
 * VFX
 * Minimal VFX effects wrapper
 * Provides glitch, CRT, film grain, and other effects
 */
export class VFX {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.effects = [];
        this.sourceElement = null;
    }

    /**
     * Add a source element (iframe, img, video, canvas, etc)
     * The element's content will be rendered to canvas before effects apply
     */
    add(sourceElement) {
        this.sourceElement = sourceElement;
        this.renderSourceToCanvas();
        return this;
    }

    /**
     * Render the source element to the canvas
     */
    renderSourceToCanvas() {
        if (!this.sourceElement) return;

        try {
            this.ctx.drawImage(this.sourceElement, 0, 0);
        } catch (error_) {
            // CORS or other rendering errors - silently continue
            // This is expected for cross-origin iframes
        }
    }

    /**
     * Add an effect to the pipeline
     */
    addEffect(shader, parameters = {}) {
        this.effects.push({
            shader,
            params: parameters,
            enabled: true,
        });
        return this;
    }

    /**
     * Remove an effect by shader name
     */
    removeEffect(shader) {
        this.effects = this.effects.filter(
            (e) => e.shader !== shader
        );
        return this;
    }

    /**
     * Apply all effects to canvas
     */
    apply() {
        for (const effect of this.effects) {
            if (!effect.enabled) continue;

            switch (effect.shader) {
            case 'glitch': {
                this.glitch(effect.params);
                break;
            }
            case 'crt': {
                this.crt(effect.params);
                break;
            }
            case 'film_grain': {
                this.filmGrain(effect.params);
                break;
            }
            case 'rgb_shift': {
                this.rgbShift(effect.params);
                break;
            }
            case 'kaleidoscope': {
                this.kaleidoscope(
                    effect.params
                );
                break;
            }
            case 'pixelate': {
                this.pixelate(effect.params);
                break;
            }
            }
        }
    }

    /**
     * Glitch effect
     */
    glitch(parameters = {}) {
        const amount = parameters.amount || 0.05;
        const lines = Math.floor(
            this.canvas.height * amount
        );

        const imageData = this.ctx.getImageData(
            0,
            0,
            this.canvas.width,
            this.canvas.height
        );
        const data = imageData.data;

        for (let i = 0; i < lines; i++) {
            const y = Math.floor(
                Math.random() * this.canvas.height
            );
            const offset = Math.floor(
                Math.random() * 20 - 10
            );

            for (let x = 0; x < this.canvas.width; x++) {
                const index = (y * this.canvas.width + x) *
                    4;
                const sourceIndex = (y * this.canvas.width +
                    ((x + offset +
                        this.canvas.width) %
                        this.canvas.width)) *
                    4;

                data[index] = data[sourceIndex];
                data[index + 1] = data[sourceIndex + 1];
                data[index + 2] = data[sourceIndex + 2];
            }
        }

        this.ctx.putImageData(
            imageData,
            0,
            0
        );
    }

    /**
     * CRT effect - scanlines
     */
    crt(parameters = {}) {
        const intensity = parameters.intensity || 0.15;
        const lineWidth = parameters.lineWidth || 2;

        const imageData = this.ctx.getImageData(
            0,
            0,
            this.canvas.width,
            this.canvas.height
        );
        const data = imageData.data;

        for (let y = 0; y < this.canvas.height; y++) {
            if (y % lineWidth === 0) {
                for (let x = 0; x <
                    this.canvas.width; x++) {
                    const index = (y *
                        this.canvas.width + x) * 4;

                    data[index] *= (1 - intensity);
                    data[index + 1] *= (1 - intensity);
                    data[index + 2] *= (1 - intensity);
                }
            }
        }

        this.ctx.putImageData(
            imageData,
            0,
            0
        );
    }

    /**
     * Film grain effect
     */
    filmGrain(parameters = {}) {
        const intensity = parameters.intensity || 0.1;
        const imageData = this.ctx.getImageData(
            0,
            0,
            this.canvas.width,
            this.canvas.height
        );
        const data = imageData.data;

        for (let i = 0; i < data.length; i += 4) {
            const grain = (Math.random() - 0.5) *
                intensity * 255;

            data[i] = Math.max(
                0,
                Math.min(255, data[i] + grain)
            );
            data[i + 1] = Math.max(
                0,
                Math.min(255, data[i + 1] + grain)
            );
            data[i + 2] = Math.max(
                0,
                Math.min(255, data[i + 2] + grain)
            );
        }

        this.ctx.putImageData(
            imageData,
            0,
            0
        );
    }

    /**
     * RGB shift effect
     */
    rgbShift(parameters = {}) {
        const offset = parameters.offset || 3;
        const imageData = this.ctx.getImageData(
            0,
            0,
            this.canvas.width,
            this.canvas.height
        );

        const r = new Uint8ClampedArray(
            imageData.data
        );
        const g = new Uint8ClampedArray(
            imageData.data
        );
        const b = new Uint8ClampedArray(
            imageData.data
        );

        const data = imageData.data;

        for (let i = 0; i < data.length; i += 4) {
            data[i] = r[(i + offset * 4) %
                data.length];
            data[i + 1] = g[i];
            data[i + 2] = b[(i - offset * 4 +
                data.length) % data.length];
        }

        this.ctx.putImageData(
            imageData,
            0,
            0
        );
    }

    /**
     * Kaleidoscope effect
     */
    kaleidoscope(parameters = {}) {
        const segments = parameters.segments || 6;
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;

        // Placeholder: just reduce colors
        const imageData = this.ctx.getImageData(
            0,
            0,
            this.canvas.width,
            this.canvas.height
        );
        const data = imageData.data;

        const levels = Math.floor(
            256 / segments
        );
        for (let i = 0; i < data.length; i += 4) {
            data[i] = Math.floor(
                data[i] / levels
            ) * levels;
            data[i + 1] = Math.floor(
                data[i + 1] / levels
            ) * levels;
            data[i + 2] = Math.floor(
                data[i + 2] / levels
            ) * levels;
        }

        this.ctx.putImageData(
            imageData,
            0,
            0
        );
    }

    /**
     * Pixelate effect
     */
    pixelate(parameters = {}) {
        const pixelSize = parameters.pixelSize || 5;
        const imageData = this.ctx.getImageData(
            0,
            0,
            this.canvas.width,
            this.canvas.height
        );
        const data = imageData.data;

        for (let y = 0; y < this.canvas.height;
            y += pixelSize) {
            for (let x = 0; x <
                this.canvas.width;
                x += pixelSize) {
                const index = (y *
                    this.canvas.width + x) * 4;
                const r = data[index];
                const g = data[index + 1];
                const b = data[index + 2];
                const a = data[index + 3];

                for (let py = 0;
                    py < pixelSize &&
                        y + py < this.canvas.height;
                    py++) {
                    for (let px = 0;
                        px < pixelSize &&
                            x + px <
                            this.canvas.width;
                        px++) {
                        const pIndex = ((y + py) *
                            this.canvas.width +
                            (x + px)) * 4;

                        data[pIndex] = r;
                        data[pIndex + 1] = g;
                        data[pIndex + 2] = b;
                        data[pIndex + 3] = a;
                    }
                }
            }
        }

        this.ctx.putImageData(
            imageData,
            0,
            0
        );
    }
}

export default VFX;
