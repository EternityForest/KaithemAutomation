/*
 It's slowly being refactored after getting very out of hand.
 Things are done oddly because:

 1. It was not originally planned to be feature.value rich
 2. It started with Vue2


*/

import {
  useBlankDescriptions,
  formatInterval,
  dictView,
  formatTime,
} from "./utils.mjs?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0";
import { kaithemapi, APIWidget } from "/static/js/widget.mjs";

let keysdown = {};

//Current per group alpha channel
let alphas = Vue.ref({});
let groupmeta = Vue.ref({});
let groupname = Vue.ref(null);
let editingGroup = Vue.ref(null);
let universes = Vue.ref({});
let cues = Vue.ref({});
let newcuename = Vue.ref("");
let cuemeta = Vue.ref({});
let availableCommands = Vue.ref({});
// per scene user selected for editing
let selectedCues = Vue.ref({});
let showPages = Vue.ref(false);
let uiAlertSounds = Vue.ref(true);
// Used for things that auto select cues after a delay to set things
// up but also are cancelable.
let cueSelectTimeout = Vue.ref(0);
//go from cue name to cue id
//groupcues[groupuuid][cuename]=cueid
let groupcues = Vue.ref({});
let formattedCues = Vue.ref([]);
//Indexed by universe then channel number
let channelInfoByUniverseAndNumber = Vue.ref({});
//same info as groupvals, indexed hierarchally, as [universe][channel]
//Actual objs are shared too so changing one obj change in in the other.

let presets = Vue.ref({});

function keyHandle(e) {
  if (keysdown[e.key] != undefined) {
    if (keysdown[e.key]) {
      return;
    }
  }
  keysdown[e.key] = true;
  e.preventRepeat();
  api_link.send(["event", "keydown." + e.key, 1, "int", "__global__"]);
}
function keyUpHandle(e) {
  if (keysdown[e.key] != undefined) {
    if (!keysdown[e.key]) {
      return;
    }
  }
  keysdown[e.key] = false;
  api_link.send(["event", "keyup." + e.key, 1, "int", "__global__"]);
}

function rebindKeys() {
  keyboardJS.reset();
  keyboardJS.bind(keyHandle);
  keyboardJS.bind(null, keyUpHandle);
}

function playAlert(m) {
  if (uiAlertSounds.value) {
    var mp3_url = "/static/sounds/72127__kizilsungur__sweetalertsound3.opus";
    new Audio(mp3_url).play().catch(() => {});
  }
  if (m) {
    KaithemWidgetApiSnackbar(m, 60);
  }
}

function errorTone(m) {
  if (uiAlertSounds.value) {
    var mp3_url =
      "/static/sounds/423166__plasterbrain__minimalist-sci-fi-ui-error.opus";
    new Audio(mp3_url).play().catch(() => {});
  }
  if (m) {
    KaithemWidgetApiSnackbar(m, 60);
  }
}
// Legacy compatibility equivalents for the old vue2 apis. TODO get rid of this
function old_vue_set(o, k, v) {
  o[k] = v;
}

function old_vue_delete(o, k) {
  delete o[k];
}

function set(o, k, v) {
  if (o[k] == undefined) {
    old_vue_set(o, k, v);
  }
  for (var key in v) {
    // If values of same property are not equal,
    // objects are not equivalent
    if (o[k][key] !== v[key]) {
      old_vue_set(o[k], key, v[key]);
    }
  }

  // If we made it far.value, objects
  // are considered equivalent
  return true;
}

async function initializeState(board) {
  var v = await fetch("/chandler/api/all-cues/" + board, {
    method: "GET",
  });

  v = await v.json();

  for (var i in v) {
    handleCueInfo(i, v[i]);
  }
}

let cueSetData = {};

// Slowly we want to migrate to these two generic setters
async function setGroupProperty(group, property, value) {
  // Serialization prevents tests from acting badly and might even be important
  // in the ui on slow connections
  if (previousSerializedPromise.value) {
    await previousSerializedPromise.value;
  }

  var x = cueSetData[group + property];
  if (x) {
    clearTimeout(x);
    delete cueSetData[group + property];
  }
  var b = {};
  b[property] = value;

  previousSerializedPromise.value = fetch(
    "/chandler/api/set-group-properties/" + group,
    {
      method: "PUT",
      body: JSON.stringify(b),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
      },
    }
  ).catch(function (e) {
    alert("Error setting property.");
  });
  await previousSerializedPromise.value;
}

