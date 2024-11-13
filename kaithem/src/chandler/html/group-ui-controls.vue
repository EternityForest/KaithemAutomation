<style scoped>
input {
    width: 100%;
}
.preview-frame{
    width: 400%;
    height: 32em;
    margin: 0px;
    padding: 0px;
    transform: scale(0.25);
    transform-origin: 0 0;
}

.preview-frame-wrapper{
    overflow: hidden;
    width: 100%;
    height: 8em;
}
</style>


<template id="group-ui">
    <div>

        <details v-on:toggle="groupData.doSlideshowEmbed= $event.target.open" style="margin: 0px; padding: 0px;"
         v-if="groupData.slideOverlayUrl || (cue && (cue.slide || cue.markdown) ) || groupData.doSlideshowEmbed || groupData.soundOutput=='groupwebplayer' || cue.soundOutput=='groupwebplayer'">
            <summary class="noselect">
                <a 
                    :href="'/chandler/webmediadisplay?group=' + groupData.id">(slideshow)</a>
            </summary>
            <div class="preview-frame-wrapper">
            <iframe v-if="groupData.doSlideshowEmbed" class="preview-frame"
                    :src="'/chandler/webmediadisplay?group=' + groupData.id"></iframe>
            </div>
        </details>
        <div  class="noselect" class="flex-row gaps" v-if="groupData.displayTags.length > 0">

            <div :style="{ 'min-width': v[2].width + 'rem' }" v-for="v in groupData.displayTags">
                <label><b>{{ v[0] }}</b></label>

                <template v-if="v[2].type == 'meter'">
                    <div>
                        <meter v-if="groupData.displayTagMeta[v[1]]" :min="groupData.displayTagMeta[v[1]].min"
                            :max="groupData.displayTagMeta[v[1]].max" :high="groupData.displayTagMeta[v[1]].hi"
                            :lo="groupData.displayTagMeta[v[1]].lo" :value="groupData.displayTagValues[v[1]]"></meter>

                        <span class="numval">{{ groupData.displayTagValues[v[1]] }}</span>
                    </div>
                </template>

                <template v-if="v[2].type == 'text'">
                    <div>
                        {{ groupData.displayTagValues[v[1]] }}
                    </div>
                </template>

                <template v-if="v[2].type == 'led'">
                    <div style="min-width: 4em">
                        <span class="numval"><small>{{ groupData.displayTagValues[v[1]].toFixed(1) }}<small></small></span><input type="checkbox" 
                        :class="{ 'led': 1, 'led-red':v[2].color=='red', 'led-yellow':v[2].color=='yellow', 'led-green':v[2].color=='green', 'led-blue':v[2].color=='blue',  'led-purple':v[2].color=='purple'}"
                            v-bind:checked="groupData.displayTagValues[v[1]]" disabled>
                    </div>
                </template>

                <template v-if="v[2].type == 'string_input'">
                    <div>
                        <input type="text" v-model="groupData.displayTagValues[v[1]]"
                            v-on:change="setTagInputValue(groupData.id, v[1], groupData.displayTagValues[v[1]])">
                    </div>
                </template>

                <template v-if="v[2].type == 'numeric_input'">
                    <div>
                        <input type="number" v-model="groupData.displayTagValues[v[1]]"
                            v-on:change="setTagInputValue(groupData.id, v[1], groupData.displayTagValues[v[1]])">
                    </div>
                </template>


                <template v-if="v[2].type == 'switch_input'">
                    <div>
                        <input type="checkbox" class="toggle"
                            v-bind:value="groupData.displayTagValues[v[1]] ? true : false"
                            v-on:change="setTagInputValue(groupData.id, v[1], groupData.displayTagValues[v[1]])">
                    </div>
                </template>

                </div>
            </div>
        </div>

        <table border="0">
            <tbody>
                <tr v-for="(v, i) in groupData.timers">
                    <td>{{ i }}</td>
                    <td style="width:8em;" v-bind:class="{ warning: (v - unixtime) < 60, blinking: (v - unixtime) < 5 }">
                        {{ formatInterval((v - unixtime)) }}
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</template>



<script>
import { formatInterval} from "./utils.mjs?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61";


module.exports = {
    template: '#group-ui',
    props: ['unixtime', 'groupData', 'cue'],
    data: function () {
        return ({ 'formatInterval': formatInterval })
    },
    methods: {
        'setTagInputValue': function (sc, tag, v) {
            /*window.api_link is global*/
            window.api_link.send(['inputtagvalue', sc, tag, v])
        }
    }
}

</script>