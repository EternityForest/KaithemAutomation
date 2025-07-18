<style>
.grey {
  color: grey;
  font-size: 70%;
}

.gradient-bg {
  background: linear-gradient(
    175deg,
    rgb(61 61 61 / 27%) 0%,
    rgb(0 0 0 / 30%) 100%
  );
}

.indicator {
  border-radius: 0.2em;
  display: inline-block;
  width: 0.9em;
  height: 0.9em;
  border-style: dashed;
  border-width: 1.5px;
}

.break {
  flex-basis: 100%;
  height: 0;
}

.cuebutton {
  min-width: 24em;
  max-width: 32em;
}

.compact-cuebutton.success {
  font-weight: bold;
}

.compact-cuebutton {
  aspect-ratio: 16/9;
  overflow: hidden;
  flex-basis: 10rem;
  height: auto;
  flex-grow: 0;
  max-width: 10rem;
  padding: 0px;
  position: relative;
  z-index: 1001;
  box-shadow: 4px 5px 3px #00000069;
  margin: 3px;
  touch-action: manipulation;

  & > img {
    position: absolute;
    object-fit: contain;
    width: 100%;
    height: 100%;
    margin: auto;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 1002;
  }

  & > div {
    & > p {
      opacity: 0.3;
    }

    width: 100%;
    height: 100%;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-shadow:
      1px 1px 2px var(--contrasting-bg-color),
      -1px 1px 2px var(--contrasting-bg-color),
      -1px -1px 2px var(--contrasting-bg-color),
      1px -1px 2px var(--contrasting-bg-color);
    position: absolute;
    z-index: 1002;
    background: radial-gradient(
      circle,
      rgba(255, 255, 255, 0.082) 58%,
      rgb(0 0 0 / 0%) 85%,
      rgba(0, 0, 0, 0.363) 100%
    ) !important;
  }
}

.cue-button-album-art {
  border: none;
  height: 100%;
  object-fit: contain;
  max-width: 4em;
  object-position: top;
  z-index: 3;
}

