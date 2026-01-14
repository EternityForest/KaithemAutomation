import globals from "globals";
import pluginJs from "@eslint/js";
import tseslint from "typescript-eslint";
import pluginVue from "eslint-plugin-vue";
import eslintPluginUnicorn from "eslint-plugin-unicorn";
import importPlugin from "eslint-plugin-import";
import html from "eslint-plugin-html";
import { default as html2 } from "@html-eslint/eslint-plugin";
// import css from "@eslint/css";

/** @type {import('eslint').Linter.Config[]} */
export default [
  {
    files: ["**/*.{js,mjs,cjs,ts,vue,html}"],
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/thirdparty/**",
      "**/test_*",
    ],
  },
  {
    plugins: {
      html,
    },
    settings: {
      "import/resolver": {
        // You will also need to install and configure the TypeScript resolver
        // See also https://github.com/import-js/eslint-import-resolver-typescript#configuration
        typescript: true,
        node: {
          extensions: [".js", ".mjs", ".cjs", ".ts", ".vue"],
        },

        alias: {
          map: [["/static/js", "./kaithem/src/js"]],
        },
      },
    },
  },
  html2.configs["flat/recommended"],
  eslintPluginUnicorn.configs["flat/recommended"],
  { languageOptions: { globals: globals.browser } },
  pluginJs.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/essential"],
  importPlugin.flatConfigs.recommended,
  // {
  //   files: ["**/*.css"],
  //   language: "css/css",
  //   ...css.configs.recommended,
  // },

  {
    files: ["**/*.vue"],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    rules: {
      "import/no-unresolved": "error",
      "vue/no-undef-properties": "error",
      "unicorn/no-null": "off",
      "unicorn/prevent-abbreviations": [
        "error",
        {
          allowList: {
            i: true,
            j: true,
            k: true,
            v: true,
            ref: true,
          },
        },
      ],

      "vue/no-unused-vars": [
        "error",
        {
          ignorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          args: "all",
          argsIgnorePattern: "^_",
          caughtErrors: "all",
          caughtErrorsIgnorePattern: "^_",
          destructuredArrayIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
    },
  },
];
