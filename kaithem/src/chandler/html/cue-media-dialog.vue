<style scoped></style>

<template>
  <div
    v-if="currentcue && editinggroup"
    class="window w-full modal"
    popover
    id="cueMediaDialog"
    ontoggle="globalThis.handleDialogState(event)">
    <header>
      <div class="tool-bar">
        <h4>{{ currentcue.name }} Sound</h4>
        <button
          class="nogrow"
          type="button"
          popovertarget="cueMediaDialog"
          popovertargetaction="hide"
          data-testid="close-cue-media">
          <i class="mdi mdi-close"></i>Close
        </button>
      </div>
    </header>

    <p>
      <a :href="'./webmediadisplay?group=' + editinggroup.id"
        >Web Media Display</a
      >
    </p>

    <div class="flex-row gaps">
      <div class="card w-sm-full">
        <header>
          <h3>Cue Media</h3>
        </header>
        <div class="stacked-form">
          <label
            >Sound
            <input
              data-testid="cue-sound-control"
              :disabled="no_edit"
              placeholder="No sound file"
              v-bind:value="currentcue.sound"
              v-on:change="
                setCueProperty(currentcue.id, 'sound', $event.target.value)
              " />
          </label>
          <label
            >Web player slide
            <input
              data-testid="cue-slide-control"
              :disabled="no_edit"
              placeholder="No media file"
              v-bind:value="currentcue.slide"
              v-on:change="
                setCueProperty(currentcue.id, 'slide', $event.target.value)
              " />
          </label>

          <label
            >Label Image
            <input
              :disabled="no_edit"
              placeholder="No picture file"
              data-testid="cue-label-image-control"
              v-bind:value="currentcue.labelImage"
              v-on:change="
                setCueProperty(currentcue.id, 'labelImage', $event.target.value)
              " />
            <button
              class="button"
              popovertarget="iframeDialog"
              @click="
                iframeDialog = getExcalidrawCueLink(
                  editinggroup.name,
                  currentcue
                )
              ">
              Draw
            </button>
          </label>
          <label v-if="currentcue.labelImage.length > 0"
            >Label Image Preview
            <img
              :src="
                '/chandler/WebMediaServer?labelImg=' +
                encodeURIComponent(currentcue.id) +
                '&timestamp=' +
                encodeURIComponent(currentcue.labelImageTimestamp)
              "
              class="h-center"
              style="max-height: 4em" />
          </label>

          <p>
            <label
              >Sound start
              <input
                :disabled="no_edit"
                v-bind:value="currentcue.soundStartPosition"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'soundStartPosition',
                    $event.target.value
                  )
                " />s into file.
            </label>

            <label
              >Media Speed
              <input
                :disabled="no_edit"
                type="number"
                v-bind:value="currentcue.mediaSpeed"
                step="0.1"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'mediaSpeed',
                    $event.target.value
                  )
                " />
            </label>
          </p>

          <p>
            <label
              >Windup
              <input
                :disabled="no_edit"
                type="number"
                v-bind:value="currentcue.mediaWindUp"
                step="0.1"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'mediaWindUp',
                    $event.target.value
                  )
                " />
            </label>

            <label
              >Winddown
              <input
                :disabled="no_edit"
                type="number"
                v-bind:value="currentcue.mediaWindDown"
                step="0.1"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'mediaWindDown',
                    $event.target.value
                  )
                " />
            </label>
          </p>

          <label
            >Device

            <datalist id="soundcards">
              <option value="groupwebplayer">
                Play media file in web player
              </option>
              <option
                v-for="i of soundcards"
                v-bind:key="i"
                v-bind:value="i"></option>
              <option value="@auto"></option>
              <option value="@pulse:hw:0,0"></option>
              <option value="@alsa:hw:0,0"></option>
            </datalist>

            <input
              title="Using mplayer -ao syntax, or one of kaithem's device aliases, set the output device"
              v-on:change="
                setCueProperty(
                  currentcue.id,
                  'soundOutput',
                  $event.target.value
                )
              "
              v-bind:value="currentcue.soundOutput"
              placeholder="default"
              list="soundcards" />
          </label>

          <p>
            <label
              >Relative length
              <input
                :disabled="no_edit"
                type="checkbox"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'relLength',
                    $event.target.checked
                  )
                "
                v-bind:checked="currentcue.relLength"
                title="If checked, the length parameter is interpreted as a delay after the sound cue ends." />
            </label>

            <label
              >Fade sound after end
              <input
                :disabled="no_edit"
                type="number"
                step="0.1"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'soundFadeOut',
                    $event.target.value
                  )
                "
                min="0"
                v-bind:value="currentcue.soundFadeOut"
                title="Sound should fade out starting when the cue ends, taking this long." />
            </label>
          </p>

          <p>
            <label
              >Sound fadein:
              <input
                :disabled="no_edit"
                type="number"
                step="0.1"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'soundFadeIn',
                    $event.target.value
                  )
                "
                min="-1"
                v-bind:value="currentcue.soundFadeIn"
                title="Sound should fade in if starting from, taking this long. Use -1 to override and disable a global group crossfade." />
            </label>

            <label
              >Cue Volume
              <input
                :disabled="no_edit"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'soundVolume',
                    $event.target.value
                  )
                "
                min="0"
                v-bind:value="currentcue.soundVolume" />
            </label>

            <label
              >Loops
              <input
                :disabled="no_edit"
                title="-1 means forever"
                v-on:change="
                  setCueProperty(
                    currentcue.id,
                    'soundLoops',
                    $event.target.value
                  )
                "
                min="-1"
                v-bind:value="currentcue.soundLoops" />
            </label>
          </p>
        </div>
      </div>
      <div
        class="w-sm-double flex-col gaps"
        data-testid="media-browser-container">
        <media-browser :no_edit="no_edit" :selectfolders="false">
          <template v-slot="slotProps">
            <button
              v-on:click="
                setCueProperty(currentcue.id, 'sound', slotProps.filename)
              ">
              Set(sound)
            </button>
            <button v-on:click="newCueFromSound(groupname, slotProps.filename)">
              New(sound)
            </button>
            <button v-on:click="previewSound(slotProps.filename)">
              Preview
            </button>
            <button
              v-on:click="
                setCueProperty(currentcue.id, 'slide', slotProps.filename)
              ">
              Set(slide)
            </button>
            <button v-on:click="newCueFromSlide(groupname, slotProps.filename)">
              New(slide)
            </button>

            <button
              v-on:click="
                setCueProperty(
                  currentcue.id,
                  'labelImage',
                  slotProps.relfilename
                )
              "
              v-if="
                slotProps.filename.endsWith('.jpg') ||
                slotProps.filename.endsWith('.svg') ||
                slotProps.filename.endsWith('.png') ||
                slotProps.filename.endsWith('.gif') ||
                slotProps.filename.endsWith('.jpeg') ||
                slotProps.filename.endsWith('.avif')
              ">
              Set Label
            </button>
          </template>
        </media-browser>
        <div class="max-h-12rem flex-col border card">
          <header>
            <h4>Sound Outputs</h4>
          </header>
          <details class="help">
            <summary><i class="mdi mdi-help-circle-outline"></i></summary>
            To use play videos, you must use the web remote display feature. Cue
            videos will play in the browser on connected remote displays.
          </details>
          <div class="scroll">
            <dl>
              <dt>Web Player</dt>
              <dd>
                <div class="tool-bar">
                  <button
                    v-on:click="
                      setCueProperty(
                        currentcue.id,
                        'soundOutput',
                        'groupwebplayer'
                      )
                    ">
                    Set for Cue
                  </button>
                  <button
                    v-on:click="
                      setgroupproperty(
                        groupname,
                        'soundOutput',
                        'groupwebplayer'
                      )
                    ">
                    Set as Group Default
                  </button>
                </div>
              </dd>

              <template v-for="i of soundcards" v-bind:key="i">
                <dt>{{ i || "UNSET" }}</dt>
                <dd>
                  <div class="tool-bar">
                    <button
                      type="button"
                      v-on:click="
                        setCueProperty(currentcue.id, 'soundOutput', i)
                      ">
                      Set for Cue
                    </button>
                    <button
                      type="button"
                      v-on:click="
                        setgroupproperty(groupname, 'soundOutput', i)
                      ">
                      Set as Group Default
                    </button>
                    <button
                      type="button"
                      v-on:click="testsoundcard(i, 0, 48000)">
                      Test
                    </button>
                  </div>
                </dd>
              </template>
            </dl>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { getExcalidrawCueLink, iframeDialog } from "./editor.mjs";