async function setCueProperty(cue, property, value) {
  if (previousSerializedPromise.value) {
    await previousSerializedPromise.value;
  }

  var x = cueSetData[cue + property];
  if (x) {
    clearTimeout(x);
    delete cueSetData[cue + property];
  }

  var b = {};
  b[property] = value;

  previousSerializedPromise.value = fetch(
    "/chandler/api/set-cue-properties/" + cue,
    {
      method: "PUT",
      body: JSON.stringify(b),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
      },
    }
  ).catch(function (e) {
    alert("Error setting property.");
  });
  await previousSerializedPromise.value;
}

function setCuePropertyDeferred(cue, property, value) {
  //Set the property in 5 seconds, unless we get another command to set
  //it to something else.  Used for cue text and stuff that shouldn;t update live
  // so it doesn't refresh a millon times
  var x = cueSetData[cue + property];
  if (x) {
    clearTimeout(x);
  }

  cueSetData[cue + property] = setTimeout(function () {
    var b = {};
    b[property] = value;

    fetch("/chandler/api/set-cue-properties/" + cue, {
      method: "PUT",
      body: JSON.stringify(b),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
      },
    }).catch(function (e) {
      alert("Error setting property.");
    });
    delete cueSetData[cue + property];
  }, 3000);
}

function setGroupPropertyDeferred(group, property, value) {
  //Set the property in 5 seconds, unless we get another command to set
  //it to something else
  var x = cueSetData[group + property];
  if (x) {
    clearTimeout(x);
  }

  cueSetData[group + property] = setTimeout(function () {
    var b = {};
    b[property] = value;

    fetch("/chandler/api/set-group-properties/" + group, {
      method: "PUT",
      body: JSON.stringify(b),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
      },
    }).catch(function (e) {
      alert("Error setting property.");
    });
    delete cueSetData[group + property];
  }, 3000);
}

function saveToDisk() {
  api_link.send(["saveState"]);
}

function sendGroupEventWithConfirm(evt, where) {
  if (confirm_for_group(where)) {
    api_link.send(["event", evt, "", "str", where]);
  }
}

function refreshhistory(sc) {
  api_link.send(["getcuehistory", sc]);
}
function setCueVal(sc, u, ch, val) {
  if (cuevals.value[sc]) {
    if (cuevals.value[sc][u]) {
      if (cuevals.value[sc][u]["__preset__"]) {
        api_link.send(["scv", sc, u, "__preset__", null]);
      }
    }
  }
  val = isNaN(parseFloat(val)) ? val : parseFloat(val);
  api_link.send(["scv", sc, u, ch, val]);
}

function selectcue(sc, cue) {
  if (cueSelectTimeout.value) {
    clearTimeout(cueSelectTimeout.value);
  }
  selectedCues.value[sc] = cue;
  getcuedata(groupcues.value[sc][cue]);
}

function selectgroup(sc, sn) {
  getcuedata(groupcues.value[sn][selectedCues.value[sc] || "default"]);
  if (cuePage.value[sn] == undefined) {
    cuePage.value[sn] = 0;
  }
  editingGroup.value = sc;
  groupname.value = sn;
}
function delgroup(sc) {
  var r = confirm("Really delete group?");
  if (r == true) {
    api_link.send(["del", sc]);
  }
}

function go(sc) {
  api_link.send(["go", sc]);
}

function shortcut(sc) {
  api_link.send(["shortcut", sc_code.value]);
  sc_code.value = "";
}

function stop(sc, sn) {
  var x = confirm(
    "Really stop group? The cue and all variables will be reset."
  );

  if (x) {
    api_link.send(["stop", sc]);
  }
}

function setalpha(sc, v) {
  api_link.send(["setalpha", sc, v]);
  alphas.value[sc] = v;
}

function nextcue(sc) {
  if (confirm_for_group(sc)) {
    api_link.send(["nextcue", sc]);
  }
}

function prevcue(sc) {
  if (confirm_for_group(sc)) {
    api_link.send(["prevcue", sc]);
  }
}

function add_cue(sc, v, after_cue) {
  api_link.send(["add_cue", sc, v, parseFloat(after_cue.number) * 1000]);
  //There's a difference between "not there" undefined and actually set to undefined....
  if (groupcues.value[sc][v] == undefined) {
    //Placeholder so we can at least show a no cue found message till it arrives
    old_vue_set(groupcues.value[sc], v, undefined);
  }
  if (cueSelectTimeout.value) {
    clearTimeout(cueSelectTimeout.value);
  }
  cueSelectTimeout.value = setTimeout(function () {
    old_vue_set(selectedCues.value, sc, v);
  }, 350);
}

