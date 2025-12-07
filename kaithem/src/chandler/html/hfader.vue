<style scoped></style>

<template id="h-fader">
  <div class="hfader" style="-webkit-user-drag: none"
  v-if="chname[0] != '_'"
  >
    <b class="w-full" v-if="chinfo == undefined">{{ chname }}</b>

    <div>
      <b
        v-if="chinfo"
        class="noselect"
        v-bind:title="'Actual channel:' + universe + ':' + chname"
        >{{ chname }}</b
      >
      <button
        v-if="showdelete"
        v-on:click="rmValFromCue(currentcueid, effect, universe, chname)">
        <i class="mdi mdi-delete"></i>Remove
      </button>
    </div>

    <div v-if="typeof val == 'string'">
      <input
        v-bind:disabled="chinfo && chinfo.type == 'fine'"
        v-on:input="setCueVal(currentcueid, effect, universe, chname, val)"
        v-model.lazy="val"
        v-on:change="
          setCueVal(currentcueid, effect, universe, chname, $event.target.value)
        " />
    </div>

    <div v-if="typeof val == 'number'">
      <div v-if="val !== null">
        <smooth-range
          v-bind:disabled="chinfo && chinfo.type == 'fine'"
          v-if="!(chname == '__length__' || chname == '__spacing__')"
          v-bind:step="chinfo && chinfo.type == 'fine' ? 0.01 : 1"
          :min="getValueRange(chinfo, val).min"
          :max="getValueRange(chinfo, val).max"
          @update:modelValue="
            setCueVal(currentcueid, effect, universe, chname, parseFloat($event))
          "
          v-model.number="val">
        </smooth-range>
      </div>

      <span v-if="val == null" class="grey">Released</span>

      <span
        v-if="!(chinfo && chinfo.type == 'fine')"
        title="Double click to set exact value"
        class="noselect"
        v-on:dblclick="
          promptExactVal(currentcueid, effectname, universe, chname)
        "
        style="font-size: 80%"
        >{{ Number(val).toPrecision(4) }}</span
      >
      <span class="grey" v-if="chinfo && chinfo.type == 'fine'">auto</span>

      <span
        v-if="chinfo && chinfo == undefined"
        v-bind:style="{
          'background-color': 'rgb(' + val + ',' + val + ',' + val + ')',
        }"
        class="indicator"></span>

      <div v-if="chinfo && chinfo.type == 'custom'"
        ><br />
        <select
          :value="getValueRange(chinfo, val).name"
          v-on:change="
            setCueVal(
              currentcueid,
              effect,
              universe,
              chname,
              mapvaluerange(val, chinfo, $event.target.value)
            )
          ">
          <option v-for="i of chinfo.ranges" :value="i.name">
            {{ i.name }}({{ i.min }} to {{ i.max }})
          </option>
        </select>
      </div>
    </div>
  </div>
</template>

<script>
var hfaderdata = {
  promptExactVal: function (cue, effect, u, v) {
    var x = prompt("Enter new value for group");

    if (x != null) {
      this.setCueVal(cue, effect, u, v, x);
    }
  },
  setCueVal: function (sc, effect, u, ch, value) {
    // console.log(sc, effect, u, ch, value);
    if (this.fixcmd["__preset__"] && this.fixcmd["__preset__"].length > 0) {
      globalThis.api_link.send(["scv",sc, effect,  u, "__preset__", null]);
    }

    value = Number.isNaN(Number.parseFloat(value)) ? value : Number.parseFloat(value);
    globalThis.api_link.send(["scv", sc,effect, u, ch, value]);
  },

  //Returns new value mapped into the range when user clicks to change the range of a custom val
  //Given current val, list of all ranges,  and old range info
  mapvaluerange: function (oldv, d, newrange) {
    const newd = d.ranges.find((x) => x.name == newrange);
    return newd.min;
  },
  getValueRange: function (d, v) {
    //Given a channel info structure thing and a value, return the [min,max,name] of the range
    //that the value is in
    if (d?.ranges) {
      for (var i of d.ranges) {
        if (v >= i.min && v <= i.max) {
          return i;
        }
      }
    }

    return { min: 0, max: 255, name: "" };
  },

  rmValFromCue: function (cue, effect, universe, ch) {
    globalThis.api_link.send(["scv", cue, effect, universe, ch, null]);
  },
};

export default {
  template: "#h-fader",
  //I is a data object having u,ch, and v, the universe channel and value.
  //Chinfo is the channel info list from the fixtues that you get with channelInfoForUniverseChannel
  props: [
    "chinfo",
    "currentcueid",
    "groupid",
    "showdelete",
      "fixcmd",
    "effect",

    "universe",
    "val",
    "chname",
  ],
  data: function () {
    return hfaderdata;
  },
  components: {
    "smooth-range": globalThis.httpVueLoader("/static/vue/smoothrange.vue"),
  },
};
</script>
