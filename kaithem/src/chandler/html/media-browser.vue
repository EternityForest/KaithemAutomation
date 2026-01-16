<style scoped></style>

<!-- This file gives you  browser for active chandler media folders.
It takes a set of action button slots that get passed "filename"
-->
<template id="media-browser">
  <div class="card w-full flex-col gaps">
    <header>
      <h3>Media browser</h3>
    </header>
    <div class="tool-bar">
      <input
        :disabled="props.no_edit"
        v-model="soundsearch"
        v-on:change="soundsearchresults = []"
        v-on:keyup.enter="doSoundSearch(soundsearch)"
        placeholder="Filter Sounds"
        style="width: 60%" />
      <button type="button" v-on:click="doSoundSearch(soundsearch)">
        Search
      </button>
      <button type="button" v-on:click="soundsearch = ''">Clear Search</button>
    </div>
    <div class="scroll h-24rem w-full padding">
      <div v-if="soundsearch.length > 0" class="w-full">
        <table border="1" class="w-full">
          <tr>
            <th>File</th>
            <th>Action</th>
          </tr>
          <tr v-for="i in soundsearchresults" v-bind:key="i[1]">
            <td v-bind:title="'Found in' + i[0]">{{ i[1] }}</td>
            <td>
              <slot :filename="soundfilesdir + i[1]" :relfilename="i[1]">
              </slot>
            </td>
          </tr>
        </table>
      </div>

      <div v-if="soundsearch == ''">
        <h4>
          <a
            title="View in file manager"
            v-bind:href="'/settings/files' + encodeURI(soundfilesdir)"
            target="_blank"
            >{{ soundfilesdir }}</a
          >
        </h4>

        <ul class="w-full noselect">
          <li v-on:click="setSoundfileDir('')"><a>&ltTOP DIRECTORY&gt</a></li>
          <li v-on:click="setSoundfileDir(soundfilesdir)">
            <a><i class="mdi mdi-refresh"></i>Refresh</a>
          </li>
          <li
            v-if="soundfilesdir"
            v-on:click="
              setSoundfileDir(
                ((soundfilesdir.match(/(.*)[\/\\]/)[1] || '').match(
                  /(.*)[\/\\]/
                )[1] || '') + '/'
              )
            ">
            <a>..</a>
          </li>
          <li
            v-on:click="setSoundfileDir(i[0])"
            v-for="i in soundfileslisting[0]"
            v-bind:key="i[0]">
            <a>{{ i[1] }}</a>
            <slot
              v-if="props.selectfolders"
              :filename="i[0]"
              :relfilename="i[0].split('/').pop()">
            </slot>
          </li>
        </ul>

        <table border="1" class="w-full">
          <thead>
            <tr>
              <th style="width: 40%">File</th>
              <th>Action</th>
            </tr>
          </thead>
          <tr v-for="i of soundfileslisting[1]" v-bind:key="i[0]">
            <td class="w-12rem">
              <header>{{ i[1] }}</header>
              <img
                :src="
                  '/chandler/file_thumbnail?file=' +
                  encodeURIComponent(soundfilesdir + i[0])
                "
                style="max-height: 3rem; max-width: 5rem" />
            </td>
            <td>
              <slot :filename="i[0]" :relfilename="i[0]"> </slot>
            </td>
          </tr>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
const props = defineProps({
    no_edit: Boolean,
    selectfolders: Boolean
})

let soundsearch = ref('')
let soundfilesdir = ref('')
let soundfileslisting = ref([[], []])
let soundsearchresults = ref([])

function  doSoundSearch(s) {
        globalThis.api_link.send(["searchsounds", s])
    }
function setSoundfileDir(i) {
    if ((i == '') | (i[0] == '/')) {
        soundfilesdir.value = i;
    }
    else {
        soundfilesdir.value += i;
    }
    soundfileslisting.value = [
        [],
        []
    ]
    globalThis.api_link.send(['listsoundfolder', i])
}


function onsoundfolderlisting(e) {
    const v = e.data
    if (v[0] == soundfilesdir.value) {
        soundfileslisting.value = v[1]
    }
}
globalThis.addEventListener('onsoundfolderlisting', onsoundfolderlisting)
function onsoundsearchresults(e) {
    const v = e.data
    console.log(v)
    if (soundsearch.value == v[0]) {
        soundsearchresults.value = v[1]
    }

}

globalThis.addEventListener('onsoundsearchresults', onsoundsearchresults)
</script>
