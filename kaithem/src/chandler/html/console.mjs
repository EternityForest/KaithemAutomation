
import { kaithemapi } from "/static/js/widget.mjs"

import {appData, appMethods, appComputed} from "./boardapi.mjs?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0";

appMethods.showPresetDialog = function (fixture, dest) {
    if (dest) {
        this.selectingPresetForDestination = true
    }
    else {
        this.selectingPresetForDestination = false
    }
    this.selectingPresetFor = fixture
}

appData.selectingImageLabelForPreset = Vue.ref(null)
appData.iframeDialog = Vue.ref(null)

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


// If true preset applies to final val of range effect
appData.selectingPresetForDestination = Vue.ref(false)

appData.selectingPresetFor = Vue.ref(null)
// Add console specific stuff to the appdata
appData.formatTime = function (t) {
    var date = new Date(t * 1000);
    return date.strftime("%I:%M:%S%p")
}

appData.boardname = Vue.ref(window.location.pathname.split('/')[3])

document.title = appData.boardname

appData.keyboardJS = keyboardJS


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
    appData.iframeDialog.value = iframe
}
const boardname = window.location.pathname.split('/')[3];
window.boardname = boardname

console.log('boardname', boardname)
export { appData, appMethods, appComputed }