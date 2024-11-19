<style scoped></style>

<template id="h-fader">
    <div class="hfader" style="-webkit-user-drag: none;">
        <b class="w-full" v-if="chinfo == undefined">{{ i.ch }}</b>

        <div>
            <b v-if="chinfo" class="noselect" v-bind:title="'Actual channel:' + i.u + ':' + i.ch">{{ i.ch }}</b>
            <button v-if="showdelete" v-on:click="rmValFromCue(currentcueid,i.u, i.ch)"><i class="mdi mdi-delete"></i>Remove</button>
        </div>

        <span v-if="typeof (i.v) == 'string'">
            <input v-bind:disabled="chinfo && chinfo.type == 'fine'"
                v-on:input="setCueVal(currentcueid, i.u, i.ch, i.v)" v-model.lazy="i.v"
                v-on:change="setCueVal(currentcueid, i.u, i.ch, $event.target.value)">

        </span>

        <span v-if="typeof (i.v) == 'number'">
            <span v-if="i.v !== null">
                <smooth-range v-bind:disabled="chinfo && chinfo.type == 'fine'"
                    v-if="(!(i.ch == '__length__' || i.ch == '__spacing__'))"
                    v-bind:step="(chinfo && chinfo.type == 'fine') ? 0.01 : 1" :min="getValueRange(chinfo, i.v).min"
                    :max="getValueRange(chinfo, i.v).max"
                    @update:modelValue="setCueVal(currentcueid, i.u, i.ch, parseFloat($event))" v-model.number="i.v">
                </smooth-range>

            </span>

            <span v-if="i.v == null" class=grey>Released</span>

            <span v-if="!(chinfo && chinfo.type == 'fine')" title="Double click to set exact value" class="noselect"
                v-on:dblclick="promptExactVal(currentcueid, i.u, i.ch)"
                style="font-size:80%">{{ Number(i.v).toPrecision(4) }}</span>
            <span class=grey v-if="chinfo && chinfo.type == 'fine'">auto</span>

            <span v-if="chinfo && chinfo == undefined"
                v-bind:style="{ 'background-color': 'rgb(' + i.v + ',' + i.v + ',' + i.v + ')' }"
                class="indicator"></span>


            <span v-if="chinfo && chinfo.type == 'custom'"><br>
                <select :value="getValueRange(chinfo, i.v).name"
                    v-on:change="setCueVal(currentcueid, i.u, i.ch, mapvaluerange(i.v, chinfo, $event.target.value))">
                    <option v-for="i of chinfo.ranges" :value="i.name">{{ i.name }}({{ i.min }} to {{ i.max }})</option>
                </select>
            </span>
        </span>
    </div>
</template>


<script>
var hfaderdata =
{
    'promptExactVal': function (cue, u, v) {
        var x = prompt("Enter new value for group")

        if (x != null) {

            this.setCueVal(cue, u, v, x);
        }
    },
    'setCueVal': function (sc, u, ch, val) {
        val = isNaN(parseFloat(val)) ? val : parseFloat(val)
        window.api_link.send(['scv', sc, u, ch, val]);
    },

    //Returns new value mapped into the range when user clicks to change the range of a custom val
    //Given current val, list of all ranges,  and old range info
    'mapvaluerange': function (oldv, d, newrange) {
        const newd = d.ranges.find(x => x.name == newrange)
        return newd.min
    },
    'getValueRange': function (d, v) {
        //Given a channel info structure thing and a value, return the [min,max,name] of the range
        //that the value is in
        if (d?.ranges) {
            for (var i of d.ranges) {
                if ((v >= i.min) && (v <= i.max)) {
                    return (i)
                }
            }
        }

        return ({min:0, max:255, name:""})
    },

    'rmValFromCue': function (cue, universe, ch) {
        window.api_link.send(['scv', cue,
            universe,
            ch,
            null
        ])
    },
}

module.exports = {
    template: '#h-fader',
    //I is a data object having u,ch, and v, the universe channel and value.
    //Chinfo is the channel info list from the fixtues that you get with channelInfoForUniverseChannel
    props: ['i', 'chinfo', 'currentcueid', 'groupid','showdelete'],
    data: function () {
        return (hfaderdata)
    },
    components: {
        'smooth-range': window.httpVueLoader('/static/vue/smoothrange.vue?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61')
    },
}

</script>