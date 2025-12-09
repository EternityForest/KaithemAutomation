<template id="template">
  <fixture-presets-dialog
    :fixture="selectingPresetFor"
    :fordestination="selectingPresetForDestination"
    :effectid="selectingPresetForEffect"
    :fixtureclasses="fixtureClasses"
    :fixturetype="lookupFixtureType(selectingPresetFor)"
    :currentvals="selectingPresetForOldValue"
    :currentcueid="currentcueid"
    :getpresetimage="getPresetImage"
    :no_edit="no_edit"></fixture-presets-dialog>

  <div class="undecorated">
    <div class="tool-bar noselect noselect">
      <button
        type="button"
        v-bind:class="{ highlight: groupChannelsViewMode == 'cue' }"
        v-on:click="groupChannelsViewMode = 'cue'">
        <i class="mdi mdi-cog-outline"></i>Normal View
      </button>
      <button
        type="button"
        v-bind:class="{
          highlight: groupChannelsViewMode == 'channels',
        }"
        data-testid="add-rm-fixtures-button"
        v-on:click="groupChannelsViewMode = 'channels'">
        <i class="mdi mdi-list-box-outline"></i>Add/Remove Fixtures
      </button>
    </div>

    <div style="max-width: 100%; align-items: baseline">
      <div class="tool-bar noselect">
        <button type="button" v-on:click="addEffectToCue()">
          <i class="mdi mdi-plus"></i>Add Effect
        </button>
      </div>
      <div class="flex-row">
        <div
          v-for="(effect, effectidx) in cuevals[currentcueid]"
          v-bind:key="effectidx"
          class="border grow min-w-8rem">
          <div class="tool-bar" noselect>
            <p>
              <b>{{ effect["type"] }}</b>
            </p>
            <label
              >Type:
              <select
                v-model="effect['type']"
                @change="restSetCueEffectMeta(currentcueid, effect['id'], cuevals[currentcueid][effectidx])">
                <option :value="effect['type']">{{ effect["type"] }}</option>
                <option value="direct">direct</option>

                <option :value="i['name']" v-for="i in plugin_info['kaithem.chandler.lighting-generator']" v-bind:key="i">
                  {{ i['name'] }}
                </option>

              </select>
            </label>
          </div>

          <template
            v-for="(keypoint, u_idx) in effect['keypoints'] || []"
            v-bind:key="u_idx">
            <article
              class="universe card flex-col gaps"
              v-if="keypoint['target'][0] != '@'">
              <header>
                <h3 class="noselect">{{ keypoint["target"] }}</h3>
              </header>
              <details class="undecorated nopadding nomargin">
                <summary data-testid="details-fixture-channels-summary">
                  Channels
                </summary>
                <div class="scroll nomargin flex-row fader-box-inner">
                  <h-fader
                    :groupid="groupname"
                    :chinfo="
                      channelInfoForUniverseChannel(keypoint['target'], chname)
                    "
                    :currentcueid="currentcueid"
                    :showdelete="groupChannelsViewMode == 'channels'"
                    :fixcmd="keypoint['values']"
                    :effect="effect['id']"
                    :chname="chname"
                    :universe="keypoint['target']"
                    :val="keypoint['values'][chname]"
                    v-bind:key="chname"
                    v-for="chname in Object.keys(keypoint['values']).sort()">
                  </h-fader>
                </div>
              </details>
            </article>
          </template>

          <template
            v-for="(keypoint, f_idx) in effect['keypoints'] || {}"
            v-bind:key="f_idx">
            <article
              v-bind:key="f_idx"
              class="fixture card flex-col gaps noselect"
              v-if="keypoint.target[0] == '@'">
              <header>
                <h4 :title="lookupFixtureType(keypoint['target'])">
                  {{ keypoint.target }}
                </h4>

                <div class="tool-bar noselect">
                  <button
                    type="button"
                    @click="
                      showPresetDialog(
                        keypoint['target'],
                        effect['id'],
                        keypoint['values'],
                        false
                      )
                    "
                    popovertarget="presetForFixture"
                    title="Select a preset for this fixture"
                    data-testid="select-preset-for-fixture">
                    <i class="mdi mdi-playlist-play"></i>
                  </button>

                  <select
                    :disabled="no_edit"
                    class="w-4rem nogrow"
                    style="flex-basis: 2rem"
                    data-testid="save-preset-options"
                    v-on:change="
                      savePreset(keypoint, $event.target.value);
                      $event.target.value = '__dummy__';
                    ">
                    <option value="__dummy__">Save</option>
                    <option value="">For Any</option>
                    <option
                      :value="'name' + keypoint['target']"
                      title="Save for use with this fixture">
                      For This
                    </option>
                    <option
                      :value="
                        'name@h-fa' +
                        lookupFixtureColorProfile(keypoint['target'])
                      "
                      title="Save for use with fixtures of this type">
                      For Type
                    </option>
                  </select>
                </div>
                <button
                  type="button"
                  v-if="groupChannelsViewMode == 'channels'"
                  v-on:click="rmFixCue(currentcueid, effect['id'], keypoint['target'])">
                  <i class="mdi mdi-delete"></i>
                </button>
              </header>

              <details
                class="undecorated nopadding nomargin"
                data-testid="details-fixture-channels-summary">
                <summary class="nomargin nopadding">
                  <img
                    v-if="
                      fixtureAssignments[keypoint['target'].slice(1)]
                        ?.label_image
                    "
                    style="max-height: 4em; border-radius: 0.5em;"
                    :src="
                      '/chandler/WebMediaServer?file=' +
                      encodeURIComponent(
                        fixtureAssignments[keypoint['target'].slice(1)]
                          ?.label_image
                      ) +
                      '&ts=' +
                      fixtureAssignments[keypoint['target'].slice(1)]
                        ?.labelImageTimestamp
                    " />

                  <div
                    class="preset-icon"
                    v-if="keypoint.values && keypoint.values.__preset__">
                    <img
                      style="max-height: 4em; object-fit: cover; border-radius: 0.5em;"
                      :src="
                        '/chandler/WebMediaServer?file=' +
                        encodeURIComponent(
                          getPresetImage(keypoint.values.__preset__)
                        )
                      " />

                    <div
                      class="label"
                      :style="{
                        'background-color':
                          presets[keypoint.values.__preset__]?.html_color ||
                          'transparent',
                      }">
                      {{ keypoint.values.__preset__.split("@")[0] }}
                    </div>
                  </div>
                </summary>
                <div
                  class="scroll nomargin padding-bottom flex-row fader-box-inner">
                  <h-fader
                    :groupid="groupname"
                    :chinfo="
                      channelInfoForUniverseChannel(keypoint['target'], chname)
                    "
                    :currentcueid="currentcueid"
                    :showdelete="groupChannelsViewMode == 'channels'"
                    :fixcmd="keypoint['values']"
                    :effect="effect['id']"
                    :chname="chname"
                    :universe="keypoint['target']"
                    :val="keypoint['values'][chname]"
                    v-bind:key="chname"
                    v-for="chname in Object.keys(keypoint['values']).sort()">
                  </h-fader>
                </div>
              </details>
            </article>
          </template>

          <div v-if="groupChannelsViewMode == 'channels'" class="flex-row gaps">
            <div class="card margin">
              <header>
                <h4>Add Raw Channel</h4>
              </header>

              <div class="stacked-form w-20rem">
                <label
                  >Universe
                  <combo-box
                    v-bind:options="useBlankDescriptions(universes)"
                    v-model="newcueu"></combo-box>
                </label>

                <label>
                  Channel
                  <combo-box
                    v-bind:options="getChannelCompletions(newcueu)"
                    v-model="newcuevnumber">
                  </combo-box>
                </label>

                <button
                  type="button"
                  :disabled="no_edit"
                  data-testid="add-channel-to-cue-button"
                  v-on:click="addValueToCue(effect['id'])">
                  <i class="mdi mdi-plus"></i>Add Channel to Cue
                </button>
              </div>
            </div>

            <div class="card margin">
              <header>
                <h4>Add Tag Point</h4>
              </header>

              <div class="stacked-form w-20rem">
                <label
                  >Tag
                  <input v-model="newcuetag" list="tagslisting" />
                </label>

                <button
                  type="button"
                  :disabled="no_edit"
                  v-on:click="addTagToCue(effect['id'])"
                  data-testid="add-tag-to-cue-button">
                  <i class="mdi mdi-plus"></i>Add Tag to Cue
                </button>
              </div>
            </div>

            <div class="card margin w-24rem">
              <header>
                <h4>Add Fixture</h4>
              </header>
              <div class="scroll">
                <table>
                  <tr
                    v-for="(v, i) in fixtureAssignments"
                    v-bind:key="v.universe + '_' + v.channel">
                    <td>{{ v.universe }}:{{ i }} at {{ v.channel }}</td>
                    <td>
                      <button
                        type="button"
                        v-on:click="addfixToCue(currentcueid, effect['id'], i)">
                        <i class="mdi mdi-plus"></i>Add
                      </button>

                      <button
                        type="button"
                        v-on:click="addAutoFix(currentcueid, effectidx, i)">
                        <i class="mdi mdi-plus"></i>Add Auto
                      </button>
                    </td>
                  </tr>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  currentcueid,
  fixtureAssignments,
  no_edit,
  // fixtureClasses,
  cuevals,
  useBlankDescriptions,
  groupname,
  universes,
  presets,
  addfixToCue,
  addAutoFix,
  rmFixCue,
  lookupFixtureType,
  lookupFixtureColorProfile,
  getChannelCompletions,
  savePreset,
  getPresetImage,
  channelInfoForUniverseChannel,
  fixtureClasses,
  restSetCueEffectMeta,
  plugin_info

} from "./boardapi.mjs";