.cue-button-body {
  aspect-ratio: 16/9;
  flex-grow: 1;
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

div.highlight {
  border: 2px solid;
}
</style>

<template id="template">
  <div
    id="app"
    v-cloak
    style="display: flex; flex-wrap: wrap; justify-content: center">
    <div class="flex-row w-full">
      <section
        class="window cols-2 max-h-24rem margin max-w-48rem"
        v-if="Object.keys(sys_alerts).length > 0">
        <div class="flex-row scroll gaps padding">
          <div
            class="card w-sm-full"
            v-for="(v, i) of sys_alerts"
            v-bind:key="v.id">
            <header :class="v['barrel-class']" class="padding break-word">
              <i class="mdi mdi-alert"></i>{{ i }}
            </header>
            <p :class="v['barrel-class']">
              {{ v.message || "no trip message" }}
            </p>
          </div>
        </div>
      </section>

      <div
        class="window paper cols-10 grow margin-top"
        style="overflow: auto; flex-grow: 1; min-width: 18em">
        <header>
          <div class="tool-bar">
            <button id="toolbar-clock">{{ clock }}</button>
            <a
              class="button"
              :href="
                '/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/' +
                boardname
              "
              ><i class="mdi mdi-pencil"></i
            ></a>

            <button type="button" @click="showUtils = !showUtils">
              <i class="mdi mdi-calculator"></i>
            </button>
            <input
              size="8"
              title="Enter a cue's shortcut code here to activate it. Keybindings are suspended while this is selected."
              aria-label="Shortcut code"
              placeholder="Shortcut"
              v-model="sc_code"
              v-on:keydown.enter="shortcut()" />
            <button v-on:click="shortcut()">Go!</button>
            <button v-on:click="showPages = !showPages">Toggle Compact</button>

            <label
              ><i class="mdi mdi-volume-medium"></i>
              <input type="checkbox" class="toggle" v-model="uiAlertSounds"
            /></label>
            <button onclick="document.documentElement.requestFullscreen()">
              <i class="mdi mdi-arrow-expand-all"></i>Fullscreen
            </button>

            <label
              ><i class="mdi mdi-keyboard"></i>Send Keys:
              <input type="checkbox" class="toggle" v-model="sendKeystrokes" />
            </label>
          </div>
        </header>

        <div class="flex-row gaps scroll max-h-48rem">
          <article v-if="showUtils" class="card w-sm-full nogrow margin">
            <header>
              <h3>Calculator</h3>
            </header>
            <p>This calculator supports units! Try "5lb+6oz to kg"</p>
            <iframe class="undecorated w-full" src="../util-calc"></iframe>
          </article>

          <article
            v-if="showUtils"
            class="card w-sm-full nogrow max-h-24rem margin">
            <header>
              <h3>Scratchpad</h3>
            </header>
            <textarea class="w-full h-60rem" v-model="scratchpad"></textarea>
          </article>

          <template v-for="i in formatGroups">
            <article
              v-if="i"
              style="position: relative"
              v-bind:key="i[1].id"
              v-bind:class="{
                'card': 1,
                'w-sm-full': 1,
                'margin': 1,
                'group': 1,
                'flex-col': 1,
                'min-h-18rem': 1,
                'max-h-24rem': 1,
                'noselect': 1,
              }">
              <header class="flex-row gaps">
                <h3>
                  <button
                    :disabled="i[1].utility"
                    v-bind:class="{ highlight: i[0] == groupname }"
                    popovertarget="groupDialog"
                    v-on:click="selectgroup(i[1], i[0])"
                    style="font-weight: bold; width: 100%">
                    {{ i[1].name
                    }}<span v-if="i[1].ext" class="grey"> (external)</span>

                    <span v-if="cuemeta[i[1].cue].sound"
                      ><i class="mdi mdi-music"></i
                    ></span>

                    <span
                      v-if="cuemeta[i[1].cue].inheritRules"
                      title="This cue has rules inherited"
                      ><i class="mdi mdi-script-text-outline"></i
                    ></span>
                    <span
                      v-if="
                        cuemeta[i[1].cue].rules &&
                        cuemeta[i[1].cue].rules.length > 0
                      "
                      title="This cue has rules attatched"
                      ><i class="mdi mdi-script-text-outline"></i
                    ></span>
                  </button>
                </h3>
              </header>
              <div
                class="flex-col nogaps scene-data-area readability-outline"
                style="text-align: center; position: relative">
                <img
                  style="
                    border: none;
                    opacity: 0.4;
                    height: 100%;
                    width: 100%;
                    object-fit: contain;
                    position: absolute;
                  "
                  class="v-center"
                  onerror='this.style.display = "none"'
                  v-if="cuemeta[i[1].cue].labelImage"
                  :src="
                    '/chandler/WebMediaServer?labelImg=' +
                    encodeURIComponent(cuemeta[i[1].cue].id) +
                    '&timestamp=' +
                    encodeURIComponent(cuemeta[i[1].cue].labelImageTimestamp)
                  " />

                <div style="height: 100%; width: 100%; z-index: 1">
                  <p class="warning" v-if="i[1].status">
                    STATUS: {{ i[1].status }}
                  </p>

                  <div
                    class="flex-row nogaps nogrow w-full h-min-content"
                    style="align-items: stretch">
                    <div
                      style="border-bottom-right-radius: 0.5em"
                      :class="{ success: i[1].active, grow: 1 }"
                      v-if="i[1].active && cuemeta[i[1].cue]">
                      <span data-testid="active-cue-name">{{
                        cuemeta[i[1].cue].name
                      }}</span>
                      <small>{{ formatTime(i[1].enteredCue) }}</small>
                    </div>

                    <img
                      style="border: none; height: fit-content"
                      class="w-4rem"
                      onerror='this.style.display = "none"'
                      v-if="cuemeta[i[1].cue].sound"
                      :src="
                        '/chandler/WebMediaServer?albumArt=' +
                        encodeURIComponent(i[1].cue)
                      " />

                    <span
                      v-if="
                        i[1].active &&
                        ('' + cuemeta[i[1].cue].length).indexOf('@') > -1
                      "
                      ><i class="mdi mdi-clock-outline"></i
                      >{{ cuemeta[i[1].cue].length.substring(1) }}</span
                    >
                  </div>
                  <cue-countdown
                    :group="i[1]"
                    :cue="cuemeta[i[1].cue]"></cue-countdown>

                  <div
                    class="w-full flex"
                    v-if="i[1].active && i[1].nextScheduledCue">
                    <span
                      ><i class="mdi mdi-calendar-clock"></i>
                      {{ formatTime(i[1].nextScheduledCue[1])
                      }}<i class="mdi mdi-arrow-right"></i>
                      {{ i[1].nextScheduledCue[0] }}
                    </span>
                  </div>

                  <small
                    v-if="
                      i[1].active &&
                      (cuemeta[i[1].cue].next || cuemeta[i[1].cue].defaultNext)
                    ">
                    Next:
                    {{
                      (
                        cuemeta[i[1].cue].next ||
                        cuemeta[i[1].cue].defaultNext ||
                        ""
                      ).split("?")[0]
                    }}
                  </small>

                  <iframe
                    style="flex-grow: 1"
                    v-if="showPages && i[1].infoDisplay.length > 0"
                    :src="i[1].infoDisplay"></iframe>

                  <group-ui
                    :unixtime="unixtime"
                    v-bind:group-data="i[1]"
                    :cue="cuemeta[i[1].cue]"></group-ui>
                </div>
              </div>

              <footer>
                <p
                  v-if="!i[1].utility"
                  class="tool-bar"
                  style="flex-grow: 0.15">
                  <button
                    :class="{ highlight: i[1].active }"
                    v-on:click="go(i[0])">
                    <i class="mdi mdi-play"></i>
                  </button>
                  <button v-on:click="gotoPreviousCue(i[0])">
                    <i class="mdi mdi-skip-previous"></i>
                  </button>
                  <button v-on:click="gotoNextCue(i[0])">
                    <i class="mdi mdi-skip-next"></i>
                  </button>
                  <button class="stopbutton" v-on:click="stop(i[0])">
                    <i class="mdi mdi-stop-circle-outline"></i>
                  </button>
                </p>

                <div class="tool-bar">
                  <input
                    v-if="!i[1].utility"
                    type="range"
                    style="width: 98%"
                    max="1"
                    step="0.01"
                    min="0"
                    v-on:input="setalpha(i[0], parseFloat($event.target.value))"
                    v-on:change="
                      setalpha(i[0], parseFloat($event.target.value))
                    "
                    :value="alphas[i[0]]" />
                </div>

                <div
                  class="tool-bar nogrow"
                  v-if="i[1].eventButtons.length > 0">
                  <button
                    v-for="v of i[1].eventButtons"
                    v-bind:key="v[0] + '-' + v[0]"
                    v-on:click="sendGroupEventWithConfirm(v[1], v[1])">
                    {{ v[0] }}
                  </button>
                </div>
              </footer>
            </article>
          </template>
        </div>
      </div>
    </div>

    <div
      popover
      id="groupDialog"
      class="window paper margin modal w-full noselect"
      v-if="editingGroup && cuemeta[editingGroup.cue]">
      <header>
        <div class="tool-bar">
          <h3>
            {{ editingGroup.name }}
            <span
              class="highlight"
              v-if="editingGroup.active & !editingGroup.doingHandoff"
              >(running)</span
            >
          </h3>

          <input
            v-if="!editingGroup.utility"
            type="range"
            style="max-width: 12rem"
            max="1"
            step="0.01"
            min="0"
            v-on:input="
              setalpha(editingGroup.id, parseFloat($event.target.value))
            "
            v-on:change="
              setalpha(editingGroup.id, parseFloat($event.target.value))
            "
            :value="alphas[editingGroup.id]" />

          <cue-countdown
            :group="editingGroup"
            :cue="cuemeta[editingGroup.cue]"></cue-countdown>

          <button
            v-if="editingGroup.cuelen"
            v-on:click="addTimeToGroup(editingGroup.id)">
            <i class="mdi mdi-clock"></i><i class="mdi mdi-plus"></i>Add Time
          </button>

          <button
            @click="refreshCueProviders(editingGroup.id)"
            v-if="editingGroup.cueProviders.length > 0">
            <i class="mdi mdi-refresh"></i>Refresh
          </button>
          <button @click="compactCues = !compactCues" class="nogrow">
            <i class="mdi mdi-view-grid-compact"></i>Compact
          </button>
          <button
            popovertarget="groupDialog"
            popovertargetaction="hide"
            class="nogrow">
            <i class="mdi mdi-close"></i>Close
          </button>
        </div>
      </header>

      <div id="cuesbox">
        <div class="flex-row align-left">
          <cue-iter
            class="w-full"
            v-slot="cueSlot"
            :cuemeta="cuemeta"
            :groupcues="groupcues"
            :editingGroup="editingGroup"
            :groupname="groupname">
            <button
              v-if="compactCues"
              v-on:click="
                jumpToCueWithConfirmationIfNeeded(
                  cueSlot.i[1].id,
                  editingGroup.id
                )
              "
              class="compact-cuebutton"
              v-bind:class="{
                success: cuemeta[editingGroup.cue].name == cueSlot.i[1].name,
              }">
              <img
                style="
                  border: none;
                  height: 100%;
                  width: 100%;
                  position: absolute;
                  object-fit: contain;
                "
                class="v-center"
                onerror='this.style.display = "none"'
                v-if="cueSlot.i[1].labelImage"
                :src="
                  '/chandler/WebMediaServer?labelImg=' +
                  encodeURIComponent(cueSlot.i[1].id) +
                  '&cacheid=' +
                  encodeURIComponent(cueSlot.i[1].labelImageTime)
                " />

              <div>
                {{ cueSlot.i[1].name }}
                <p>
                  <span
                    v-if="cueSlot.i[1].sound.length > 0"
                    class="mdi mdi-music"></span>
                  <span
                    v-if="cueSlot.i[1].slide.length > 0"
                    class="mdi mdi-projector-screen-outline"></span>
                  <span
                    v-if="!cueSlot.i[1].track"
                    class="mdi mdi-arrow-expand-right"
                    title="Cue Only"></span>
                  <span
                    v-if="cueSlot.i[1].hasLightingData || !cueSlot.i[1].track"
                    class="mdi mdi-track-light"
                    title="Cue Only"></span>
                  <span
                    v-if="cueSlot.i[1].length > 0"
                    class="mdi mdi-clock-outline"
                    title="Timed Cue"></span>
                  <span
                    v-if="cueSlot.i[1].fadeIn"
                    class="mdi mdi-chart-bell-curve-cumulative"
                    title="Fade In"></span>
                </p>
              </div>
            </button>

            <article
              class="w-sm-full margin flex-col"
              v-if="!compactCues"
              v-bind:class="{
                card: 1,
                success: cuemeta[editingGroup.cue].name == cueSlot.i[1].name,
              }">
              <header>
                <button
                  class="h-4rem w-full cuebutton"
                  v-on:click="
                    jumpToCueWithConfirmationIfNeeded(
                      cueSlot.i[1].id,
                      editingGroup.id
                    )
                  ">
                  <span v-if="cueSlot.i[1].shortcut.length > 0">
                    ({{ cueSlot.i[1].shortcut }})</span
                  >
                  {{ cueSlot.i[1].name }}

                  <span
                    v-if="cueSlot.i[1].sound.length > 0"
                    class="mdi mdi-music"></span>
                  <span
                    v-if="cueSlot.i[1].slide.length > 0"
                    class="mdi mdi-projector-screen-outline"></span>
                  <span
                    v-if="!cueSlot.i[1].track"
                    class="mdi mdi-arrow-expand-right"
                    title="Cue Only"></span>
                  <span
                    v-if="cueSlot.i[1].hasLightingData || !cueSlot.i[1].track"
                    class="mdi mdi-track-light"
                    title="Cue Only"></span>
                  <span
                    v-if="cueSlot.i[1].length > 0 || cueSlot.i[1].relLength"
                    class="mdi mdi-clock-outline"
                    title="Timed Cue"></span>
                  <span
                    v-if="cueSlot.i[1].fadeIn"
                    class="mdi mdi-chart-bell-curve-cumulative"
                    title="Fade In"></span>
                </button>
              </header>

              <div
                class="flex-row nogaps nogrow h-12rem w-full cue-button-body"
                style="position: relative">
                <img
                  style="
                    border: none;
                    height: 100%;
                    width: 100%;
                    position: absolute;
                    object-fit: contain;
                  "
                  class="v-center"
                  onerror='this.style.display = "none"'
                  v-if="cueSlot.i[1].labelImage"
                  :src="
                    '/chandler/WebMediaServer?labelImg=' +
                    encodeURIComponent(cueSlot.i[1].id) +
                    '&cacheid=' +
                    encodeURIComponent(cueSlot.i[1].labelImageTime)
                  " />

                <div
                  style="z-index: 1; height: 2rem"
                  :class="{
                    'success':
                      cuemeta[editingGroup.cue].name == cueSlot.i[1].name,
                    'grow': 1,
                    'readability-outline': 1,
                  }">
                  <cue-countdown
                    v-if="cuemeta[editingGroup.cue].name == cueSlot.i[1].name"
                    :group="editingGroup"
                    :cue="cuemeta[editingGroup.cue]"></cue-countdown>

                  <div
                    v-if="cueSlot.i[1].notes.length > 0"
                    style="max-width: 10em">
                    {{ cueSlot.i[1].notes }}
                  </div>

                  <span
                    v-if="
                      cueSlot.i[1].active &&
                      ('' + cueSlot.i[1].length).indexOf('@') > -1
                    "
                    ><i class="mdi mdi-clock-outline"></i
                    >{{ cueSlot.i[1].cue.length.substring(1) }}</span
                  >
                </div>

                <img
                  class="v-center cue-button-album-art"
                  onerror='this.style.display = "none"'
                  v-if="cueSlot.i[1].sound"
                  :src="
                    '/chandler/WebMediaServer?albumArt=' +
                    encodeURIComponent(cueSlot.i[1].id)
                  " />
              </div>
            </article>
          </cue-iter>
        </div>
      </div>
    </div>

    <section
      class="window margin scroll col-2 h-18rem"
      style="min-width: 12rem">
      <iframe src="/dropdownpanel?summary=1" class="w-full h-full"></iframe>
    </section>
  </div>