function clonecue(sc, cue, v) {
  api_link.send(["clonecue", cue, v]);
  //There's a difference between "not there" undefined and actually set to undefined....
  if (groupcues.value[sc][v] == undefined) {
    //Placeholder so we can at least show a no cue found message till it arrives
    old_vue_set(groupcues.value[sc], v, undefined);
  }
  if (cueSelectTimeout.value) {
    clearTimeout(cueSelectTimeout.value);
  }
  cueSelectTimeout.value = setTimeout(function () {
    old_vue_set(selectedCues.value, sc, v);
  }, 350);
}
function gotonext(currentcueid, group) {
  if (!confirm_for_group(group)) {
    return;
  }
  let nextcue = cuemeta.value[currentcueid].next;

  let cue = nextcue || cuemeta.value[currentcueid].defaultnext;
  if (!cue) {
    return;
  }
  api_link.send(["add_cue", groupname.value, nextcue]);
  api_link.send(["getcuedata", cue]);

  //There's a difference between "not there" undefined and actually set to undefined....
  if (groupcues.value[cue] == undefined) {
    //Placeholder so we can at least show a no cue found message till it arrives
    set(groupcues.value[groupname.value], cue, undefined);
  }
  setTimeout(function () {
    old_vue_set(selectedCues.value, groupname.value, cue);
  }, 30);
}
function rmcue(cue) {
  if (!confirm("Delete cue?")) {
    return;
  }
  selectedCues.value[groupname.value] = "default";
  api_link.send(["rmcue", cue]);
}

function uploadFileFromElement(e, type) {
  // Type says what to do with it
  let t = document.getElementById(e);

  async function readText(target) {
    const file = target.files.item(0);
    const text = await file.text();

    api_link.send(["fileUpload", text, type]);
  }

  readText(t);
}
function downloadSetup() {
  downloadReqId.value = Math.random().toString();
  api_link.send(["downloadSetup", downloadReqId.value]);
}
function jumptocue(cue, group) {
  if (confirm_for_group(group)) {
    api_link.send(["jumptocue", cue]);
  }
}
function getcuedata(c) {
  api_link.send(["getcuedata", c]);
}
function getcuemeta(c) {
  api_link.send(["getcuemeta", c]);
}
function setnext(sc, cue, v) {
  api_link.send(["setnext", sc, cue, v]);
}

function setprobability(sc, cue, v) {
  api_link.send(["setprobability", sc, cue, v]);
}

function promptsetnumber(cue) {
  api_link.send([
    "setnumber",
    cue,
    Number(prompt("Enter new number for cue.value:")),
  ]);
}

function setnumber(cue, v) {
  api_link.send(["setnumber", cue, v]);
}

function closePreview(s) {
  document.getElementById("soundpreviewdialog").close();
  document.getElementById("soundpreview").pause();
}

function setcrossfade(sc, v) {
  groupmeta.value[sc].crossfade = v;
  api_link.send(["setcrossfade", sc, v]);
}
function setmqtt(sc, v) {
  groupmeta.value[sc].mqttServer = v;
  api_link.send(["setMqttServer", sc, v]);
}

function setmqttfeature(sc, feature, v) {
  api_link.send(["setmqttfeature", sc, feature, v]);
}

function setcommandtag(sc, v) {
  groupmeta.value[sc].commandTag = v;
  api_link.send(["setgroupcommandtag", sc, v]);
}

function setinfodisplay(sc, v) {
  groupmeta.value[sc].infoDisplay = v;
  api_link.send(["setinfodisplay", sc, v]);
}
function setbpm(sc, v) {
  api_link.send(["setbpm", sc, v]);
}
function tap(sc) {
  api_link.send(["tap", sc, api_link.now() / 1000]);
}
function testSoundCard(sc, c) {
  api_link.send(["testSoundCard", sc, c]);
}

function addGroup() {
  api_link.send(["addgroup", newgroupname.value]);
}

function addRangeEffect(fix) {
  addfixToCurrentCue(
    fix,
    prompt(
      "Bulb # offset(2 represents the first identical fixture after one.value, etc)",
      1
    ),
    prompt(
      "Range effect length(# of identical fixtures to cover with pattern)"
    ),
    prompt(
      "Channel spacing between first channel of successive fixtures(If fix #1 is on DMX1 and fix #2 is on 11, spacing is 10). 0 if spacing equals fixture channel count."
    )
  );
}

function addfixToCurrentCue(fix, idx, len, spacing) {
  //Idx and len are for adding range patters to an array of identical fixtures.
  //Otherwise they should be one
  idx = parseInt(idx);

  if (idx != 1) {
    fix = fix + "[" + idx + "]";
  }

  api_link.send([
    "add_cuef",
    groupcues.value[groupname.value][selectedCues.value[groupname.value]],
    fix,
    idx,
    len,
    spacing,
  ]);
}
function rmFixCue(cue, fix) {
  api_link.send(["rmcuef", cue, fix]);
}

