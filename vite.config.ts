import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
// rollup.config.js
const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/static/vite/", // Use a relative base path
  assetsInclude: ["**/*.woff", "**/*.woff2"],
  plugins: [vue()],

  define: {
    // Enable devtools in production
    __VUE_PROD_DEVTOOLS__: true,
  },
  build: {
    outDir: "kaithem/data/static/vite",
    minify: false,
    assetsInlineLimit: 4 * 1024,
    sourcemap: true,

    rollupOptions: {
      preserveEntrySignatures: "exports-only",
      external: [
        "/static/js/widget.mjs",
        "/static/js/thirdparty/picodash/picodash-base.esm.js",
      ],

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
    },
  },
});