import {
  newCueFromSound,
  newCueFromSlide,
  setCueProperty,
} from "./boardapi.mjs";

defineProps([
  "no_edit",
  "soundcards",
  "currentcue",
  "editinggroup",
  "groupname",
  "setgroupproperty",
  "testsoundcard",
]);

function previewSound(s) {
  document.querySelector("#soundpreviewdialog").show();
  var t = [".mp3", ".ogg", ".wav", ".oga", ".opus", ".aac", ".flac"];
  for (let i of t) {
    if (s.endsWith(i)) {
      document.querySelector("#soundpreview").src =
        "/chandler/WebMediaServer?file=" + encodeURIComponent(s);
      document.querySelector("#soundpreview").currentTime = 0;
      document.querySelector("#soundpreview").play();
      document.querySelector("#textpreview").src = "";
      document.querySelector("#textpreview").style.display = "none";
      document.querySelector("#soundpreview").style.display = "block";
      return;
    }
  }
  document.querySelector("#textpreview").src =
    "/chandler/WebMediaServer?file=" + encodeURIComponent(s);
  document.querySelector("#soundpreview").src = "";
  document.querySelector("#textpreview").style.display = "block";
  document.querySelector("#soundpreview").style.display = "none";
}
</script>

<script>
var data = {};

export default {
  template: "#template",

  data: function () {
    return data;
  },
  components: {
    "media-browser": globalThis.httpVueLoader("./media-browser.vue"),
  },
};
</script>