function addValToCue() {
  if (!newcueu.value) {
    return;
  }
  api_link.send([
    "add_cueval",
    groupcues.value[groupname.value][selectedCues.value[groupname.value]],
    newcueu.value,
    newcuevnumber.value,
  ]);
  if (!Number.isNaN(parseInt(newcuevnumber.value))) {
    newcuevnumber.value = (parseInt(newcuevnumber.value) + 1).toString();
  }
}

function addTagToCue() {
  if (!newcuetag.value) {
    return;
  }
  api_link.send([
    "add_cueval",
    groupcues.value[groupname.value][selectedCues.value[groupname.value]],
    newcuetag.value,
    "value",
  ]);
}
function editMode() {
  keyboardJS.reset();
  keybindmode.value = "edit";
}
function runMode() {
  rebindKeys();
  keybindmode.value = "run";
}
function refreshPorts() {
  api_link.send(["getserports"]);
}
function pushSettings() {
  api_link.send(["setconfuniverses", configuredUniverses.value]);
}

function newCueFromSlide(sc, i) {
  api_link.send(["newFromSlide", sc, i]);
}

function newCueFromSound(sc, i) {
  api_link.send(["newFromSound", sc, i]);
}

function setEventButtons(sc, i) {
  api_link.send(["seteventbuttons", sc, i]);
}
function setTagInputValue(sc, tag, v) {
  api_link.send(["inputtagvalue", sc, tag, v]);
}

function _currentcue() {
  if (selectedCues.value[groupname.value] == undefined) {
    return null;
  }
  return cuemeta.value[
    groupcues.value[groupname.value][selectedCues.value[groupname.value]]
  ];
}

let currentcue = Vue.computed(_currentcue);

function _currentcueid() {
  if (selectedCues.value[groupname.value] == undefined) {
    return null;
  }
  return groupcues.value[groupname.value][selectedCues.value[groupname.value]];
}

let currentcueid = Vue.computed(_currentcueid);

function _formatCues() {
  var z = {};
  var filt = true;
  //list cue objects
  for (var i in groupcues.value[groupname.value]) {
    var m = cuemeta.value[groupcues.value[groupname.value][i]];
    if (m !== undefined) {
      if (!filt | i.includes(cuefilter.value)) {
        z[i] = m;
      }
    }
  }
  if (!filt) {
    formattedCues.value = dictView(
      z,
      ["number"],
      undefined,
      cuePage.value[groupname.value]
    ).filter((item) => item[1].id);
    return formattedCues.value;
  } else {
    return dictView(
      z,
      ["number"],
      undefined,
      cuePage.value[groupname.value]
    ).filter((item) => item[1].id);
  }
}

let formatCues = Vue.computed(_formatCues);

function _formatAllGroups() {
  /*Sorted list of group objects*/
  var flt = groupfilter.value;
  var x = dictView(groupmeta.value, ["!priority", "!started", "name"]).filter(
    function (x) {
      return x[1].name && x[1].name.includes(flt);
    }
  );
  return x;
}
let formatAllGroups = Vue.computed(_formatAllGroups);

function _formatGroups() {
  var flt = groupfilter.value;

  return dictView(groupmeta.value, ["!priority", "!started", "name"]).filter(
    function (x) {
      return x[1].name && x[1].name.includes(flt) && !x[1].hide;
    }
  );
}
let formatGroups = Vue.computed(_formatGroups);

window.boardname = window.location.pathname.split("/")[3];

//https://stackoverflow.com/questions/6312993/javascript-seconds-to-time-string-with-format-hhmmss
let boardname = Vue.ref(window.location.pathname.split("/")[3]);
let clock = Vue.ref("time_should_be_here");
let sc_code = Vue.ref("");
let serports = Vue.ref([]);
let shortcuts = Vue.ref([]);
//Index by name
let fixtureAssignments = Vue.ref({});
let newfixname = Vue.ref("");
let newfixtype = Vue.ref("");
let newfixaddr = Vue.ref("");
let newfixuniverse = Vue.ref("");
//Fixture error info str
let ferrs = Vue.ref("");
let evfilt = Vue.ref("");
let newcueu = Vue.ref("");
let newcuetag = Vue.ref("");
let newcuevnumber = Vue.ref("");
let newgroupname = Vue.ref("");
//For each group what page are we on
let cuePage = Vue.ref({});
let nuisianceRateLimit = Vue.ref([10, Date.now()]);

let previousSerializedPromise = Vue.ref(null);

let no_edit = Vue.ref(!kaithemapi.checkPermission("system_admin"));

// Sorted from most to least recent
let recentEventsLog = Vue.ref([["Page Load", formatTime(Date.now() / 1000)]]);
let soundCards = Vue.ref({});

