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
} from "./utils.mjs";
import {
  kaithemapi,
  APIWidget,
} from "/static/js/widget.mjs?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0";
import picodash from '/static/js/thirdparty/picodash/picodash-base.esm.js'

import { computed, ref, toRaw } from "/static/js/thirdparty/vue.esm-browser.js";

let keysdown = {};

//Current per group alpha channel
let alphas = ref({});
let groupmeta = ref({});
let groupname = ref(null);
let editingGroup = ref(null);
let universes = ref({});
let cues = ref({});
let newcuename = ref("");
let cuemeta = ref({});
let availableCommands = ref({});
// per scene user selected for editing
let selectedCues = ref({});
let showPages = ref(false);
let uiAlertSounds = ref(true);
// Used for things that auto select cues after a delay to set things
// up but also are cancelable.
let cueSelectTimeout = ref(0);
//go from cue name to cue id
//groupcues[groupuuid][cuename]=cueid
let groupcues = ref({});
let formattedCues = ref([]);
//Indexed by universe then channel number
let channelInfoByUniverseAndNumber = ref({});
//same info as groupvals, indexed hierarchally, as [universe][channel]
//Actual objs are shared too so changing one obj change in in the other.

let presets = ref({});

function keyHandle(event_) {
  if (keysdown[event_.key] != undefined && keysdown[event_.key]) {
    return;
  }
  keysdown[event_.key] = true;
  event_.preventRepeat();
  api_link.send(["event", "keydown." + event_.key, 1, "int", "__global__"]);
}
function keyUpHandle(event_) {
  if (keysdown[event_.key] != undefined && !keysdown[event_.key]) {
    return;
  }
  keysdown[event_.key] = false;
  api_link.send(["event", "keyup." + event_.key, 1, "int", "__global__"]);
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
    picodash.snackbar.createSnackbar(m, {
      timeout: 60 * 1000,
    });
  }
}

function errorTone(m) {
  if (uiAlertSounds.value) {
    var mp3_url =
      "/static/sounds/423166__plasterbrain__minimalist-sci-fi-ui-error.opus";
    new Audio(mp3_url).play().catch(() => {});
  }
  if (m) {
    picodash.snackbar.createSnackbar(m,
      {
        accent: "error",
        timeout: 60 * 1000,
      }
    );
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

  for (var index in v) {
    handleCueInfo(index, v[index]);
  }
}

let cueSetData = {};

function triggerShortcut(sc) {
  api_link.send(["shortcut", sc]);
}

// Slowly we want to migrate to these two generic setters
async function setGroupProperty(group, property, value) {
  await doSerialized(async () => {
    var x = cueSetData[group + property];
    if (x) {
      clearTimeout(x);
      delete cueSetData[group + property];
    }
    var b = {};
    b[property] = value;

    let response = fetch("/chandler/api/set-group-properties/" + group, {
      method: "PUT",
      body: JSON.stringify(b),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
      },
    }).catch(function (error) {
      alert("Could not reach server:" + error);
    });

    let v = await response;

    if (!v.ok) {
      alert("Error setting property, possible invalid value: " + value);
    }
  });
}

async function restSetCueValue(cue, universe, channel, value) {
  await doSerialized(async () => {
    var x = cueSetData[cue + "value"];
    if (x) {
      clearTimeout(x);
      delete cueSetData[cue + "value"];
    }

    let response = fetch(
      "/chandler/api/set-cue-value/" +
        cue +
        "/" +
        universe +
        "/" +
        channel +
        "?" +
        new URLSearchParams({ value: JSON.stringify(value) }).toString(),
      {
        method: "PUT",
      }
    ).catch(function (error) {
      alert("Could not reach server:" + error);
    });

    let v = await response;

    if (!v.ok) {
      alert("Error setting value, possible invalid value: " + value);
    }
  });
}

