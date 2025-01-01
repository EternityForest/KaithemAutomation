<style>
.grey {
  color: grey;
  font-size: 70%;
}

.indicator {
  border-radius: 0.2em;
  display: inline-block;
  width: 0.9em;
  height: 0.9em;
  border-style: dashed;
  border-width: 1.5px;
}

.labelbox {
  display: flex;
  flex-wrap: wrap;
}

.break {
  flex-basis: 100%;
  height: 0;
}

.blinking {
  animation: blinkingText 1s infinite;
}

@keyframes blinkingText {
  0% {
    opacity: 0.5;
  }

  50% {
    opacity: 1;
  }

  100% {
    opacity: 0.5;
  }
}

.multibar > * {
  display: inline-flex;
}
</style>

<template id="template">
  <datalist name="colorprofiles" id="colorprofiles">
    <option value="rgb.generic">Typical common RGB LED fixture</option>
    <option value="rgbw.generic">Typical common RGBW LED fixture</option>

    <option value="rgb.generic.2010">
      Typical common RGB LED fixture circa 2010-2020
    </option>
    <option value="rgbw.generic.2010">
      Typical common RGBW LED fixture circa 2010-2020
    </option>

    <option value="rgb.generic.2020">
      Typical common RGB LED fixture circa 2020-2030
    </option>
    <option value="rgbw.generic.2020">
      Typical common RGBW LED fixture circa 2020-2030
    </option>
  </datalist>

  <div id="app" v-cloak class="flex-row gaps">
    <div
      v-if="iframeDialog"
      class="card paper flex-col"
      style="
        background: var(--alt-control-bg);
        position: fixed;
        width: 90vw;
        max-width: 48rem;
        height: 90vh;
        top: 5vh;
        left: 5vw;
        z-index: 100;
      ">
      <header>
        <button @click="iframeDialog = null" class="w-full nogrow">
          <i class="mdi mdi-close"></i>Close
        </button>
      </header>
      <iframe :src="iframeDialog"></iframe>
    </div>

    <div
      v-if="selectingImageLabelForFixture"
      class="card paper flex-col"
      style="
        position: fixed;
        width: 90vw;
        height: 90vh;
        top: 5vh;
        left: 5vw;
        z-index: 100;
      ">
      <header>Label for {{ selectingImageLabelForFixture.name }}</header>
      <button
        @click="selectingImageLabelForFixture = null"
        class="w-full nogrow">
        <i class="mdi mdi-close"></i>Close
      </button>

      <hr />
      <input
        class="w-full h-2rem nogrow"
        type="text"
        @change="
          setFixtureAssignment(
            selectingImageLabelForFixture.name,
            selectingImageLabelForFixture
          )
        "
        v-model="selectingImageLabelForFixture.label_image" />

      <div style="background-color: var(--alt-control-bg)">
        <media-browser :no_edit="no_edit" :selectfolders="false">
          <template v-slot="slotProps">
            <button
              v-if="
                slotProps.filename.endsWith('.jpg') ||
                slotProps.filename.endsWith('.svg') ||
                slotProps.filename.endsWith('.png') ||
                slotProps.filename.endsWith('.gif') ||
                slotProps.filename.endsWith('.jpeg') ||
                slotProps.filename.endsWith('.avif')
              "
              @click="
                selectingImageLabelForFixture.label_image =
                  slotProps.relfilename;
                setFixtureAssignment(
                  selectingImageLabelForFixture.name,
                  selectingImageLabelForFixture
                );
              ">
              Use
            </button>
          </template>
        </media-browser>
      </div>
    </div>

    <section
      id="optionsblock"
      class="multibar undecorated"
      style="flex-basis: 98%">
      <div class="menubar tool-bar">
        <button
          v-on:click="saveToDisk()"
          title="Save the current state now.  If not manually saved, autosave happens every 10min">
          <i class="mdi mdi-content-save"></i>Save
        </button>
      </div>

      <div class="menubar tool-bar">
        <button v-on:click="showMediaFolders = !showMediaFolders">
          <i class="mdi mdi-folder"></i>Media Folders
        </button>
        <button v-on:click="showDMXSetup = !showDMXSetup">
          <i class="mdi mdi-globe"></i>Universes
        </button>
        <button v-on:click="showhidefixtures()">
          <i class="mdi mdi-pencil"></i> Fixture Types
        </button>
        <button v-on:click="showhidefixtureassignments()">
          <i class="mdi mdi-light-bulb"></i>Fixtures
        </button>
        <button v-on:click="showimportexport = !showimportexport">
          <i class="mdi mdi-folder-open"></i>Import/Export
        </button>

        <a class="button" href="docs/index" target="_blank"
          ><i class="mdi mdi-help-circle-outline"></i>Help</a
        >
      </div>
    </section>

    <main class="w-full flex-row">
      <datalist id="serports">
        <option v-for="i of serports" v-bind:key="i" v-bind:value="i"></option>
      </datalist>

      <datalist id="universes">
        <option
          v-bind:key="i"
          v-for="(v, i) of universes"
          v-bind:value="i"></option>
      </datalist>

      <section v-if="showimportexport" class="flex-item window paper h-24rem">
        <header>
          <div class="tool-bar">
            <h3>Import/Export controls</h3>
            <button v-on:click="showimportexport = !showimportexport">
              <i class="mdi mdi-close"></i>Close
            </button>
          </div>
        </header>

        <p class="help">
          To export, use the download feature on the modules page.
        </p>

        <div class="card">
          <header>Import</header>

          <form
            :action="'/chandler/api/import-file/' + boardname"
            method="POST"
            enctype="multipart/form-data">
            <div class="stacked-form">
              <label
                >File
                <input type="file" name="file" />
              </label>

              <label
                >Import Universes
                <input type="checkbox" class="toggle" name="universes" />
              </label>

              <label
                >Import Fixture Types Library
                <input type="checkbox" class="toggle" name="fixture_types" />
              </label>

              <label
                >Import Fixture Assignments
                <input
                  type="checkbox"
                  class="toggle"
                  name="fixture_assignments" />
              </label>

              <label
                >Import Presets
                <input type="checkbox" class="toggle" name="fixture_presets" />
              </label>

              <input type="submit" value="Import" />
            </div>
          </form>
        </div>
      </section>

      <section
        v-if="showMediaFolders"
        class="flex-item window paper w-56rem nogrow margin"
        style="flex-basis: 56rem">
        <header>
          <div class="tool-bar">
            <h3>Media Folders</h3>
          </div>
        </header>

        <p>Enter your sound folder paths here, one per line</p>
        <div class="scroll">
          <textarea
            class="h-36rem"
            style="width: 80rem"
            v-bind:value="soundfolders.join('\r\n')"
            v-on:change="setSoundFolders($event.target.value.replace('\r', ''))"
            v-on:blur="
              setSoundFolders($event.target.value.replace('\r', ''))
            "></textarea>
        </div>
      </section>

      <div v-if="showDMXSetup" class="window margin flex-item w-sm-double">
        <header>
          <div class="tool-bar">
            <h3>Universe Setup</h3>
            <button v-on:click="showDMXSetup = 0">
              <i class="mdi mdi-close"></i>Close
            </button>
          </div>
        </header>

        <div class="tool-bar">
          <button v-on:click="refreshPorts">Refresh Serial Ports</button>
          <button v-on:click="pushSettings">Update Settings</button>
        </div>

        <div class="flex-row gaps margin">
          <div class="card">
            <table border="1" class="paper" data-testid="universe-status-table">
              <tr>
                <th>Universe</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
              <tr v-for="(v, i) in universes">
                <td>{{ i }}</td>
                <td v-bind:class="{ success: v.ok, danger: !v.ok }">
                  {{ v.status }}
                </td>

                <td>
                  <a class="button" :href="'/chandler/universe_info/' + i"
                    >Values</a
                  >
                </td>
              </tr>
            </table>
          </div>

          <div class="card max-h-24rem scroll">
            <header>
              <h4>Serial Ports</h4>
            </header>
            <ul>
              <li v-for="i in serports">{{ i }}</li>
            </ul>
          </div>
        </div>
        <details class="help">
          <summary><i class="mdi mdi-help-circle-outline"></i></summary>
          These settings take effect immediately when you click "Update
          Settings". To save them to disk, use "save setup" Configuring these
          universes requires system_admin.
        </details>
        <h4>Configure Universes</h4>

        <datalist id="artnettargets"> </datalist>

        <datalist id="utypes">
          <option
            value="enttecopen"
            title="Enttec Open DMX and most cheap FTDI based adapters, or raw serial ports"></option>
          <option
            value="smartbulb"
            title="A smart bulb from kaithem's device manager'"></option>

          <option value="enttec"></option>
          <option value="artnet"></option>
          <option value="null">Disabled/Unused</option>
        </datalist>

        <table border="1" data-testid="universe-configuration-table">
          <tr>
            <th>Universe</th>
            <th>Type</th>
            <th>Interface</th>
            <th>FPS</th>
            <th>Number</th>
            <th>Actions</th>
          </tr>
          <tr v-for="(v, i) in configuredUniverses">
            <td>{{ i }}</td>
            <td>
              <input
                list="utypes"
                class="w-6rem"
                v-model="v.type"
                title="The type of universe. Usually enttec or artnet" />
            </td>

            <td v-if="v.type != 'artnet'">
              <input
                list="serports"
                v-model="v.interface"
                title="The interface device that describes where to send the data. Usually a serial port, or a device name from the device manager for smartbulbs"
                placeholder="Default" />
            </td>
            <td v-if="v.type == 'artnet'">
              <input
                list="artnettargets"
                v-model="v.interface"
                title="A destination ip:port in the case of ArtNet."
                placeholder="Default" />
            </td>

            <td>
              <input
                type="number"
                min="0"
                max="480"
                class="w-4rem"
                step="0.1"
                v-model="v.framerate"
                title="The max frame rate" />
            </td>

            <td>
              <input
                type="number"
                min="0"
                max="65535"
                v-model="v.number"
                class="w-6rem"
                title="The universe number. Mostly used for ArtNet" />
            </td>

            <td>
              <button v-on:click="deleteUniverse(i)">Del</button>
            </td>
          </tr>
        </table>
        <input placeholder="New Universe Name" v-model="newuniversename" />
        <button
          v-on:click="
            configuredUniverses[newuniversename] = {
              type: 'enttec',
              framerate: 44,
              channels: 512,
              number: 1,
              channel_config: {},
            }
          ">
          Add
        </button>
      </div>

      <section v-if="universeFullSettings" class="flex-item window paper">
        <h3>
          <button v-on:click="universeFullSettings = 0">
            <i class="mdi mdi-close"></i>Close</button
          >Universe Setup:{{ universeFullSettings }}
        </h3>
      </section>

      <section
        v-if="showFixtureSetup"
        class="flex-item window margin min-h-36rem w-sm-full"
        style="max-height: 80vh">
        <header>
          <div class="tool-bar">
            <h3>Fixture Types</h3>
            <button v-on:click="showhidefixtures()">
              <i class="mdi mdi-close"></i>Close
            </button>
          </div>
        </header>

        <div class="tool-bar">
          <button v-on:click="addfixturetype()">
            <i class="mdi mdi-plus"></i>New
          </button>
          <a
            class="button"
            :href="
              '/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/opz_import/' +
              boardname
            "
            >Import from OP-Z format</a
          >
        </div>
        <hr />

        <select
          data-testid="fixture-type-to-edit"
          v-model="selectedFixtureClass"
          v-on:change="getfixtureclass(selectedFixtureClass)">
          <option v-for="i in Object.keys(fixtureClasses)" :value="i">
            {{ i }}
          </option>
        </select>

        <div v-if="selectedFixtureClass" class="margin">
          <h4>{{ selectedFixtureClass }}</h4>

          <div class="tool-bar">
            <button v-on:click="delfixturetype">
              <i class="mdi mdi-delete"></i>Delete Fixture Type
            </button>
            <button>Rename</button>
          </div>

          <h3>Basic Info</h3>
          <div class="stacked-form">
            <p class="help">
              Color profiles let you group fixtures with similar color behavior,
              so that they can share all presets called "name@profile". A preset
              for "rgb" will show up for any fixture where the profile *starts
              with* "rgb", including "rgbw", "rgb.generic", etc.
            </p>
            <label>
              Color Profile:
              <input
                list="colorprofiles"
                v-on:change="pushfixture(selectedFixtureClass)"
                v-model="fixtureClasses[selectedFixtureClass].color_profile" />
            </label>
          </div>

          <h3>Channels in Fixture Type</h3>
          <div
            v-for="(v, i) in fixtureClasses[selectedFixtureClass].channels ||
            []">
            <h4>{{ i }}.</h4>
            <label
              >Name:
              <input
                v-on:change="pushfixture(selectedFixtureClass)"
                v-model="
                  fixtureClasses[selectedFixtureClass].channels[i].name
                " />
            </label>

            <label
              >Type:
              <select
                v-on:change="
                  chTypeChanged(i);
                  pushfixture(selectedFixtureClass);
                "
                v-model="fixtureClasses[selectedFixtureClass].channels[i].type">
                <option>red</option>
                <option>green</option>
                <option>blue</option>
                <option>uv</option>
                <option>white</option>
                <option>amber</option>
                <option>lime</option>
                <option>intensity</option>
                <option>generic</option>
                <option>custom</option>
                <option>fine</option>
                <option>unused</option>
                <option>fixed</option>
              </select>
            </label>

            <label
              v-if="
                fixtureClasses[selectedFixtureClass].channels[i].type == 'fine'
              ">
              Matching Coarse:
              <input
                v-on:change="pushfixture(selectedFixtureClass)"
                title="The corresponding coarse channel for this fine channel"
                min="0"
                max="64"
                type="number"
                v-model="
                  fixtureClasses[selectedFixtureClass].channels[i].coarse
                " />
            </label>

            <label
              v-if="
                fixtureClasses[selectedFixtureClass].channels[i].type == 'fixed'
              ">
              Fixed Value:
              <input
                v-on:change="pushfixture(selectedFixtureClass)"
                title="The fixed DMX channel value"
                min="0"
                max="256"
                type="number"
                v-model="
                  fixtureClasses[selectedFixtureClass].channels[i].value
                " />
            </label>

            <div
              v-if="
                fixtureClasses[selectedFixtureClass].channels[i].type ==
                'custom'
              ">
              <details class="help">
                <summary><i class="mdi mdi-help-circle-outline"></i></summary>
                The custom channel type allows you to define a different meaning
                for a channel depending on what range it is in. This is fairly
                common for controlling gobos and gobo rotation, etc. Ranges are
                defined my the inclusive min and max channel of that range, plus
                a name for that option.
              </details>

              <h5>Ranges for channel {{ i }}</h5>
              <table border="1">
                <tr>
                  <th>Min Val</th>
                  <th>Max Val</th>
                  <th>Option Name</th>
                  <th>Actions</th>
                </tr>
                <tr
                  v-for="(w, j) in fixtureClasses[selectedFixtureClass]
                    .channels[i].ranges">
                  <td>
                    <input
                      v-on:change="pushfixture(selectedFixtureClass)"
                      class="w-4rem"
                      v-model.number="
                        fixtureClasses[selectedFixtureClass].channels[i].ranges[
                          j
                        ].min
                      "
                      type="number" />
                  </td>
                  <td>
                    <input
                      v-on:change="pushfixture(selectedFixtureClass)"
                      class="w-4rem"
                      v-model.number="
                        fixtureClasses[selectedFixtureClass].channels[i].ranges[
                          j
                        ].max
                      "
                      type="number" />
                  </td>
                  <td>
                    <input
                      v-on:change="pushfixture(selectedFixtureClass)"
                      class="w-6rem"
                      v-model.number="
                        fixtureClasses[selectedFixtureClass].channels[i].ranges[
                          j
                        ].name
                      " />
                  </td>
                  <td>
                    <button
                      v-on:click="
                        fixtureClasses[selectedFixtureClass].channels[
                          i
                        ].ranges.splice(j, 1);
                        pushfixture(selectedFixtureClass);
                      ">
                      Del
                    </button>
                  </td>
                </tr>
              </table>
              <button
                v-on:click="
                  fixtureClasses[selectedFixtureClass].channels[i].ranges.push({
                    min: 0,
                    max: 0,
                    name: 'name',
                  });
                  pushfixture(selectedFixtureClass);
                ">
                Add Range
              </button>
            </div>
            <button
              v-on:click="
                fixtureClasses[selectedFixtureClass].channels.splice(i, 1);
                pushfixture(selectedFixtureClass);
              ">
              Del
            </button>
          </div>
          <button
            v-on:click="
              fixtureClasses[selectedFixtureClass].channels.push({
                name: 'red',
                type: 'red',
              });
              pushfixture(selectedFixtureClass);
            ">
            Add Channel
          </button>
        </div>
      </section>

      <section v-if="showfixtureassg" class="flex-item window paper">
        <header>
          <div class="tool-bar">
            <h3>Fixture Assignments</h3>
            <button v-on:click="showfixtureassg = 0">
              <i class="mdi mdi-close"></i>Close
            </button>
          </div>
        </header>
        <details class="help">
          <summary><i class="mdi mdi-help-circle-outline"></i></summary>
          Here is where you actually assign fixtures to channels after creating
          the desired fixture types. Clicking Update will cause the new
          assignments to take effect immediately. Use the save settings button
          to make them permanent.
        </details>

        <table border="1">
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Universe</th>
            <th>Address</th>
            <th>Action</th>
          </tr>

          <tr
            v-bind:key="i[1].name + i[1].universe + i[1].addr"
            v-for="i in dictView(fixtureAssignments, ['universe', 'channel'])">
            <td>{{ i[1].name }}</td>
            <td>{{ i[1].type }}</td>
            <td>
              <input
                class="w-6rem"
                v-on:change="setFixtureAssignment(i[1].name, i[1])"
                v-model="i[1].universe" />
            </td>
            <td>
              <input
                class="w-4rem"
                v-on:change="setFixtureAssignment(i[1].name, i[1])"
                v-model="i[1].addr" />
            </td>
            <td>
              <button v-on:click="rmFixtureAssignment(i[1].name)">
                <i class="mdi mdi-delete"></i>
                Delete
              </button>
              <button v-on:click="selectingImageLabelForFixture = i[1]">
                <i class="mdi mdi-image-outline"></i>
                Image
              </button>
              <button
                v-on:click="iframeDialog = getExcalidrawFixtureLink(i[1].name)">
                <i class="mdi mdi-pencil-outline"></i>
                Draw
              </button>
            </td>
          </tr>
        </table>

        <h4>Add Assignment</h4>

        <table border="1">
          <tr>
            <td>Name</td>
            <td><input v-model="newfixname" /></td>
          </tr>
          <tr>
            <td>Type</td>
            <td>
              <select v-model="newfixtype">
                <option v-for="(v, i) in fixtureClasses"
                 v-bind:key="i"
                 v-bind:value="i">
                  {{ i }}
                </option>
              </select>
            </td>
          </tr>

          <tr>
            <td>Universe</td>
            <td>
              <input v-model="newfixuniverse" list="universes" />
            </td>
          </tr>
          <tr>
            <td>Address</td>
            <td>
              <input type="number" min="1" v-model="newfixaddr" />
            </td>
          </tr>
        </table>
        <button
          v-on:click="
            addFixtureAssignment(
              newfixname,
              newfixtype,
              newfixuniverse,
              newfixaddr
            )
          ">
          Add and Update
        </button>

        <div v-if="ferrs">
          <h4>Errors</h4>
          <pre>{{ ferrs }}</pre>
        </div>
        <br />
      </section>

      <section class="window w-full h-8rem" v-if="sys_alerts">
        <div class="flex-row scroll gaps padding">
          <div class="card" v-for="(v, i) of sys_alerts"
          v-bind:key="v.id"
          >
            <header :class="v['barrel-class']" class="padding">
              <i class="mdi mdi-alert"></i>{{ i }}
            </header>
            <p :class="v['barrel-class']">
              {{ v.message || "no trip message" }}
            </p>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import {
  // used to be in appData
  sys_alerts,
  boardname,
  serports,
  fixtureAssignments,
  ferrs,
  no_edit,
  universeFullSettings,
  soundfolders,
  configuredUniverses,
  fixtureClasses,
  dictView,
  universes,
  saveToDisk,
  refreshPorts,
  pushSettings,
  deleteUniverse,
} from "./boardapi.mjs";
import * as Vue from "/static/js/thirdparty/vue.esm-browser.js";

