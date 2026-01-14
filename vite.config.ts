import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import smartAsset from "rollup-plugin-smart-asset";
// rollup.config.js
const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "./", // Use a relative base path
  assetsInclude: ["**/*.woff", "**/*.woff2"],

  build: {
    outDir: "kaithem/data/static/vite",
    minify: false,
    assetsInlineLimit: 4 * 1024,

    rollupOptions: {
      preserveEntrySignatures: "exports-only",

      input: {
        excalidraw: resolve(
          __dirname,
          "kaithem/src/plugins/CorePluginExcalidraw/index.html"
        ),
      },
      output: {
        assetFileNames: "assets/[name]-[hash][extname]",

        preserveModules: true,
      },
      plugins: [
        smartAsset({
          // "copy" mode extracts the base64 to an external file
          url: "copy",
          // Define extensions to search for
          extensions: [".svg", ".png", ".jpg", ".gif", ".woff2"],
          // Where to put the extracted files
          output: "dist/assets",
          // Option to hash filenames for caching
          useHash: true,
        }),
      ],
    },
  },
});