//What universe if any to show the full settings page for
let universeFullSettings = Vue.ref(false);

let fixtureassg = Vue.ref("");

let availableTags = Vue.ref({});
let midiInputs = Vue.ref([]);
let blendModes = Vue.ref([]);

let soundfolders = Vue.ref([]);
let showimportexport = Vue.ref(false);

let grouptab = Vue.ref("cue");
let configuredUniverses = Vue.ref({
  blah: { type: "enttec", interface: "xyz" },
});

let fixtureClasses = Vue.ref({});

//Filter which groups are shown in the list
let groupfilter = Vue.ref("");
let cuefilter = Vue.ref("");
let keybindmode = Vue.ref("edit");
//Keep track of what timers are running in a group
let grouptimers = Vue.ref({});
//Formatted for display
let cuevals = Vue.ref({});
let slideshow_telemetry = Vue.ref({});
let showslideshowtelemetry = Vue.ref(false);
function formatCueVals(c) {
  //Return a simplified version of the data in cuevals
  //Meant for direct display
  let op = {};
  for (var i in c) {
    op[i] = {};
    for (var j in c[i]) {
      op[i][j] = c[i][j].v;
    }
  }
  return op;
}

function doRateLimit() {
  nuisianceRateLimit.value[0] +=
    (Date.now() - nuisianceRateLimit.value[1]) / 180000;
  nuisianceRateLimit.value[0] = Math.min(12, nuisianceRateLimit.value[0]);
  if (nuisianceRateLimit.value[0] > 0) {
    nuisianceRateLimit.value[0] -= 1;
    return true;
  }
}

function lookupFixtureType(f) {
  for (var i in fixtureAssignments.value) {
    if ("@" + fixtureAssignments.value[i].name == f) {
      return fixtureAssignments.value[i].type;
    }
  }
  return "";
}

function lookupFixtureColorProfile(f) {
  // If fixture has no color profile, the profile is just the type
  let x = "";
  for (var i in fixtureAssignments.value) {
    if ("@" + fixtureAssignments.value[i].name == f) {
      x = fixtureAssignments.value[i].type;
      break;
    }
  }
  if (x.length > 0) {
    let c = fixtureClasses.value[x];
    if (c) {
      if (c.color_profile && c.color_profile.length > 0) {
        return c.color_profile;
      }
    }
  }
  return x;
}
function getfixtureassg() {
  api_link.send(["getfixtureassg"]);
}

function getChannelCompletions(u) {
  var x = configuredUniverses.value[u];
  if (x) {
    return useBlankDescriptions(x.channelConfig);
  }
}

function promptRename(s) {
  var x = prompt(
    "Enter new name for group(May break existing references to group)"
  );

  if (x != null) {
    api_link.send(["setgroupname", s, x]);
  }
}

function promptRenameCue(sc, s) {
  var x = prompt(
    "Enter new name for cue(May break existing references to cue)"
  );

  if (x != null) {
    api_link.send(["rename_cue", sc, s, x]);
  }
}
function deleteUniverse(u) {
  console.log(u);
  old_vue_delete(configuredUniverses.value, u);
}

function deletePreset(p) {
  if (confirm("Really Delete")) {
    delete presets.value[p];
    api_link.send(["preset", p, null]);
  }
}

function addTimeToGroup(group) {
  var t = prompt("Add minutes?");
  if (t) {
    api_link.send(["addTimeToGroup", group, t]);
  }
}

function renamePreset(p) {
  var n = prompt("Preset Name?");

  if (n && n.length) {
    var b = presets.value[p];
    if (b) {
      delete presets.value[p];
      api_link.send(["preset", p, null]);

      presets.value[n] = b;
      api_link.send(["preset", n, b]);
    }
  }
}

function copyPreset(p) {
  var n = prompt("Copy to name?");

  if (n && n.length) {
    var b = presets.value[p];
    if (b) {
      presets.value[n] = JSON.parse(JSON.stringify(b));
      api_link.send(["preset", n, b]);
    }
  }
}

function savePreset(v, suggestedname) {
  /*Prompt saving data from the cuevals dict as a preset*/

  var n = prompt("Preset Name?", suggestedname || "");
  console.log("Saving preset", n, v);

  var v2 = presets.value[n] || {};
  v2.values = {};

  // Just the vals
  for (var i in v) {
    if (i == "__length__") {
      continue;
    }
    if (i == "__spacing__") {
      continue;
    }
    if (i == "__preset__") {
      continue;
    }

    v2.values[i] = v[i].v;
  }

  if (n && n.length) {
    presets.value[n] = v2;
    api_link.send(["preset", n, v2]);
  }
}