import { ref } from "/static/js/thirdparty/vue.esm-browser.js";

let newcueu = ref("");
let newcuetag = ref("");
let newcuevnumber = ref("");
let selectingPresetForDestination = ref(false);
let selectingPresetForEffect = ref(false);
let selectingPresetForOldValue = ref({});

let selectingPresetFor = ref("");
let groupChannelsViewMode = ref("cue");

function showPresetDialog(fixture, effect, values,destination) {
  // destination lets us set a preset for the end of a range effect
  selectingPresetForDestination.value = destination ? true : false;
  selectingPresetForEffect.value = effect;
  selectingPresetForOldValue.value = values;
  selectingPresetFor.value = fixture;
}
function setCueValue(sc, effect, u, ch, value) {
  value = Number.isNaN(Number.parseFloat(value))
    ? value
    : Number.parseFloat(value);
  globalThis.api_link.send(["scv", sc, effect, u, ch, value]);
}

function addValueToCue(effect) {
  if (!newcueu.value) {
    return;
  }

  setCueValue(
    currentcueid.value,
    effect,
    newcueu.value,
    newcuevnumber.value,
    0
  );
}

function addEffectToCue() {
  if (cuevals.value[currentcueid.value].length > 0) {
    alert("Cue already has a default effect");
    return;
  }

  restSetCueEffectMeta(currentcueid.value, "default", {
    type: "direct",
    keypoints: {},
    auto: [],
  });
}
function addTagToCue(effect) {
  if (!newcuetag.value) {
    return;
  }
  if (!newcuetag.value.startsWith("/")) {
    alert("Tag must start with /");
    return;
  }

  setCueValue(currentcueid.value, effect, newcuetag.value, "value", 0);
}
</script>

<script type="module">
export default {
  name: "console-app",
  template: "#template",
  components: {
    "fixture-presets-dialog": globalThis.httpVueLoader(
      "./fixture-presets-dialog.vue"
    ),
    "combo-box": globalThis.httpVueLoader("/static/vue/ComboBox.vue"),
    "h-fader": globalThis.httpVueLoader("./hfader.vue"),
    // "fixture-presets-dialog": globalThis.httpVueLoader(
    //   "./fixture-presets-dialog.vue"
    // )
  },
};
</script>
