
import { kaithemapi } from "/static/js/widget.mjs"

import {appData, appMethods, appComputed,initChandlerVueModel} from "./boardapi.mjs?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0";

appMethods.showPresetDialog = function (fixture) {
    vueapp.$data.selectingPresetFor = fixture
}

appData.selectingImageLabelForPreset = null
appData.iframeDialog = null

const session_time = new Date().toISOString().slice(0, -8)
window.session_time = session_time
appData.getExcalidrawCueLink = function (group, cue) {
    return '/excalidraw-plugin/edit?module=' +
        encodeURIComponent(this.boardname.split(":")[0]) +
        '&resource=' + encodeURIComponent("media/chandler/sketches/cue_" + this.boardname.split(":")[1] + "_" +
            "_" +
            group + "_" + cue.name + ".excalidraw.png") +
        "&callback=" + encodeURIComponent("/chandler/label_image_update_callback/cue/" + cue.id) +
        "&ratio_guide=16_9"
}




appData.selectingPresetFor = null
// Add console specific stuff to the appdata
appData.formatTime = function (t) {
    var date = new Date(t * 1000);
    return date.strftime("%I:%M:%S%p")
}

appData.boardname = window.location.pathname.split('/')[3]

document.title = appData.boardname

appData.keyboardJS = keyboardJS


const options = {
    moduleCache: {
        vue: Vue
    },
    async getFile(url) {

        const res = await fetch(url);
        if (!res.ok)
            throw Object.assign(new Error(res.statusText + ' ' + url), { res });
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

const { loadModule } = window['vue3-sfc-loader'];


function httpVueLoader(u) {
    return Vue.defineAsyncComponent(() => loadModule(u, options))
}
window.httpVueLoader = httpVueLoader

var vueapp = Vue.createApp(
    {
        data: function () {
            return appData
        },
        methods: appMethods,
        components: {
            "combo-box": window.httpVueLoader('/static/vue/ComboBox.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            "h-fader": window.httpVueLoader('../static/hfader.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'cue-countdown': window.httpVueLoader('../static/cue-countdown.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'cue-table': window.httpVueLoader('../static/cuetable.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),

            // // Currently contains the timers and the display tags for the groups overview
            'group-ui': window.httpVueLoader('../static/group-ui-controls.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'smooth-range': window.httpVueLoader('/static/vue/smoothrange.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'media-browser': window.httpVueLoader('../static/media-browser.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'slideshow-telemetry': window.httpVueLoader('../static/signagetelemetry.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'fixture-presets-dialog': window.httpVueLoader('../static/fixture-presets-dialog.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'cue-logic-dialog': window.httpVueLoader('../static/cue-logic-dialog.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),
            'preset-editing-dialog': window.httpVueLoader('../static/preset-editing-dialog.vue?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0'),

        },
        computed: appComputed
    }).mount("#app")


// Blur the active element to cause Onchange events
window.visibilitychange = function () {
    document.activeElement.blur();
};


var prev = history.state

function handleDialogState(e) {
    if (e.newState == 'open') {
        history.pushState({ el: e.target.id }, null, '#popover')
        prev = history.state
    }
    else {
        if (history.state?.el == e.target.id) {
            history.back()
            prev = history.state
        }
    }
}

globalThis.handleDialogState = handleDialogState

window.addEventListener('popstate', function (e) {
    if (prev?.el && document.getElementById(prev?.el).hidePopover) {
        document.getElementById(prev?.el).hidePopover()
    }
    prev = history.state
});


window.setIframeDialog = function (iframe) {
    appData.iframeDialog = iframe
}
const boardname = window.location.pathname.split('/')[3];
window.boardname = boardname
initChandlerVueModel(boardname,vueapp)