async function setCueProperty(cue, property, value) {
  await doSerialized(async () => {
    var x = cueSetData[cue + property];
    if (x) {
      clearTimeout(x);
      delete cueSetData[cue + property];
    }

    var b = {};
    b[property] = value;

    let p = fetch("/chandler/api/set-cue-properties/" + cue, {
      method: "PUT",
      body: JSON.stringify(b),
      headers: {
        "Content-type": "application/json; charset=UTF-8",
      },
    });

    try {
      let r = await p;
      if (!r.ok) {
        alert("Error setting property, possible invalid value: " + value);
      }
    } catch (error) {
      alert("Could not reach server: " + error);
    }
  });
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
    }).catch(function (error) {
      alert("Error setting property: " + error);
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
    }).catch(function (error) {
      alert("Error setting property: " + error);
    });
    delete cueSetData[group + property];
  }, 3000);
}

function saveToDisk() {
  api_link.send(["saveState"]);
}

function sendGroupEventWithConfirm(event_, where) {
  if (confirm_for_group(where)) {
    api_link.send(["event", event_, "", "str", where]);
  }
}

function refreshhistory(sc) {
  api_link.send(["getcuehistory", sc]);
}

async function setCueValue(sc, u, ch, value) {
  if (globalThis.testMode) {
    await restSetCueValue(sc, u, ch, value);
    return;
  }
  if (cuevals.value?.[sc]?.[u]?.["__preset__"]) {
    api_link.send(["scv", sc, u, "__preset__", null]);
  }

  value = Number.isNaN(Number.parseFloat(value))
    ? value
    : Number.parseFloat(value);
  api_link.send(["scv", sc, u, ch, value]);
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

async function delgroup(group) {
  var r = confirm("Really delete group?");
  if (r == true) {
    await doSerialized(async () => {
      let result = fetch(
        "/chandler/api/delete-group/" + boardname.value + "/" + group, {
          method: "PUT",
        }
      ).catch(function (error) {
        alert("Could not reach server:" + error);
      });

      let result2 = await result;
      if (!result2.ok) {
        {
          alert("Error deleting group: " + result.statusText);
        }
      }
    });
  }
}

async function go(group) {
  await doSerialized(async () => {
    const result = fetch("/chandler/api/group-go/" + group,
      {
        method: "PUT",
      }
    ).catch(
      function (error) {
        alert("Could not reach server:" + error);
      }
    );
    const result2 = await result;
    if (!result2.ok) {
      alert("Error activating group: " + result.statusText);
    }
  });
}

async function stop(group) {
  var x = confirm(
    "Really stop group? The cue and all variables will be reset."
  );

  if (x) {
    const result = fetch("/chandler/api/group-stop/" + group,
      {
        method: "PUT",
      }
    ).catch(
      function (error) {
        alert("Could not reach server:" + error);
      }
    );
    const result2 = await result;
    if (!result2.ok) {
      alert("Error activating group: " + result.statusText);
    }  }
}

function setalpha(sc, v) {
  api_link.send(["setalpha", sc, v]);
  alphas.value[sc] = v;
}

function gotoNextCue(sc) {
  if (confirm_for_group(sc)) {
    api_link.send(["gotoNextCue", sc]);
  }
}

function gotoPreviousCue(sc) {
  if (confirm_for_group(sc)) {
    api_link.send(["gotoPreviousCue", sc]);
  }
}

function add_cue(sc, v, after_cue) {
  api_link.send(["add_cue", sc, v, Number.parseFloat(after_cue.number) * 1000]);
  //There's a difference between "not there" undefined and actually set to undefined....
  if (groupcues.value[sc][v] == undefined) {
    //Placeholder so we can at least show a no cue found message till it arrives
    old_vue_set(groupcues.value[sc], v);
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
    old_vue_set(groupcues.value[sc], v);
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


async function jumpToCueWithConfirmationIfNeeded(cueid, group) {

  if(!groupmeta.value[group].active) {
    // picodash.snackbar.createSnackbar("Group is not active", {
    //   timeout: 3000,
    //   accent: "error"
    // });

    alert("Group is not active");
    return;
  }
  if (confirm_for_group(group)) {
    await doSerialized(async () => {
      const result = fetch(
        "/chandler/api/go-to-cue-by-cue-id/" + cueid,
        {
          method: "PUT",
        }
      ).catch(function (error) {
        alert("Could not reach server:" + error);
      });
      const result2 = await result;
      if (!result2.ok) {
        alert("Error activating cue: " + result.statusText);
      }
    });
  }
}

const gettingCueDataPromises = {};
async function getcuedata(c) {
  await doSerialized(async () => {
    const p = new Promise((resolve, _reject) => {
      gettingCueDataPromises[c] = resolve;
    });
    const timeoutPromise = new Promise((_resolve, reject) => {
      setTimeout(() => {
        reject();
      }, 5000);
    });
    api_link.send(["getcuedata", c]);
    try {
      await Promise.race([p, timeoutPromise]);
    } catch (error) {
      console.log("Error getting cue data", error);
    }
  });
}

const gettingCueMetaPromises = {};

async function getcuemeta(c) {
  await doSerialized(async () => {
    const p = new Promise((_resolve, _reject) => {
      gettingCueMetaPromises[c] = _resolve;
    });
    const timeoutPromise = new Promise((_resolve, reject) => {
      setTimeout(() => {
        reject();
        alert("Timeout waiting for cue data.");
      }, 5000);
    });
    api_link.send(["getcuemeta", c]);
    try {
      await Promise.race([p, timeoutPromise]);
    } catch (error) {
      console.log("Error getting cue data", error);
    }
  });
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

function addfixToCurrentCue(fix, index, length_, spacing) {
  //Idx and len are for adding range patters to an array of identical fixtures.
  //Otherwise they should be one
  index = Number.parseInt(index);

  if (index != 1) {
    fix = fix + "[" + index + "]";
  }

  api_link.send([
    "add_cuef",
    groupcues.value[groupname.value][selectedCues.value[groupname.value]],
    fix,
    index,
    length_,
    spacing,
  ]);
}
function rmFixCue(cue, fix) {
  api_link.send(["rmcuef", cue, fix]);
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

function newCueFromSlide(sc, index) {
  api_link.send(["newFromSlide", sc, index]);
}

function newCueFromSound(sc, index) {
  api_link.send(["newFromSound", sc, index]);
}

function setEventButtons(sc, index) {
  api_link.send(["seteventbuttons", sc, index]);
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

let currentcue = computed(_currentcue);

function _currentcueid() {
  if (selectedCues.value[groupname.value] == undefined) {
    return null;
  }
  return groupcues.value[groupname.value][selectedCues.value[groupname.value]];
}

let currentcueid = computed(_currentcueid);

function _formatCues() {
  var z = {};
  var filt = true;
  //list cue objects
  for (var index in groupcues.value[groupname.value]) {
    var m = cuemeta.value[groupcues.value[groupname.value][index]];
    if (m !== undefined && !filt | index.includes(cuefilter.value)) {
      z[index] = m;
    }
  }
  if (filt) {
    return dictView(
      z,
      ["number"],
      undefined,
      cuePage.value[groupname.value]
    ).filter((item) => item[1].id);
  } else {
    formattedCues.value = dictView(
      z,
      ["number"],
      undefined,
      cuePage.value[groupname.value]
    ).filter((item) => item[1].id);
    return formattedCues.value;
  }
}

let formatCues = computed(_formatCues);

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
let formatAllGroups = computed(_formatAllGroups);

function _formatGroups() {
  var flt = groupfilter.value;

  return dictView(groupmeta.value, ["!priority", "!started", "name"]).filter(
    function (x) {
      return x[1].name && x[1].name.includes(flt) && !x[1].hide;
    }
  );
}
let formatGroups = computed(_formatGroups);

globalThis.boardname = globalThis.location.pathname.split("/").at(-1);

//https://stackoverflow.com/questions/6312993/javascript-seconds-to-time-string-with-format-hhmmss
let boardname = ref(globalThis.location.pathname.split("/").at(-1));
let clock = ref("time_should_be_here");
let serports = ref([]);
let shortcuts = ref([]);
//Index by name
let fixtureAssignments = ref({});

//Fixture error info str
let ferrs = ref("");

//For each group what page are we on
let cuePage = ref({});
let nuisianceRateLimit = ref([10, Date.now()]);

// This is a global the whole app can use to await serialized promises.
let previousSerializedPromise = ref(null);

if (globalThis.previousSerializedPromise) {
  previousSerializedPromise = globalThis.previousSerializedPromise;
} else {
  globalThis.previousSerializedPromise = previousSerializedPromise;
}

/*
This function waits until the previous action has completed before
doing the callback.

Timeout does not apply to callback, only waiting for previous actions.
Can call without a callback to just wait for previous actions.

This basically adds each new function to a chain, so if the timeout
on one expires, the next ones can go even if ones before it don't,
so it is pretty much a "soft" approximate serialization.

It mostly exists to allow tests to wait for previous actions.
*/
async function doSerialized(callback, timeout) {
  let previous = previousSerializedPromise.value;

  const f = async () => {
    try {
      if (previous) {
        if (timeout > 0) {
          const timeoutPromise = new Promise((_resolve, reject) => {
            setTimeout(() => {
              reject();
            }, timeout);
          });
          try {
            await Promise.race([previous, timeoutPromise]);
          } catch (error) {
            console.log("Error in previous serialized promise", error);
          }
        } else {
          await previous;
        }
      }
    } catch (error) {
      console.log("Eror in previous serialized promise", error);
    }
    if (callback) {
      return await callback();
    }
  };

  const p = f();
  previousSerializedPromise.value = p;
  return await p;
}

// Used for tests
globalThis.doSerialized = doSerialized;

/*Like doSerialized but also times out on callback, not just
waiting for previous actions*/
async function doSerializedWithTimeout(callback, timeout) {
  const timeoutPromise = new Promise((_resolve, reject) => {
    setTimeout(() => {
      reject();
      alert("Timeout waiting for action.");
    }, timeout);
  });

  return doSerialized(
    () => Promise.race([callback(), timeoutPromise]),
    timeout
  );
}

let no_edit = ref(!kaithemapi.checkPermission("system_admin"));

// Sorted from most to least recent
let recentEventsLog = ref([["Page Load", formatTime(Date.now() / 1000)]]);
let soundCards = ref({});

//What universe if any to show the full settings page for
let universeFullSettings = ref(false);

let fixtureassg = ref("");

let availableTags = ref({});
let midiInputs = ref([]);
let blendModes = ref([]);

let soundfolders = ref([]);

let groupChannelsViewMode = ref("cue");
let configuredUniverses = ref({
  blah: { type: "enttec", interface: "xyz" },
});

let fixtureClasses = ref({});

//Filter which groups are shown in the list
let groupfilter = ref("");
let cuefilter = ref("");
let keybindmode = ref("edit");
//Keep track of what timers are running in a group
let grouptimers = ref({});
//Formatted for display
let cuevals = ref({});
let slideshow_telemetry = ref({});
let showslideshowtelemetry = ref(false);
function formatCueVals(c) {
  //Return a simplified version of the data in cuevals
  //Meant for direct display
  let op = {};
  for (var index in c) {
    op[index] = {};
    for (var index_ in c[index]) {
      op[index][index_] = c[index][index_].v;
    }
  }
  return op;
}

function doRateLimit() {
  nuisianceRateLimit.value[0] +=
    (Date.now() - nuisianceRateLimit.value[1]) / 180_000;
  nuisianceRateLimit.value[0] = Math.min(12, nuisianceRateLimit.value[0]);
  if (nuisianceRateLimit.value[0] > 0) {
    nuisianceRateLimit.value[0] -= 1;
    return true;
  }
}

function lookupFixtureType(f) {
  for (var index in fixtureAssignments.value) {
    if ("@" + fixtureAssignments.value[index].name == f) {
      return fixtureAssignments.value[index].type;
    }
  }
  return "";
}

function lookupFixtureColorProfile(f) {
  // If fixture has no color profile, the profile is just the type
  let x = "";
  for (var index in fixtureAssignments.value) {
    if ("@" + fixtureAssignments.value[index].name == f) {
      x = fixtureAssignments.value[index].type;
      break;
    }
  }
  if (x.length > 0) {
    let c = fixtureClasses.value[x];
    if (c && c.color_profile && c.color_profile.length > 0) {
      return c.color_profile;
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

  if (n && n.length > 0) {
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

  if (n && n.length > 0) {
    var b = presets.value[p];
    if (b) {
      presets.value[n] = structuredClone(toRaw(b));
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
  for (var index in v) {
    if (index == "__length__") {
      continue;
    }
    if (index == "__spacing__") {
      continue;
    }
    if (index == "__preset__") {
      continue;
    }

    v2.values[index] = v[index].v;
  }

  if (n && n.length > 0) {
    presets.value[n] = v2;
    api_link.send(["preset", n, v2]);
  }
}

async function notifyPopupComputedCueLengthgth(cuelenstr, force) {
  if (!force && !Number.isNaN(Number.parseFloat(cuelenstr))) {
    return;
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

function updatePreset(index, v) {
  /*Update given a name and the modified data as would be found in the presets file*/
  presets.value[index] = v;
  api_link.send(["preset", index, v]);
}

function channelInfoForUniverseChannel(u, c) {
  if (channelInfoByUniverseAndNumber.value[u] == undefined) {
    return;
  }
  if (channelInfoByUniverseAndNumber.value[u][c] == undefined) {
    return;
  }

  return channelInfoByUniverseAndNumber.value[u][c][1];
}

// Current time as float seconds, updated periodically
let unixtime = ref(Date.now() / 1000);

//All alarms active on server
let sys_alerts = ref({});

function handleCueInfo(id, cue) {
  if (cue == null) {
    if (cuemeta.value[id] != undefined) {
      delete cuemeta.value[id];
    }
    return;
  }

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

let downloadRequestId = ref("");

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
      if (
        v[2].status != (slideshow_telemetry.value[v[1]] || {}).status &&
        v[2].status.includes("FAILED") &&
        doRateLimit()
      ) {
        errorTone("A slideshow display may need attention");
        showslideshowtelemetry.value = true;
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
    if (v[2].cue && cuemeta.value[v[2].cue] == undefined) {
      getcuemeta(v[2].cue);
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
    if (gettingCueMetaPromises[v[1]]) {
      gettingCueMetaPromises[v[1]]();
      delete gettingCueMetaPromises[v[1]];
    }
    handleCueInfo(v[1], v[2]);
  } else if (c == "event") {
    recentEventsLog.value.unshift(v[1]);
    if (recentEventsLog.value.length > 250) {
      recentEventsLog.value = recentEventsLog.value.slice(-250);
    }

    if (v[1][0].includes("error")) {
      const event = new Event("servererrorevent");
      globalThis.dispatchEvent(event);
      errorTone("");
    }
  } else if (c == "serports") {
    serports.value = v[1];
  } else if (c == "alerts") {
    if (JSON.stringify(sys_alerts.value) != JSON.stringify(v[1]) && v[1]) {
      errorTone();
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
    globalThis.dispatchEvent(event);
  } else if (c == "cuedata") {
    if (gettingCueDataPromises[v[1]]) {
      gettingCueDataPromises[v[1]]();
      delete gettingCueDataPromises[v[1]];
    }

    if (v[2] == null) {
      if (cuevals.value[v[1]]) {
        old_vue_delete(cuevals.value, v[1]);
      }
      return;
    }

    let d = {};
    old_vue_set(cuevals.value, v[1], d);

    for (var index in v[2]) {
      if (!(index in channelInfoByUniverseAndNumber.value)) {
        api_link.send(["getcnames", index]);
      }
      old_vue_set(cuevals.value[v[1]], index, {});

      for (var index_ in v[2][index]) {
        let y = {
          u: index,
          ch: index_,
          v: v[2][index][index_],
        };
        old_vue_set(cuevals.value[v[1]][index], index_, y);
        //The other 2 don't need to be reactive, v does
        old_vue_set(y, "v", v[2][index][index_]);
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

    if (v[4] === null) {
      old_vue_delete(cuevals.value[cue][universe], channel);
    } else {
      let y = {
        u: universe,
        ch: channel,
        v: value,
      };
      old_vue_set(y, "v", value);
      old_vue_set(cuevals.value[cue][universe], channel, y);
    }

    if (Object.entries(cuevals.value[cue][universe]).length === 0) {
      old_vue_delete(cuevals.value[cue], universe);
    }
  } else if (c == "refreshPage") {
    globalThis.reload();
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
    globalThis.dispatchEvent(event);
  } else if (c == "fixturePresets") {
    presets.value = v[1];
  } else if (c == "preset") {
    presets.value[v[1]] = v[2];
  } else if (c == "fileDownload") {
    if (v[1] == downloadRequestId.value) {
      const file = new File([v[2]], v[3], {
        type: "text/plain",
      });

      const link = document.createElement("a");
      const url = URL.createObjectURL(file);

      link.href = url;
      link.download = file.name;
      document.body.append(link);
      link.click();

      link.remove();
      globalThis.URL.revokeObjectURL(url);
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
    setTimeout(unix_time_upd, 10_000 - (api_link.now() % 10_000));
  }

  unix_time_upd();

  function clock_upd() {
    var c = new Date(api_link.now()).toLocaleTimeString();
    const element = document.querySelector("#toolbar-clock");
    if (element) {
      element.innerHTML = c;
    }

    setTimeout(clock_upd, 1000 - (api_link.now() % 1000));
  }

  clock_upd();

  var update_meters = function () {
    var u = api_link.now() / 1000;

    for (let index of document.querySelectorAll("[data-meter-ref]")) {
      index.value = u - Number.parseFloat(index.dataset.meterRef);
    }

    for (let index of document.querySelectorAll("[data-count-ref]")) {
      let durationLength =
        Number.parseFloat(index.dataset.countLen) *
        (60 / Number.parseFloat(index.dataset.countBpm));

      let endTime = Number.parseFloat(index.dataset.countRef) + durationLength;

      index.innerHTML = formatInterval(endTime - u);
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

// Suspected unused
// TODO: remove
function next(sc) {
  return function () {
    api_link.send(["gotoNextCuebyname", sc]);
  };
}

async function goto(group, cue) {
  await doSerialized(async () => {
    const result = fetch(
      "/chandler/api/go-to-cue-by-name/" + group + "/" + cue,
      {
        method: "PUT",
      }
    ).catch(function (error) {
      alert("Could not reach server:" + error);
    });
    const result2 = await result;
    if (!result2.ok) {
      alert("Error activating cue: " + result.statusText);
    }
  });
}

var script = document.createElement("script");
script.addEventListener("load", function () {
  const boardname = globalThis.location.pathname.split("/").at(-1);
  initChandlerVueModel(boardname);
});

let api_link = new APIWidget("WebChandlerConsole:" + boardname.value);
globalThis.api_link = api_link;

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
  clock,
  serports,
  shortcuts,
  fixtureAssignments,
  ferrs,
  cuePage,
  nuisianceRateLimit,
  previousSerializedPromise,
  doSerialized,
  doSerializedWithTimeout,
  no_edit,
  recentEventsLog,
  soundCards,
  universeFullSettings,
  fixtureassg,
  availableTags,
  midiInputs,
  blendModes,
  soundfolders,
  groupChannelsViewMode,
  configuredUniverses,
  fixtureClasses,
  groupfilter,
  cuefilter,
  keybindmode,
  grouptimers,
  cuevals,
  slideshow_telemetry,
  showslideshowtelemetry,
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
  setCueValue as setCueVal,
  selectcue,
  selectgroup,
  delgroup,
  go,
  stop,
  setalpha,
  gotoNextCue,
  gotoPreviousCue,
  add_cue,
  clonecue,
  gotonext,
  rmcue,
  jumpToCueWithConfirmationIfNeeded,
  setnext,
  setprobability,
  promptsetnumber,
  setnumber,
  setcrossfade,
  setmqtt,
  setmqttfeature,
  setcommandtag,
  setinfodisplay,
  setbpm,
  tap,
  testSoundCard,
  addRangeEffect,
  addfixToCurrentCue,
  rmFixCue,
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
  notifyPopupComputedCueLengthgth as notifyPopupComputedCueLength,
  next,
  goto,
  triggerShortcut,
  restSetCueValue,
};

export { formatInterval, useBlankDescriptions, dictView } from "./utils.mjs";
