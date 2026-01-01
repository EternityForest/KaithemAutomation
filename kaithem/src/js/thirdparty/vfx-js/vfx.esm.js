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
    }

    /**
     * Add an effect to the pipeline
     */
    addEffect(shader, params = {}) {
        this.effects.push({
            shader,
            params,
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
        this.effects.forEach((effect) => {
            if (!effect.enabled) return;

            switch (effect.shader) {
            case 'glitch':
                this.glitch(effect.params);
                break;
            case 'crt':
                this.crt(effect.params);
                break;
            case 'film_grain':
                this.filmGrain(effect.params);
                break;
            case 'rgb_shift':
                this.rgbShift(effect.params);
                break;
            case 'kaleidoscope':
                this.kaleidoscope(
                    effect.params
                );
                break;
            case 'pixelate':
                this.pixelate(effect.params);
                break;
            }
        });
    }

    /**
     * Glitch effect
     */
    glitch(params = {}) {
        const amount = params.amount || 0.05;
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
                const idx = (y * this.canvas.width + x) *
                    4;
                const sourceIdx = (y * this.canvas.width +
                    ((x + offset +
                        this.canvas.width) %
                        this.canvas.width)) *
                    4;

                data[idx] = data[sourceIdx];
                data[idx + 1] = data[sourceIdx + 1];
                data[idx + 2] = data[sourceIdx + 2];
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
    crt(params = {}) {
        const intensity = params.intensity || 0.15;
        const lineWidth = params.lineWidth || 2;

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
                    const idx = (y *
                        this.canvas.width + x) * 4;

                    data[idx] *= (1 - intensity);
                    data[idx + 1] *= (1 - intensity);
                    data[idx + 2] *= (1 - intensity);
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
    filmGrain(params = {}) {
        const intensity = params.intensity || 0.1;
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
    rgbShift(params = {}) {
        const offset = params.offset || 3;
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
    kaleidoscope(params = {}) {
        const segments = params.segments || 6;
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
    pixelate(params = {}) {
        const pixelSize = params.pixelSize || 5;
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
                const idx = (y *
                    this.canvas.width + x) * 4;
                const r = data[idx];
                const g = data[idx + 1];
                const b = data[idx + 2];
                const a = data[idx + 3];

                for (let py = 0;
                    py < pixelSize &&
                        y + py < this.canvas.height;
                    py++) {
                    for (let px = 0;
                        px < pixelSize &&
                            x + px <
                            this.canvas.width;
                        px++) {
                        const pIdx = ((y + py) *
                            this.canvas.width +
                            (x + px)) * 4;

                        data[pIdx] = r;
                        data[pIdx + 1] = g;
                        data[pIdx + 2] = b;
                        data[pIdx + 3] = a;
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
