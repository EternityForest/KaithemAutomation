import {
  boardname,
  triggerShortcut,
} from "./boardapi.mjs";

import { ref } from "vue";


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




function addGroupDialog() {
  const x = prompt("New Group Name?");
  if (x != null) {
    globalThis.api_link.send(["addgroup", x]);
  }
}


let eventsFilterString = ref("");


export {
  sc_code,
  shortcut,
  closePreview,
  getExcalidrawCueLink,
  iframeDialog,
  selectingImageLabelForPreset,
  eventsFilterString,
  addGroupDialog
};
