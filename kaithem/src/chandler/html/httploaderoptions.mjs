import { loadModule } from '/static/js/thirdparty/vue3-sfc-loader.esm.js'
import * as Vue from "/static/js/thirdparty/vue.esm-browser.js";


const options = {
    moduleCache: {
        vue: Vue
    },

    async loadModule(path) {
        if (path.includes(".vue")) {
            return;
        }

        const path_is_abs = path.startsWith("http://") || path.startsWith("https://") || path.startsWith("/");

        if(!path_is_abs && !path.startsWith("./")) {
            path = "./" + path
        }
        let x = import(path)
        return x
    },

    async getFile(url) {

        const result = await fetch(url);
        if (!result.ok)
            throw Object.assign(new Error(result.statusText + ' ' + url), { res: result });

        // make js be treated as an mjs file
        // This is bad but should be ok because we shouldn't be using normal js at all
        // because that's not best practices
        if (url.endsWith(".js")) {
            return {
                getContentData: async (_asBinary) => {
                    return await result.text();
                },
                type: ".mjs",
            }
        }

        return {
            getContentData: asBinary => asBinary ? result.arrayBuffer() : result.text(),
        }
    },

    addStyle(textContent) {

        const style = Object.assign(document.createElement('style'), { textContent });
        const ref = document.head.querySelectorAll('style')[0] || null;
        document.head.insertBefore(style, ref);
    },
}


function httpVueLoader(u) {
    return Vue.defineAsyncComponent(() => loadModule(u, options))
}
globalThis.httpVueLoader = httpVueLoader

// We must populate this with everything we want to import from within a vue module
// Or else it will load them twice because it doesn't know about the
let vueModuleCache = options.moduleCache

export { httpVueLoader, vueModuleCache }