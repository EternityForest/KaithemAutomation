import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import smartAsset from "rollup-plugin-smart-asset";
// rollup.config.js
const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/static/vite/", // Use a relative base path
  assetsInclude: ["**/*.woff", "**/*.woff2"],
  plugins: [vue()],

  build: {
    outDir: "kaithem/data/static/vite",
    minify: false,
    assetsInlineLimit: 4 * 1024,


    rollupOptions: {
      preserveEntrySignatures: "exports-only",
      external: ["/static/js/widget.mjs",
        "/static/js/thirdparty/picodash/picodash-base.esm.js"],

      input: {
        // excalidraw: resolve(
        //   __dirname,
        //   "kaithem/src/plugins/CorePluginExcalidraw/next/index.html"
        // ),


        chandler_commander: resolve(
          __dirname,
          "kaithem/src/chandler/html/commander.html"
        ),
        mixer: resolve(
          __dirname,
          "kaithem/src/plugins/CorePluginJackMixer/next/index.html"
        ),
      },
      output: {
        assetFileNames: "assets/[name]-[hash][extname]",

        preserveModules: true,
      },
      external: ["/static/js/widget.mjs"],
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
