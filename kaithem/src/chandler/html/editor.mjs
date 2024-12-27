import {
  boardname,
  triggerShortcut,
  groupcues,
  groupname,
  selectedCues,
} from "./boardapi.mjs";

import { ref } from "/static/js/thirdparty/vue.esm-browser.js";

let selectingPresetForDestination = ref(false);
let selectingPresetFor = ref("");

function showPresetDialog(fixture, destination) {
  selectingPresetForDestination.value = destination ? true : false;
  selectingPresetFor.value = fixture;
}

let selectingImageLabelForPreset = ref(null);
let iframeDialog = ref(null);

const session_time = new Date().toISOString().slice(0, -8);
globalThis.session_time = session_time;
function getExcalidrawCueLink(group, cue) {
  return (
    "/excalidraw-plugin/edit?module=" +
    encodeURIComponent(boardname.value.split(":")[0]) +
    "&resource=" +
    encodeURIComponent(
      "media/chandler/sketches/cue_" +
        boardname.value.split(":")[1] +
        "_" +
        "_" +
        group +
        "_" +
        cue.name +
        ".excalidraw.png"
    ) +
    "&callback=" +
    encodeURIComponent("/chandler/label_image_update_callback/cue/" + cue.id) +
    "&ratio_guide=16_9"
  );
}

// If true preset applies to final val of range effect
selectingPresetForDestination = ref(false);

selectingPresetFor = ref(null);
// Add console specific stuff to the appdata

document.title = boardname.value;

// Blur the active element to cause Onchange events
globalThis.visibilitychange = function () {
  document.activeElement.blur();
};

var previous = history.state;

function handleDialogState(event) {
  if (event.newState == "open") {
    history.pushState(
      { el: event.target.id },
      null,
      "editor/" + boardname.value + "#popover"
    );
    previous = history.state;
  } else {
    if (history.state?.el == event.target.id) {
      history.back();
      previous = history.state;
    }
  }
}

globalThis.handleDialogState = handleDialogState;

globalThis.addEventListener("popstate", function (_event) {
  // eslint-disable-next-line unicorn/prefer-query-selector
  if (previous?.el && document.getElementById(previous?.el).hidePopover) {
    // eslint-disable-next-line unicorn/prefer-query-selector
    document.getElementById(previous?.el).hidePopover();
  }
  previous = history.state;
});

globalThis.setIframeDialog = function (iframe) {
  iframeDialog.value = iframe;
};
globalThis.boardname = boardname;

let sc_code = ref("");

function shortcut() {
  triggerShortcut(sc_code.value);
  sc_code.value = "";
}

function closePreview() {
  document.querySelector("#soundpreviewdialog").close();
  document.querySelector("#soundpreview").pause();
}

function addValueToCue() {
  if (!newcueu.value) {
    return;
  }
  globalThis.api_link.send([
    "add_cueval",
    groupcues.value[groupname.value][selectedCues.value[groupname.value]],
    newcueu.value,
    newcuevnumber.value,
  ]);
  if (!Number.isNaN(Number.parseInt(newcuevnumber.value))) {
    newcuevnumber.value = (Number.parseInt(newcuevnumber.value) + 1).toString();
  }
}

function addTagToCue() {
  if (!newcuetag.value) {
    return;
  }
  globalThis.api_link.send([
    "add_cueval",
    groupcues.value[groupname.value][selectedCues.value[groupname.value]],
    newcuetag.value,
    "value",
  ]);
}

function addGroup() {
  globalThis.api_link.send(["addgroup", newgroupname.value]);
}

let eventsFilterString = ref("");
let newcueu = ref("");
let newcuetag = ref("");
let newcuevnumber = ref("");
let newgroupname = ref("");

export {
  sc_code,
  shortcut,
  closePreview,
  showPresetDialog,
  selectingPresetForDestination,
  selectingPresetFor,
  getExcalidrawCueLink,
  iframeDialog,
  selectingImageLabelForPreset,
  eventsFilterString,
  newcueu,
  newcuetag,
  newcuevnumber,
  newgroupname,
  addValueToCue,
  addTagToCue,
  addGroup,
};