async function debugCueLen(cuelenstr, force) {
  if (!force) {
    if (!isNaN(parseFloat(cuelenstr))) {
      return;
    }
  }

  let x = fetch("/chandler/api/eval-cue-length?rule=" + cuelenstr, {
    method: "GET",
  });

  x = await x;
  alert(
    "Cue len: " +
      cuelenstr +
      ". If cue started now, it would end at " +
      (await x.text())
  );
}
function getPresetImage(preset) {
  // Can use generic preset image if specific not available
  if (presets.value[preset]?.label_image) {
    return presets.value[preset]?.label_image;
  }

  if (presets.value[preset.split("@")[0]]?.label_image) {
    return presets.value[preset.split("@")[0]]?.label_image;
  }
  return "1x1.png";
}

function updatePreset(i, v) {
  /*Update given a name and the modified data as would be found in the presets file*/
  presets.value[i] = v;
  api_link.send(["preset", i, v]);
}

function channelInfoForUniverseChannel(u, c) {
  if (channelInfoByUniverseAndNumber.value[u] == undefined) {
    return undefined;
  }
  if (channelInfoByUniverseAndNumber.value[u][c] == undefined) {
    return undefined;
  }

  return channelInfoByUniverseAndNumber.value[u][c][1];
}

// Current time as float seconds, updated periodically
let unixtime = Vue.ref(Date.now() / 1000);

//All alarms active on server
let sys_alerts = Vue.ref({});

function handleCueInfo(id, cue) {
  //Make an empty list of cues if it's not there yet
  if (groupcues.value[cue.group] == undefined) {
    old_vue_set(groupcues.value, cue.group, {});
  }
  old_vue_set(groupcues.value[cue.group], cue.name, id);

  //Make an empty list of cues as a placeholder till the real data arrives
  if (cuemeta.value[id] == undefined) {
    old_vue_set(cuemeta.value, id, {});
  }
  set(cuemeta.value, id, cue);
}

let downloadReqId = Vue.ref("");