</template>

<script setup>
import {
  unixtime,
  boardname,
  clock,
  alphas,
  groupname,
  editingGroup,
  cuemeta,
  showPages,
  uiAlertSounds,
  groupcues,
  formatGroups,
  triggerShortcut,

  // Methids
  sys_alerts,
  selectgroup,
  go,
  gotoPreviousCue,
  gotoNextCue,
  setalpha,
  jumpToCueWithConfirmationIfNeeded,
  sendGroupEventWithConfirm,
  stop,
  addTimeToGroup,
  sendKeystrokes,
  refreshCueProviders,
} from "./boardapi.mjs";
import * as Vue from "/static/js/thirdparty/vue.esm-browser.js";

const sc_code = Vue.ref("");

function shortcut() {
  triggerShortcut(sc_code.value);
  sc_code.value = "";
}

function formatTime(t) {
  var date = new Date(t * 1000);
  return date.strftime("%I:%M:%S%p");
}

const showUtils = Vue.ref(false);
const compactCues = Vue.ref(true);
const scratchpad = Vue.ref("Text here is NOT yet saved when page reloads.");
</script>

<script type="module">
import { httpVueLoader } from "./httploaderoptions.mjs";

globalThis.httpVueLoader = httpVueLoader;

export default {
  name: "commander-app",
  template: "#template",
  methods: {
    selectgroup,
    go,
    gotoPreviousCue,
    gotoNextCue,
    setalpha,
    jumpToCueWithConfirmationIfNeeded,
    sendGroupEventWithConfirm,
    addTimeToGroup,
  },
  components: {
    "cue-countdown": globalThis.httpVueLoader("./cue-countdown.vue"),
    // Currently contains the timers and the display tags for the groups overview
    "group-ui": globalThis.httpVueLoader("./group-ui-controls.vue"),
    "cue-iter": globalThis.httpVueLoader("./cue-iter.vue"),
  },
};
</script>