let showimportexport = Vue.ref(false);
let newfixname = Vue.ref("");
let newfixtype = Vue.ref("");
let newfixaddr = Vue.ref("");
let newfixuniverse = Vue.ref("");

function chTypeChanged(i) {
  const chType =
    fixtureClasses.value[selectedFixtureClass.value].channels[i].type;

  fixtureClasses.value[selectedFixtureClass.value].channels[i].name = chType;
  // Set up the  data options param for each channel

  if (chType == "fine") {
    fixtureClasses.value[selectedFixtureClass.value].channels[i].coarse = 0;
  } else if (chType == "custom") {
    fixtureClasses.value[selectedFixtureClass.value].channels[i].ranges = [];
  } else if (chType == "fixed") {
    fixtureClasses.value[selectedFixtureClass.value].channels[i].value = 0;
  } else {
    fixtureClasses.value[selectedFixtureClass.value].channels[i].coarse =
      undefined;
    fixtureClasses.value[selectedFixtureClass.value].channels[i].value =
      undefined;
    fixtureClasses.value[selectedFixtureClass.value].channels[i].ranges =
      undefined;
  }
  this.pushfixture(selectedFixtureClass.value);
}
function addFixtureAssignment(name, t, univ, addr) {
  if (!name) {
    return;
  }
  var d = {
    name: name,
    type: t,
    universe: univ,
    addr: addr,
  };

  globalThis.api_link.send(["setFixtureAssignment", name, d]);
}
function getfixtureclasses() {
  globalThis.api_link.send(["getfixtureclasses"]);
}
function showhidefixtures() {
  showFixtureSetup.value = !showFixtureSetup.value;
  getfixtureclasses();
  selectedFixtureClass.value = "";
}
function showhidefixtureassignments() {
  getfixtureclasses();
  showfixtureassg.value = !showfixtureassg.value;
  globalThis.api_link.send(["getfixtureassg"]);
}