function handleServerMessage(v) {
  let c = v[0];

  if (c == "soundfolders") {
    soundfolders.value = v[1];
  } else if (c == "ui_alert") {
    playAlert(v[1]);
  } else if (c == "slideshow_telemetry") {
    if (v[2] == null) {
      delete slideshow_telemetry.value[v[1]];
    } else {
      if (v[2].status != (slideshow_telemetry.value[v[1]] || {}).status) {
        if (v[2].status.includes("FAILED")) {
          if (doRateLimit.value()) {
            errorTone("A slideshow display may need attention");
            showslideshowtelemetry.value = true;
          }
        }
      }

      slideshow_telemetry.value[v[1]] = v[2];
    }
  } else if (c == "grouptimers") {
    if (groupmeta.value[v[1]]) {
      groupmeta.value[v[1]].timers = v[2];
    }
  } else if (c == "cuehistory") {
    groupmeta.value[v[1]].history = v[2];
  } else if (c == "groupmeta") {
    if (v[2].cue) {
      if (cuemeta.value[v[2].cue] == undefined) {
        getcuemeta(v[2].cue);
      }
    }

    if (v[2].alpha != undefined) {
      old_vue_set(alphas.value, v[1], v[2].alpha);
    }

    //Just update existing data if we can
    if (groupmeta.value[v[1]]) {
      set(groupmeta.value, v[1], v[2]);
    } else {
      var meta = v[2];
      set(groupmeta.value, v[1], meta);
    }

    if (selectedCues.value[v[1]] == undefined) {
      old_vue_set(selectedCues.value, v[1], "default");
    }
    //Make an empty list of cues as a placeholder till the real data arrives
    if (groupcues.value[v[1]] == undefined) {
      old_vue_set(groupcues.value, v[1], {});
    }
  } else if (c == "cuemeta") {
    handleCueInfo(v[1], v[2]);
  } else if (c == "event") {
    recentEventsLog.value.unshift(v[1]);
    if (recentEventsLog.value.length > 250) {
      recentEventsLog.value = recentEventsLog.value.slice(-250);
    }

    if (v[1][0].includes("error")) {
      const event = new Event("servererrorevent");
      window.dispatchEvent(event);
      errorTone("");
    }
  } else if (c == "serports") {
    serports.value = v[1];
  } else if (c == "alerts") {
    if (JSON.stringify(sys_alerts.value) != JSON.stringify(v[1])) {
      if (v[1]) {
        errorTone();
      }
    }

    sys_alerts.value = v[1];
  } else if (c == "confuniverses") {
    configuredUniverses.value = v[1];
  } else if (c == "universe_status") {
    universes.value[v[1]].status = v[2];
    universes.value[v[1]].ok = v[3];
    universes.value[v[1]].telemetry = v[4];
  } else if (c == "varchange") {
    if (groupmeta.value[v[1]]) {
      groupmeta.value[v[1]]["vars"][v[2]] = v[3];
    }
  } else if (c == "delcue") {
    c = cuemeta.value[v[1]];
    old_vue_delete(cuemeta.value, v[1]);
    old_vue_delete(cuevals.value, v[1]);
    old_vue_delete(groupcues.value[c.group], c.name);
  } else if (c == "cnames") {
    old_vue_set(channelInfoByUniverseAndNumber.value, v[1], v[2]);
  } else if (c == "universes") {
    universes.value = v[1];
  } else if (c == "soundoutputs") {
    soundCards.value = v[1];
  } else if (c == "soundsearchresults") {
    const event = new Event("onsoundsearchresults");
    event.data = [v[1], v[2]];
    window.dispatchEvent(event);
  } else if (c == "cuedata") {
    let d = {};
    old_vue_set(cuevals.value, v[1], d);

    for (var i in v[2]) {
      if (!(i in channelInfoByUniverseAndNumber.value)) {
        api_link.send(["getcnames", i]);
      }
      old_vue_set(cuevals.value[v[1]], i, {});

      for (var j in v[2][i]) {
        let y = {
          u: i,
          ch: j,
          v: v[2][i][j],
        };
        old_vue_set(cuevals.value[v[1]][i], j, y);
        //The other 2 don't need to be reactive, v does
        old_vue_set(y, "v", v[2][i][j]);
      }
    }
  } else if (c == "commands") {
    availableCommands.value = v[1];
  } else if (c == "scv") {
    let cue = v[1];
    let universe = v[2];
    let channel = v[3];
    let value = v[4];

    //Empty universe dict, we are not set up to listen to yet.value
    if (!cuevals.value[cue]) {
      return;
    }
    if (!cuevals.value[cue][universe]) {
      cuevals.value[cue][universe] = {};
    }

    if (v[4] !== null) {
      let y = {
        u: universe,
        ch: channel,
        v: value,
      };
      old_vue_set(y, "v", value);
      old_vue_set(cuevals.value[cue][universe], channel, y);
    } else {
      old_vue_delete(cuevals.value[cue][universe], channel);
    }

    if (Object.entries(cuevals.value[cue][universe]).length == 0) {
      old_vue_delete(cuevals.value[cue], universe);
    }
  } else if (c == "go") {
    old_vue_set(groupmeta.value[v[1]], "active", true);
  } else if (c == "refreshPage") {
    window.reload();
  } else if (c == "stop") {
    old_vue_set(groupmeta.value[v[1]], "active", false);
  } else if (c == "ferrs") {
    ferrs.value = v[1];
  } else if (c == "fixtureclasses") {
    fixtureClasses.value = v[1];
  } else if (c == "fixtureclass") {
    if (v[2] == null) {
      old_vue_delete(fixtureClasses.value, v[1]);
    } else {
      old_vue_set(fixtureClasses.value, v[1], v[2]);
    }
  } else if (c == "fixtureAssignments") {
    fixtureAssignments.value = v[1];
  } else if (c == "del") {
    old_vue_delete(selectedCues.value, v[1]);
    old_vue_delete(groupmeta.value, v[1]);
    editingGroup.value = null;
  } else if (c == "soundfolderlisting") {
    // Handled in media-browser.vue
    const event = new Event("onsoundfolderlisting");
    event.data = [v[1], v[2]];
    window.dispatchEvent(event);
  } else if (c == "fixturePresets") {
    presets.value = v[1];
  } else if (c == "preset") {
    presets.value[v[1]] = v[2];
  } else if (c == "fileDownload") {
    if (v[1] == downloadReqId.value) {
      const file = new File([v[2]], v[3], {
        type: "text/plain",
      });

      const link = document.createElement("a");
      const url = URL.createObjectURL(file);

      link.href = url;
      link.download = file.name;
      document.body.appendChild(link);
      link.click();

      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    }
  } else if (c == "shortcuts") {
    shortcuts.value = v[1];
  } else if (c == "availableTags") {
    availableTags.value = v[1];
  } else if (c == "midiInputs") {
    midiInputs.value = v[1];
  } else if (c == "blendModes") {
    blendModes.value = v[1];
  }
}

