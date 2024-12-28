<style scoped></style>

<template id="template">
  <div
    popover
    id="presetForFixture"
    v-if="fixture"
    class="card paper flex-col"
    style="
      background: var(--alt-control-bg);
      position: fixed;
      width: 98vw;
      height: 90vh;
      top: 1vh;
      left: 1vw;
      z-index: 100;
    ">
    <header>
      Presets for {{ fixture }}
      <span v-if="fordestination"> destination value</span>
    </header>
    <button
      class="w-full nogrow"
      popovertarget="presetForFixture"
      popovertargetaction="hide">
      <i class="mdi mdi-close"></i>Close
    </button>
    <div
      class="flex-row nogrow max-h-12rem scroll"
      style="align-items: flex-start; align-content: flex-start">
      <template v-for="ps of recentPresets.toReversed()">
        <button
          v-bind:key="ps"
          v-if="checkPresetUsablility(ps)"
          @click="setFixturePreset(currentcueid, fixture, ps)"
          :disabled="no_edit"
          class="preset-button preset-icon"
          popovertarget="presetForFixture"
          popovertargetaction="hide">
          <img
            v-if="getpresetimage(ps)"
            :src="
              '/chandler/WebMediaServer?board=' +
              boardname +
              '&file=' +
              encodeURIComponent(getpresetimage(ps))
            " />
          <div
            class="label"
            :style="{
              'background-color': presets[ps]?.html_color || 'transparent',
            }">
            {{ ps.split("@")[0] }}
          </div>
          <div
            class="label-bottom"
            :style="{ 'background-color': ps[1]?.html_color || 'transparent' }">
            <small>
              {{ ps.split("@")[1] || "" }}
            </small>
          </div>
          <div class="sheen"></div>
        </button>
      </template>
      <div style="flex-grow: 2"></div>
    </div>

    <div class="tool-bar">
      <input v-model="presetFilter" placeholder="Search Presets..." />
      <button @click="presetFilter = ''" class="nogrow">
        <i class="mdi mdi-backspace"></i>
      </button>
    </div>
    <div
      class="flex-row grow scroll"
      data-testid="presets-list"
      style="
        background: var(--alt-control-bg);
        align-items: flex-start;
        align-content: flex-start;
      ">
      <button
        v-bind:key="ps[0]"
        v-for="ps of dictView(presets, sorts, function (k, v) {
          if (checkPresetUsablility(k)) {
            return 1;
          }
        })"
        @click="setFixturePreset(currentcueid, fixture, ps[0])"
        :disabled="no_edit"
        class="preset-button preset-icon"
        popovertarget="presetForFixture"
        popovertargetaction="hide">
        <img
          v-if="getpresetimage(ps[0])"
          :src="
            '/chandler/WebMediaServer?board=' +
            boardname +
            '&file=' +
            encodeURIComponent(getpresetimage(ps[0]))
          " />

        <div
          class="label"
          :style="{ 'background-color': ps[1]?.html_color || 'transparent' }">
          {{ ps[0].split("@")[0] }}
        </div>
        <div
          class="label-bottom"
          :style="{ 'background-color': ps[1]?.html_color || 'transparent' }">
          <small>
            {{ ps[0].split("@")[1] || "" }}
          </small>
        </div>

        <div class="sheen"></div>
      </button>
    </div>
    <div style="h-2rem"></div>
  </div>
</template>

<script setup>
import { presets, boardname, restSetCueValue } from "./boardapi.mjs";
import { dictView } from "./utils.mjs";
import * as Vue from "/static/js/thirdparty/vue.esm-browser.js";

const properties = defineProps({
  fixture: String,
  fordestination: [String, Boolean],
  fixtureclasses: Object,
  fixturetype: String,
  currentcueid: String,
  currentvals: Object,
  getpresetimage: Function,
  no_edit: Boolean,
});

const recentPresets = Vue.ref([]);
const presetFilter = Vue.ref("");

const sorts = Vue.ref([
  "category",
  "!values.green",
  "!values.red",
  "!values.blue",
  "!values.white",
  "!values.dim",
]);

function setFixturePreset(sc, fix, preset) {
  console.log("setFixturePreset", sc, fix, preset);
  const deleteIndex = recentPresets.value.indexOf(preset);

  if (deleteIndex !== -1) {
    recentPresets.value = recentPresets.value.toSpliced(deleteIndex, 1);
  }
  recentPresets.value = recentPresets.value.slice(-8);
  recentPresets.value.push(preset);

  var generic = false;

  // Use a fixture specific preset if available
  var selectedPreset = presets.value[preset + "@" + fix];

  // Else use a type specific preset
  if (selectedPreset == undefined) {
    selectedPreset = presets.value[preset + "@" + properties.fixturetype];
  }

  if (selectedPreset == undefined) {
    selectedPreset = presets.value[preset];
    // Could not find fixture or type specific preset.
    if (!preset.includes("@")) {
      generic = true;
    }
  }

  if (selectedPreset == undefined) {
    return;
  }

  selectedPreset = structuredClone(Vue.toRaw(selectedPreset));

  for (var i in properties.currentvals) {
    // If just editing destinations
    // don't use the special vals.
    if (properties.fordestination && i.includes("__")) {
      continue;
    }

    if (i == "__length__") {
      continue;
    }
    if (i == "__spacing__") {
      continue;
    }
    if (
      typeof selectedPreset.values[i] == "string" &&
      selectedPreset.values[i].length === 0
    ) {
      continue;
    }

    if (selectedPreset.values[i] == "-1") {
      continue;
    }
    if (selectedPreset.values[i] != undefined) {
      if (properties.fordestination) {
        restSetCueValue(sc, fix, "__dest__." + i, selectedPreset.values[i]);
      } else {
        restSetCueValue(sc, fix, i, selectedPreset.values[i]);
      }
    }
  }
  if (!properties.fordestination) {
    restSetCueValue(sc, fix, "__preset__", preset);
  }
}

function checkPresetUsablility(preset) {
  if (
    !preset.toLocaleLowerCase().includes(presetFilter.value.toLocaleLowerCase())
  ) {
    return false;
  }
  if (!preset.includes("@")) {
    return true;
  }
  if (preset.endsWith(properties.fixture)) {
    return true;
  }

  if (properties.fixturetype && preset.endsWith("@" + properties.fixturetype)) {
    return true;
  }

  let clsdata = properties.fixtureclasses[properties.fixturetype];

  if (!clsdata) {
    return false;
  }

  if (
    clsdata &&
    clsdata.color_profile &&
    preset.includes("@") &&
    clsdata.color_profile.startsWith(preset.split("@")[1])
  ) {
    return true;
  }

  return false;
}
</script>

<script>
export default {
  template: "#template",
  name: "fixture-presets-dialog",
};
</script>