function getfixtureclass(i) {
  if (i == "") {
    return;
  }
  globalThis.api_link.send(["getfixtureclass", i]);
}

function addfixturetype() {
  let x = prompt("New Fixture Type Name:", selectedFixtureType.value);
  if (x) {
    old_vue_set(fixtureClasses.value, x, { channels: [] });
    selectedFixtureType.value = x;
    globalThis.api_link.send(["setfixtureclass", x, fixtureClasses.value[x]]);
    globalThis.api_link.send(["getfixtureclass", x]);
  }
}
function delfixturetype() {
  let x = confirm("Really delete?");
  if (x) {
    old_vue_delete(fixtureClasses.value, selectedFixtureType.value);
    globalThis.api_link.send(["rmfixtureclass", selectedFixtureType.value]);
    selectedFixtureType.value = "";
  }
}
function pushfixture(i) {
  globalThis.api_link.send(["setfixtureclass", i, fixtureClasses.value[i]]);
}

function setFixtureAssignment(i, v) {
  globalThis.api_link.send(["setFixtureAssignment", i, v]);
}

function rmFixtureAssignment(i) {
  globalThis.api_link.send(["rmFixtureAssignment", i]);
}

function setSoundFolders(folders) {
  globalThis.api_link.send(["setsoundfolders", folders]);
}
</script>

