import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
// rollup.config.js
const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: '/static/vite/', // Use a relative base path
  assetsInclude: ['**/*.woff', '**/*.woff2'],
  plugins: [vue()],

  define: {
    // Enable devtools in production
    __VUE_PROD_DEVTOOLS__: true,
  },
  build: {
    outDir: 'kaithem/data/static/vite',
    minify: false,
    assetsInlineLimit: 4 * 1024,
    sourcemap: true,

    rolldownOptions: {
      preserveEntrySignatures: 'exports-only',
      external: [
        '/static/js/widget.mjs',
        '/static/js/thirdparty/picodash/picodash-base.esm.js',
      ],

      input: {
        // excalidraw: resolve(
        //   __dirname,
        //   "kaithem/src/plugins/CorePluginExcalidraw/next/index.html"
        // ),

        alerts_component: resolve(
          __dirname,
          'kaithem/src/js/alerts-component.ts'
        ),

        yjs_provider: resolve(__dirname, 'kaithem/src/js/yjs-provider.ts'),

        dashboards_editor: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginDashboards/dashboards/index.html'
        ),

        chandler_media_display: resolve(
          __dirname,
          'kaithem/src/chandler/html/webmediadisplay.html'
        ),
        chandler_opz_import: resolve(
          __dirname,
          'kaithem/src/chandler/html/opz-import.html'
        ),
        chandler_commander: resolve(
          __dirname,
          'kaithem/src/chandler/html/commander.html'
        ),

        chandler_editor: resolve(
          __dirname,
          'kaithem/src/chandler/html/editor.html'
        ),

        chandler_config: resolve(
          __dirname,
          'kaithem/src/chandler/html/config.html'
        ),
        mixer: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginJackMixer/next/index.html'
        ),
        projectionmapper: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginProjectionMapper/html/editor.html'
        ),
        mapview: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginMapView/index.html'
        ),
        podman_manager: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginPodmanManager/index.html'
        ),
        container_apps: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginContainerApps/index.html'
        ),
        bluetooth_console: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginBluetooth/html/index.html'
        ),
        conversation_chat: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginPydanticConversation/html/index.html'
        ),
        git_snapshots: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginGitSnapshots/html/index.html'
        ),
        presentationscreen_admin: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginPresentationScreen/html/admin.html'
        ),
        presentationscreen_editor: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginPresentationScreen/html/editor.html'
        ),
        presentationscreen_viewer: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginPresentationScreen/html/viewer.html'
        ),
        text_editor: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginTextEditor/html/index.html'
        ),
        webconsole: resolve(
          __dirname,
          'kaithem/src/plugins/CorePluginWebConsole/html/index.html'
        ),
      },
      output: {
        assetFileNames: 'assets/[name]-[hash][extname]',
        entryFileNames: 'assets/[name].js',
        footer: '\n//# sourceMappingURL',
      },
      treeshake: {
        // Rolldown's treeshake.moduleSideEffects only accepts a boolean.
        // Older Rollup/Vite used the string 'no-treeshake' to retain whole
        // modules. The closest equivalent is to treat every module as having
        // side effects, so yjs providers, the alerts component, etc. are not
        // dropped from the bundle.
        moduleSideEffects: () => true,
      },
    },
  },
});
