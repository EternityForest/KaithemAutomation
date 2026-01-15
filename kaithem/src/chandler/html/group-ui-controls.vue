<style scoped>
input {
  width: 100%;
}

.preview-frame {
  width: 400%;
  height: 32em;
  margin: 0px;
  padding: 0px;
  transform: scale(0.25);
  transform-origin: 0 0;
}

.preview-frame-wrapper {
  overflow: hidden;
  width: 100%;
  height: 8em;
}
</style>

<template id="group-ui">
  <div>
    <details
      v-on:toggle="groupData.doSlideshowEmbed = $event.target.open"
      style="margin: 0px; padding: 0px"
      v-if="
        groupData?.slideOverlayUrl ||
        cue?.slide ||
        cue?.markdown ||
        groupData?.doSlideshowEmbed ||
        groupData?.soundOutput == 'groupwebplayer' ||
        cue?.soundOutput == 'groupwebplayer'
      ">
      <summary class="noselect">
        <a :href="'./webmediadisplay?group=' + groupData.id">(slideshow)</a>
      </summary>
      <div class="preview-frame-wrapper">
        <iframe
          v-if="groupData.doSlideshowEmbed"
          class="preview-frame"
          :src="'./webmediadisplay?group=' + groupData.id"></iframe>
      </div>
    </details>

    <div class="warning" v-if="!groupData.enableTiming">
      <i class="mdi mdi-warning"></i>
      Timing Disabled
    </div>
    <table border="0">
      <tbody>
        <tr v-for="(v, i) in groupData.timers" :key="i + v">
          <td>{{ i }}</td>
          <td
            style="width: 8em"
            v-bind:class="{
              warning: v - unixtime < 60,
              blinking: v - unixtime < 5,
            }">
            {{ formatInterval(v - unixtime) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { formatInterval } from "./utils.mjs";
const props = defineProps({
  unixtime: Number,
  groupData: Object,
  cue: Object,
});
</script>
