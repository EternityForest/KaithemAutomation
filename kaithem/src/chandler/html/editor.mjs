
import{ boardname, triggerShortcut} from "./boardapi.mjs";

let selectingPresetForDestination = Vue.ref(false)
let selectingPresetFor= Vue.ref("")

function showPresetDialog(fixture, dest) {
    if (dest) {
        selectingPresetForDestination.value = true
    }
    else {
        selectingPresetForDestination.value = false
    }
    selectingPresetFor.value = fixture
}

let selectingImageLabelForPreset = Vue.ref(null)
let iframeDialog = Vue.ref(null)

const session_time = new Date().toISOString().slice(0, -8)
window.session_time = session_time
function getExcalidrawCueLink(group, cue) {
    return '/excalidraw-plugin/edit?module=' +
        encodeURIComponent(boardname.value.split(":")[0]) +
        '&resource=' + encodeURIComponent("media/chandler/sketches/cue_" + boardname.value.split(":")[1] + "_" +
            "_" +
            group + "_" + cue.name + ".excalidraw.png") +
        "&callback=" + encodeURIComponent("/chandler/label_image_update_callback/cue/" + cue.id) +
        "&ratio_guide=16_9"
}


// If true preset applies to final val of range effect
selectingPresetForDestination = Vue.ref(false)

selectingPresetFor = Vue.ref(null)
// Add console specific stuff to the appdata



document.title = boardname.value


// Blur the active element to cause Onchange events
window.visibilitychange = function () {
    document.activeElement.blur();
};


var prev = history.state

function handleDialogState(e) {
    if (e.newState == 'open') {
        history.pushState({ el: e.target.id }, null, 'editor/'+boardname.value+'#popover')
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
    iframeDialog.value = iframe
}
window.boardname = boardname

let sc_code = Vue.ref("");

function shortcut() {
  triggerShortcut(sc_code.value);
  sc_code.value = "";
}

function closePreview(s) {
  document.querySelector("#soundpreviewdialog").close();
  document.querySelector("#soundpreview").pause();
}

export {
    sc_code,
    shortcut,
    closePreview,
    showPresetDialog,
    selectingPresetForDestination,
    selectingPresetFor,
    getExcalidrawCueLink,
    iframeDialog,
    selectingImageLabelForPreset
}