<style scoped></style>

<template id="h-fader">
  <div class="hfader" style="-webkit-user-drag: none" v-if="props.chname[0] != '_'">
    <b class="w-full" v-if="props.chinfo == undefined">{{ props.chname }}</b>

    <div>
      <b
        v-if="props.chinfo"
        class="noselect"
        v-bind:title="'Actual channel:' + props.universe + ':' + props.chname"
        >{{ props.chname }}</b
      >
      <button
        v-if="props.showdelete"
        v-on:click="rmValFromCue(props.currentcueid, props.effect, props.universe, props.chname)">
        <i class="mdi mdi-delete"></i>Remove
      </button>
    </div>

    <div v-if="typeof props.val == 'string'">
      <input
        v-bind:disabled="props.chinfo && props.chinfo.type == 'fine'"
        v-on:input="setCueVal(props.currentcueid, props.effect, props.universe, props.chname, props.val)"
        v-bind:value="props.val"
        v-on:change="
          setCueVal(props.currentcueid, props.effect, props.universe, props.chname, $event.target.value)
        " />
    </div>

    <div v-if="typeof props.val == 'number'">
      <div v-if="props.val !== null && props.val != -1000001">
        <smooth-range
          v-bind:disabled="props.chinfo && props.chinfo.type == 'fine'"
          v-if="!(props.chname == '__length__' || props.chname == '__spacing__')"
          v-bind:step="props.chinfo && props.chinfo.type == 'fine' ? 0.01 : 1"
          :min="getValueRange(props.chinfo, props.val).min"
          :max="getValueRange(props.chinfo, props.val).max"
          @update:modelValue="
            setCueVal(
              props.currentcueid,
              props.effect,
              props.universe,
              props.chname,
              parseFloat($event)
            )
          "
          :modelValue="props.val">
        </smooth-range>
      </div>
      <span v-if="props.val == -1000001" class="grey">AUTO</span>

      <span v-if="props.val == null" class="grey">Released</span>

      <span
        v-if="!(props.chinfo && props.chinfo.type == 'fine') && props.val != -1000001"
        title="Double click to set exact value"
        class="noselect"
        v-on:dblclick="promptExactVal(props.currentcueid, props.effect, props.universe, props.chname)"
        style="font-size: 80%"
        >{{ Number(props.val).toPrecision(4) }}</span
      >
      <span class="grey" v-if="props.chinfo && props.chinfo.type == 'fine'">auto</span>

      <span
        v-if="props.chinfo && props.chinfo == undefined"
        v-bind:style="{
          'background-color': 'rgb(' + props.val + ',' + props.val + ',' + props.val + ')',
        }"
        class="indicator"></span>

      <div v-if="props.chinfo && props.chinfo.type == 'custom'">
        <br />
        <select
          :value="getValueRange(props.chinfo, props.val).name"
          v-on:change="
            setCueVal(
              props.currentcueid,
              props.effect,
              props.universe,
              props.chname,
              mapvaluerange(props.val, props.chinfo, $event.target.value)
            )
          ">
          <option v-for="i of props.chinfo.ranges" :value="i.name">
            {{ i.name }}({{ i.min }} to {{ i.max }})
          </option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup>

import SmoothRange  from "../../vue/smooth-range.vue";
  const props = defineProps({
    chinfo: Object,
    currentcueid: Number,
    groupid: Number,
    showdelete: Boolean,
    fixcmd: Object,
    effect: String,
    universe: Number,
    val: Number,
    chname: String,
  })



function promptExactVal (cue, effect, u, v) {
    var x = prompt("Enter new value for group");

    if (x != null) {
      setCueVal(cue, effect, u, v, x);
    }
  }
function setCueVal (sc, effect, u, ch, value) {
    // console.log(sc, effect, u, ch, value);
    if (props.fixcmd["__preset__"] && props.fixcmd["__preset__"].length > 0) {
      globalThis.api_link.send(["scv",sc, effect,  u, "__preset__", null]);
    }

    value = Number.isNaN(Number.parseFloat(value)) ? value : Number.parseFloat(value);
    globalThis.api_link.send(["scv", sc,effect, u, ch, value]);
  }

  //Returns new value mapped into the range when user clicks to change the range of a custom val
  //Given current val, list of all ranges,  and old range info
function mapvaluerange (oldv, d, newrange) {
    const newd = d.ranges.find((x) => x.name == newrange);
    return newd.min;
  }
function getValueRange (d, v) {
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
  }

function rmValFromCue (cue, effect, universe, ch) {
    globalThis.api_link.send(["scv", cue, effect, universe, ch, null]);
  }

</script>
