import { defineConfig } from 'vite';

// Build a self contained static app with relative asset paths, so the
// output works under whatever BASE_PATH Kaithem serves it from.
export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
