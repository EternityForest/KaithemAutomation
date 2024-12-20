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
        if(path.startsWith("http://") || path.startsWith("https://") || path.startsWith("/")) {

        }
        else if(!path.startsWith("./")) {
            path = "./" + path
        }
        let x = import(path)
        console.log("loading", path, x)
        return x
    },

    async getFile(url) {

        const res = await fetch(url);
        if (!res.ok)
            throw Object.assign(new Error(res.statusText + ' ' + url), { res });

        // make js be treated as an mjs file
        // This is bad but should be ok because we shouldn't be using normal js at all
        // because that's not best practices
        if (url.endsWith(".js")) {
            return {
                getContentData: async (asBinary) => { // asBinary is unused here, we know it is a text file

                    return await res.text();
                },
                type: ".mjs",
            }
        }

        return {
            getContentData: asBinary => asBinary ? res.arrayBuffer() : res.text(),
        }
    },

    addStyle(textContent) {

        const style = Object.assign(document.createElement('style'), { textContent });
        const ref = document.head.getElementsByTagName('style')[0] || null;
        document.head.insertBefore(style, ref);
    },
}


function httpVueLoader(u) {
    return Vue.defineAsyncComponent(() => loadModule(u, options))
}
window.httpVueLoader = httpVueLoader

// We must populate this with everything we want to import from within a vue module
// Or else it will load them twice because it doesn't know about the
let vueModuleCache = options.moduleCache

export { httpVueLoader, vueModuleCache }