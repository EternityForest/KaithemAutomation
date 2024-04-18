<style scoped></style>

<template id="h-fader">
    <div class="hfader">
        <b class="w-full" v-if="chinfo == undefined">{{ i.ch }}</b>

        <div>
            <b v-if="chinfo" v-bind:title="'Actual channel:' + i.u + ':' + i.ch">{{ i.ch }}</b>
            <button v-if="showdelete" v-on:click="rmValFromCue(i.u, i.ch)"><i class="mdi mdi-delete"></i>Remove</button>
        </div>

        <span v-if="typeof (i.v) == 'string'">
            <input v-bind:disabled="chinfo && chinfo[2] == 'fine'" v-if="!monitor"
                v-on:input="setCueVal(currentcueid, i.u, i.ch, i.v)" v-model.lazy="i.v"
                v-on:change="setCueValNolock(currentcueid, i.u, i.ch, $event.target.value)">

        </span>

        <span v-if="typeof (i.v) == 'number'">
            <span v-if="i.v !== null">
                <input v-bind:disabled="chinfo && chinfo[2] == 'fine'"
                    v-if="(!monitor) && (!(i.ch == '__length__' || i.ch == '__spacing__'))" type="range"
                    v-bind:step="(chinfo && chinfo[2] == 'fine') ? 0.01 : 1" :min="getValueRange(chinfo, i.v)[0]"
                    :max="getValueRange(chinfo, i.v)[1]"
                    v-on:input="setCueVal(currentcueid, i.u, i.ch, parseFloat($event.target.value))" v-model.number="i.v"
                    v-on:change="setCueValNolock(currentcueid, i.u, i.ch, parseFloat($event.target.value))">

                <input v-bind:disabled="chinfo && chinfo[2] == 'fine'"
                    v-if="(!monitor) && (i.ch == '__length__' || i.ch == '__spacing__')" type="number"
                    v-bind:step="(chinfo && chinfo[2] == 'fine') ? 0.01 : 1" :min="getValueRange(chinfo, i.v)[0]"
                    :max="getValueRange(chinfo, i.v)[1]"
                    v-on:input="setCueVal(currentcueid, i.u, i.ch, parseFloat($event.target.value))" v-model.number="i.v"
                    v-on:change="setCueValNolock(currentcueid, i.u, i.ch, parseFloat($event.target.value))">


                <meter v-if="monitor" type="range" max=255 v-bind:value="i.v"></meter>
            </span>

            <span v-if="i.v == null" class=grey>Released</span>



            <span v-if="!(chinfo && chinfo[2] == 'fine')" title="Double click to set exact value"
                v-on:dblclick="promptExactVal(currentcueid, i.u, i.ch)"
                style="font-size:80%">{{ Number(i.v).toPrecision(4) }}</span>
            <span class=grey v-if="chinfo && chinfo[2] == 'fine'">auto</span>

            <span v-if="chinfo && (chinfo[2] == 'red')"
                v-bind:style="{ 'background-color': 'rgb(' + i.v + ',0,0)', 'border-color': 'red' }" class="indicator"></span>
            <span v-if="chinfo && (chinfo[2] == 'green')"
                v-bind:style="{ 'background-color': 'rgb(0,' + i.v + ',0)', 'border-color': 'green' }" class="indicator"></span>
            <span v-if="chinfo && (chinfo[2] == 'blue')"
                v-bind:style="{ 'background-color': 'rgb(0,0,' + i.v + ')', 'border-color': 'blue' }" class="indicator"></span>
            <span v-if="chinfo && chinfo[2] == 'uv'"
                v-bind:style="{ 'background-color': 'rgb(i.v,0,' + i.v + ')', 'border-color': 'blue' }" class="indicator"></span>
            <span v-if="chinfo && chinfo[2] == 'custom'" v-bind:style="{ 'background-color': 'rgb(' + i.v + ',' + i.v + ',' + i.v + ')' }"
                class="indicator"></span>
            <span v-if="chinfo && chinfo[2] == 'intensity'"
                v-bind:style="{ 'background-color': 'rgb(' + i.v + ',' + i.v + ',' + i.v + ')' }" class="indicator"></span>
            <span v-if="chinfo && chinfo[2] == 'white'" v-bind:style="{ 'background-color': 'rgb(' + i.v + ',' + i.v + ',' + i.v + ')' }"
                class="indicator"></span>
            <span v-if="chinfo && chinfo[2] == 'fog'" v-bind:style="{ 'background-color': 'rgb(' + i.v + ',' + i.v + ',' + i.v + ')' }"
                class="indicator"></span>

            <span v-if="chinfo && chinfo == undefined" v-bind:style="{ 'background-color': 'rgb(' + i.v + ',' + i.v + ',' + i.v + ')' }"
                class="indicator"></span>


            <span v-if="chinfo && chinfo[2] == 'custom'"><br>
                <select :value="getValueRange(chinfo, i.v)[2]"
                    v-on:change="setCueValNolock(currentcueid, i.u, i.ch, mapvaluerange(i.v, chinfo, $event.target.value))">
                    <option v-for="i of chinfo.slice(3)" :value="i[2]">{{ i[2] }}({{ i[0] }} to {{ i[1] }})</option>
                </select>
            </span>
        </span>
    </div>
</template>


<script>
var hfaderdata =
{
    'promptExactVal': function (cue, u, v) {
        var x = prompt("Enter new value for scene")

        if (x != null) {

            this.setCueValNolock(cue, u, v, x);
        }
    },
    'setCueVal': function (sc, u, ch, val) {
        val = isNaN(parseFloat(val)) ? val : parseFloat(val)
        appData.lockedFaders[sc + ":" + u + ":" + ch] = true;
        api_link.send(['scv', sc, u, ch, val]);
    },
    'setCueValNolock': function (sc, u, ch, val) {
        val = isNaN(parseFloat(val)) ? val : parseFloat(val)
        api_link.send(['scv', sc, u, ch, val]);
    },
    'unlockCueValFader': function (sc, u, ch) {
        delete appData.lockedFaders[sc + ":" + u + ":" + ch];
    },
    'getValueRange': getValueRange,

    'rmValFromCue': function (universe, ch) {
        api_link.send(['scv', appData.scenecues[appData.scenename]
        [appData.selectedCues[appData.scenename]],
            universe,
            ch,
            null
        ])
        Vue.delete(appData.cuevals[appData.selectedCues[appData
            .scenename]][appData.newcueu],
            ch)
        Vue.delete(appData.cuevals[appData.selectedCues[appData
            .scenename]][appData.newcueu],
            ch)
    },
}

module.exports = {
    template: '#h-fader',
    //I is a data object having u,ch, and v, the universe channel and value.
    //Chinfo is the channel info list from the fixtues that you get with chnamelookup
    props: ['i', 'chinfo', 'monitor', 'currentcueid', 'showdelete'],
    data: function () {
        return (hfaderdata)
    }
}

</script>