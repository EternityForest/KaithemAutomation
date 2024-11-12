
appMethods.showPresetDialog = function (fixture) {
    vueapp.$data.selectingPresetFor = fixture
}

appData.selectingImageLabelForPreset = null
appData.iframeDialog = null
appData.filterPresets = ''
const session_time = new Date().toISOString().slice(0, -8)

appData.getExcalidrawCueLink = function (group, cue) {
    return '/excalidraw-plugin/edit?module=' +
        encodeURIComponent(this.boardname.split(":")[0]) +
        '&resource=' + encodeURIComponent("media/chandler/sketches/cue_" + this.boardname.split(":")[1] + "_" +
            "_" +
            group + "_" + cue.name + ".excalidraw.png") +
        "&callback=" + encodeURIComponent("/chandler/label_image_update_callback/cue/" + cue.id) +
        "&ratio_guide=16_9"
}

appData.getExcalidrawPresetLink = function (preset) {
    return '/excalidraw-plugin/edit?module=' +
        encodeURIComponent(this.boardname.split(":")[0]) +
        '&resource=' + encodeURIComponent("media/chandler/sketches/preset_" + this.boardname.split(":")[1] + "_" +
            preset + "_" +
            session_time + ".excalidraw.png") +
        "&callback=" + encodeURIComponent("/chandler/label_image_update_callback/preset/" + this.boardname + "/" + preset) +
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

appData.no_edit = !kaithemapi.checkPermission("system_admin");

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

var vueapp = Vue.createApp(
    {
        data: function () {
            return appData
        },
        methods: appMethods,
        components: {
            "combo-box": httpVueLoader('/static/vue/ComboBox.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            "h-fader": httpVueLoader('../static/hfader.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            'cue-countdown': httpVueLoader('../static/cue-countdown.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            'cue-table': httpVueLoader('../static/cuetable.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),

            // Currently contains the timers and the display tags for the groups overview
            'group-ui': httpVueLoader('../static/group-ui-controls.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            'smooth-range': httpVueLoader('/static/vue/smoothrange.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            'media-browser': httpVueLoader('../static/media-browser.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            'slideshow-telemetry': httpVueLoader('../static/signagetelemetry.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            'fixture-presets-dialog': httpVueLoader('../static/fixture-presets-dialog.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
            'cue-logic-dialog': httpVueLoader('../static/cue-logic-dialog.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61'),
        },
        computed: appComputed
    }).mount("#app")

var script = document.createElement('script');
script.onload = function () {
    const boardname = window.location.pathname.split('/')[3];
    init_api_link(boardname)
};

script.src = "/apiwidget/WebChandlerConsole:" + appData.boardname + "?js_name=api_link";

document.head.appendChild(script);


keysdown = {}
keyHandle = function (e) {
    if (keysdown[e.key] != undefined) {
        if (keysdown[e.key]) {
            return;
        }

    }
    keysdown[e.key] = true;
    e.preventRepeat();
    api_link.send(['event', "keydown." + e.key, 1, 'int', "__global__"])
}
keyUpHandle = function (e) {
    if (keysdown[e.key] != undefined) {
        if (!keysdown[e.key]) {
            return;
        }

    }
    keysdown[e.key] = false;
    api_link.send(['event', "keyup." + e.key, 1, 'int', "__global__"])
}
rebind = function (data) {
    keyboardJS.reset()
    keyboardJS.bind(keyHandle)
    keyboardJS.bind(null, keyUpHandle)

}

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

window.addEventListener('popstate', function (e) {
    if (prev?.el && document.getElementById(prev?.el).hidePopover) {
        document.getElementById(prev?.el).hidePopover()
    }
    prev = history.state
});