<script>
import { httpVueLoader } from "./httploaderoptions.mjs";
import * as Vue from "/static/js/thirdparty/vue.esm-browser.js";

// Legacy compatibility equivalents for the old vue2 apis. TODO get rid of this
function old_vue_set(o, k, v) {
  o[k] = v;
}

function old_vue_delete(o, k) {
  delete o[k];
}

// Blur the active element to cause Onchange events
globalThis.visibilitychange = function () {
  document.activeElement.blur();
};

let selectingImageLabelForFixture = Vue.ref(null);
let iframeDialog = Vue.ref(null);
let showfixtureassg = Vue.ref(false);
let showDMXSetup = Vue.ref(false);
let showMediaFolders = Vue.ref(false);
let showFixtureSetup = Vue.ref(false);
let selectedFixtureClass = Vue.ref("");
let newuniversename = Vue.ref("");
let selectedFixtureType = Vue.ref("");

function getExcalidrawFixtureLink(fixture) {
  return (
    "/excalidraw-plugin/edit?module=" +
    encodeURIComponent(boardname.value.split(":")[0]) +
    "&resource=" +
    encodeURIComponent(
      "media/chandler/sketches/fixture_" +
        boardname.value.split(":")[0] +
        "_" +
        fixture +
        ".excalidraw.png"
    ) +
    "&callback=" +
    encodeURIComponent(
      "/chandler/label_image_update_callback/fixture/" +
        boardname.value +
        "/" +
        fixture
    ) +
    "&ratio_guide=16_9"
  );
}

export default {
  name: "config-app",
  components: {
    "media-browser": httpVueLoader("./media-browser.vue"),
  },
};
</script>
