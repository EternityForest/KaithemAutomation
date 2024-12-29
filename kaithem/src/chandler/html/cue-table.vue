<style scoped></style>

<template id="cue-table">
  <div class="flex-col">
    <div class="tool-bar">
      <p style="flex-grow: 300">
        <input
          v-model="cuefilter"
          placeholder="Search Cues"
          @change="page = 0" />
        <button type="button" v-on:click="cuefilter = ''">
          <i class="mdi mdi-backspace"></i>
        </button>
      </p>

      <label
        >Page
        <input
          v-model="page"
          type="number"
          min="0"
          max="99"
          style="width: 6em" />
      </label>
      <button type="button" v-on:click="page -= 1" :disabled="page == 0">
        <span class="mdi mdi-page-previous" title="Previous Page"></span>
      </button>
      <button type="button" v-on:click="page += 1">
        <span class="mdi mdi-page-next" title="Next Page"></span>
      </button>
    </div>

    <div style="overflow-y: auto; max-height: 12em">
      <table class="reflow w-full" border="1">
        <thead class="noselect">
          <slot name="header"></slot>
        </thead>

        <tbody>
          <template v-for="i in formatCues()">
            <slot name="row" :i="i"></slot>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import { dictView } from "./utils.mjs";

export default {
  template: "#cue-table",
  name: "cue-table",
  //I is a data object having u,ch, and v, the universe channel and value.
  //Chinfo is the channel info list from the fixtues that you get with channelInfoForUniverseChannel
  props: ["groupname", "groupcues", "cuemeta"],
  methods: {
    formatCues: function () {
      var z = {};
      var filt = true;
      //list cue objects
      for (var i in this.groupcues[this.groupname]) {
        var m = this.cuemeta[this.groupcues[this.groupname][i]];
        if (
          m !== undefined &&
          !filt | i.toLowerCase().includes(this.cuefilter.toLowerCase())
        ) {
          z[i] = m;
        }
      }
      if (filt) {
        return this.dictView(z, ["number"], undefined, this.page).filter(
          (item) => item[1].id
        );
      } else {
        let fc =this.dictView(
          z,
          ["number"],
          undefined,
          this.page
        ).filter((item) => item[1].id);
          return fc;
      }
    },
    dictView: dictView,
  },
  data: function () {
    return {
      page: 0,
      cuefilter: "",
    };
  },
};
</script>
