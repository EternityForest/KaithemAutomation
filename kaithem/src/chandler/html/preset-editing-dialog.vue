<style scoped></style>

<template>
  <section
    popover
    id="presetsDialog"
    ontoggle="globalThis.handleDialogState"
    class="margin modal flex-item window paper"
    style="width: 32em; max-height: 90vh">
    <datalist id="colorcategories">
      <option>neutral</option>
      <option>teal</option>
      <option>amber</option>
      <option>violet</option>
      <option>green</option>
      <option>utility</option>
    </datalist>

    <h3>
      Presets<button
        type="button"
        popovertarget="presetsDialog"
        popovertargetaction="hide">
        <i class="mdi mdi-close"></i>Close
      </button>
    </h3>

    <div
      v-if="selectingImageLabelForPreset"
      class="card paper flex-col"
      popover
      id="presetImageLabel"
      style="
        position: fixed;
        width: 90vw;
        height: 90vh;
        top: 5vh;
        left: 5vw;
        z-index: 100;
      ">
      <header>Label for {{ selectingImageLabelForPreset }}</header>
      <button
        @click="selectingImageLabelForPreset = null"
        popovertargetaction="hide"
        class="w-full nogrow">
        <i class="mdi mdi-close"></i>Close
      </button>

      <hr />
      <input
        class="w-full h-2rem nogrow"
        type="text"
        @change="
          updatepreset(
            selectingImageLabelForPreset,
            presets[selectingImageLabelForPreset]
          )
        "
        v-model="presets[selectingImageLabelForPreset].label_image" />

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
                presets[selectingImageLabelForPreset].label_image =
                  slotProps.relfilename;
                updatepreset(
                  selectingImageLabelForPreset,
                  presets[selectingImageLabelForPreset]
                );
              ">
              Use
            </button>
          </template>
        </media-browser>
      </div>
    </div>

    <details class="help">
      <summary>Help</summary>
      <p>
        A preset is a set of values that may be quickly applied to any feature.
        Create them in the cue values section. They are loaded and saved with
        the "setup" file. Empty fields in a preset have no effect, they leave
        that value alone, so you can, for example, make a preset that sets the
        color without setting the XY values.
      </p>

      <p>
        Presets named presetname@fixture are scoped to that fixture or fixture
        type only. They only appear for fixture or fixture type. They will
        override any generic "presetname" preset for that fixture.
      </p>
    </details>
    <div class="tool-bar">
      <input type="text" v-model="filterPresets" placeholder="Filter" />
      <button type="button" class="nogrow" @click="filterPresets = ''">
        <span class="mdi mdi-backspace"></span>
      </button>
    </div>
    <div class="scroll" style="max-height: 36rem; margin-bottom: 0.5em">
      <dl>
        <template v-for="(ps, i) of dictView(presets, [])">
          <dt
            v-if="ps[0].toLowerCase().includes(filterPresets.toLowerCase())"
            :data-testid="'preset-inspector-' + ps[0] + '-heading'"
            v-bind:key="ps[0]">
            <div class="tool-bar">
              <p>
                <b>{{ ps[0] }}</b>
              </p>
              <button
                type="button"
                popovertarget="presetImageLabel"
                v-on:click="selectingImageLabelForPreset = ps[0]">
                <i class="mdi mdi-image-edit-outline"></i>
                Image
              </button>

              <button
                class="button"
                type="button"
                popovertarget="iframeDialog"
                @click="setIframeDialog(getExcalidrawPresetLink(ps[0]))">
                <i class="mdi mdi-fountain-pen-tip"></i>
                Draw
              </button>

              <button type="button" v-on:click="deletepreset(ps[0])">
                <i class="mdi mdi-delete"></i>Delete
              </button>
              <button type="button" v-on:click="renamepreset(ps[0])">
                <i class="mdi mdi-pencil"></i>Rename
              </button>
              <button
                type="button"
                v-on:click="
                  copypreset(ps[0]);
                  filterPresets = '';
                ">
                <i class="mdi mdi-copy"></i>Copy
              </button>
            </div>
          </dt>
          <dd
            :data-testid="'preset-inspector-' + ps[0] + '-body'"
            v-if="ps[0].toLowerCase().includes(filterPresets.toLowerCase())"
            v-bind:key="ps[0]">
            <img
              v-if="getpresetimage(ps[0])"
              style="max-height: 8em; max-width: 8em"
              :src="
                '/chandler/WebMediaServer?file=' +
                encodeURIComponent(getpresetimage(ps[0]))
              " />
            <details>
              <div class="stacked-form">
                <label
                  ><i class="mdi mdi-format-list-bulleted"></i>Category
                  <input
                    :disabled="no_edit"
                    v-model="ps[1].category"
                    type="text"
                    list="colorcategories"
                    v-on:change="
                      ps[1].category = $event.target.value.trim();
                      updatepreset(ps[0], ps[1]);
                    " />
                </label>

                <label
                  ><i class="mdi mdi-format-color-fill"></i>HTML color
                  <input
                    :disabled="no_edit"
                    v-model="ps[1].html_color"
                    type="color"
                    v-on:change="
                      ps[1].html_color = $event.target.value.trim();
                      updatepreset(ps[0], ps[1]);
                    " />
                </label>
              </div>
              <summary>Values</summary>
              <div class="stacked-form">
                <label v-for="(val, field) of ps[1].values" v-bind:key="field">
                  {{ field
                  }}<input
                    :disabled="no_edit"
                    v-model="ps[1].values[field]"
                    v-on:change="
                      ps[1].values[field] = $event.target.value.trim();
                      updatepreset(ps[0], ps[1]);
                    " />
                </label>
              </div>
            </details>
          </dd>
        </template>
      </dl>
    </div>
  </section>
</template>

<script setup>
import { dictView } from "./utils.mjs";
import * as Vue from "/static/js/thirdparty/vue.esm-browser.js";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const properties = defineProps({
  getpresetimage: Function,
  presets: Object,
  no_edit: Boolean,
  updatepreset: Function,
  deletepreset: Function,
  renamepreset: Function,
  copypreset: Function,
});

const filterPresets = Vue.ref("");
const selectingImageLabelForPreset = Vue.ref("");

function setIframeDialog(url) {
  globalThis.setIframeDialog(url);
}
function getExcalidrawPresetLink(preset) {
  return (
    "/excalidraw-plugin/edit?module=" +
    encodeURIComponent(globalThis.boardname.split(":")[0]) +
    "&resource=" +
    encodeURIComponent(
      "media/chandler/sketches/preset_" +
        globalThis.boardname.split(":")[1] +
        "_" +
        preset +
        "_" +
        globalThis.session_time +
        ".excalidraw.png"
    ) +
    "&callback=" +
    encodeURIComponent(
      "/chandler/label_image_update_callback/preset/" +
        globalThis.boardname +
        "/" +
        preset
    ) +
    "&ratio_guide=16_9"
  );
}
</script>

<script>
export default {
  template: "#template",
  components: {
    "media-browser": globalThis.httpVueLoader("./media-browser.vue"),
  },
  computed: {},
};
</script>
