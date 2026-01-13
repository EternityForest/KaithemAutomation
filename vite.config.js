import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "./", // Use a relative base path

  build: {
    outDir: "kaithem/data/static/vite",

    rollupOptions: {
      input: {
        excalidraw: resolve(
          __dirname,
          "kaithem/src/plugins/CorePluginExcalidraw/index.html"
        ),
      },
    },
  },
});