async function initChandlerVueModel(board) {
  await initializeState(board);

  api_link.upd = handleServerMessage;
  api_link.send(["get_state"]);
  api_link.send(["getCommands"]);

  // Exact sync on half seconds
  function unix_time_upd() {
    unixtime.value = api_link.now() / 1000;
    setTimeout(unix_time_upd, 10000 - (api_link.now() % 10000));
  }

  unix_time_upd();

  function clock_upd() {
    var c = new Date(api_link.now()).toLocaleTimeString();
    const el = document.getElementById("toolbar-clock");
    if (el) {
      el.innerHTML = c;
    }

    setTimeout(clock_upd, 1000 - (api_link.now() % 1000));
  }

  clock_upd();

  var update_meters = function () {
    var u = api_link.now() / 1000;

    for (var i of document.querySelectorAll("[data-meter-ref]")) {
      i.value = u - parseFloat(i.dataset.meterRef);
    }

    for (var i of document.querySelectorAll("[data-count-ref]")) {
      let l =
        parseFloat(i.dataset.countLen) * (60 / parseFloat(i.dataset.countBpm));
      let e = parseFloat(i.dataset.countRef) + l;

      i.innerHTML = formatInterval(e - u);
    }
  };
  setInterval(update_meters, 200);
}

function confirm_for_group(sc) {
  if (groupmeta.value[sc].requireConfirm) {
    if (confirm("Confirm Action for Group: " + groupmeta.value[sc].name)) {
      return true;
    }
  } else {
    return true;
  }
}

function next(sc) {
  return function () {
    api_link.send(["nextcuebyname", sc]);
  };
}
function goto(sc, cue) {
  return function () {
    api_link.send(["jumpbyname", sc, cue]);
  };
}

var script = document.createElement("script");
script.onload = function () {
  const boardname = window.location.pathname.split("/")[3];
  initChandlerVueModel(boardname);
};

let api_link = new APIWidget("WebChandlerConsole:" + boardname.value);
window.api_link = api_link;

export {
  api_link,
  initChandlerVueModel,
  // Computed method helpers
  formatGroups,
  formatAllGroups,
  formatCues,
  currentcue,
  currentcueid,

  // used to be in appData
  sys_alerts,
  unixtime,
  boardname,
  formatInterval,
  clock,
  sc_code,
  serports,
  shortcuts,
  fixtureAssignments,
  newfixname,
  newfixtype,
  newfixaddr,
  newfixuniverse,
  ferrs,
  evfilt,
  newcueu,
  newcuetag,
  newcuevnumber,
  newgroupname,
  cuePage,
  nuisianceRateLimit,
  previousSerializedPromise,
  no_edit,
  recentEventsLog,
  soundCards,
  universeFullSettings,
  fixtureassg,
  availableTags,
  midiInputs,
  blendModes,
  soundfolders,
  showimportexport,
  grouptab,
  configuredUniverses,
  fixtureClasses,
  groupfilter,
  cuefilter,
  keybindmode,
  grouptimers,
  cuevals,
  useBlankDescriptions,
  slideshow_telemetry,
  showslideshowtelemetry,
  dictView,
  alphas,
  groupmeta,
  groupname,
  editingGroup,
  universes,
  cues,
  newcuename,
  cuemeta,
  availableCommands,
  selectedCues,
  showPages,
  uiAlertSounds,
  cueSelectTimeout,
  groupcues,
  formattedCues,
  channelInfoByUniverseAndNumber,
  presets,

  // methods
  setGroupProperty,
  setCueProperty,
  setCuePropertyDeferred,
  setGroupPropertyDeferred,
  saveToDisk,
  sendGroupEventWithConfirm,
  refreshhistory,
  setCueVal,
  selectcue,
  selectgroup,
  delgroup,
  go,
  shortcut,
  stop,
  setalpha,
  nextcue,
  prevcue,
  add_cue,
  clonecue,
  gotonext,
  rmcue,
  uploadFileFromElement,
  downloadSetup,
  jumptocue,
  setnext,
  setprobability,
  promptsetnumber,
  setnumber,
  closePreview,
  setcrossfade,
  setmqtt,
  setmqttfeature,
  setcommandtag,
  setinfodisplay,
  setbpm,
  tap,
  testSoundCard,
  addGroup,
  addRangeEffect,
  addfixToCurrentCue,
  rmFixCue,
  addValToCue,
  addTagToCue,
  editMode,
  runMode,
  refreshPorts,
  pushSettings,
  newCueFromSlide,
  newCueFromSound,
  setEventButtons,
  setTagInputValue,
  addTimeToGroup,
  formatCueVals,
  lookupFixtureType,
  lookupFixtureColorProfile,
  getfixtureassg,
  getChannelCompletions,
  promptRename,
  promptRenameCue,
  deleteUniverse,
  deletePreset,
  renamePreset,
  copyPreset,
  savePreset,
  getPresetImage,
  updatePreset,
  channelInfoForUniverseChannel,
  debugCueLen,
  next,
  goto,
};
