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


<template id="scene-ui">
    <div>

        <details v-on:toggle="sceneData.doSlideshowEmbed= $event.target.open" style="margin: 0px; padding: 0px;"
         v-if="sceneData.slideOverlayUrl || (cue && (cue.slide || cue.markdown) ) || sceneData.doSlideshowEmbed || sceneData.soundOutput=='scenewebplayer' || cue.soundOutput=='scenewebplayer'">
            <summary>
                <a 
                    :href="'/chandler/webmediadisplay?scene=' + sceneData.id">(slideshow)</a>
            </summary>
            <div class="preview-frame-wrapper">
            <iframe v-if="sceneData.doSlideshowEmbed" class="preview-frame"
                    :src="'/chandler/webmediadisplay?scene=' + sceneData.id"></iframe>
            </div>
        </details>
        <div class="flex-row gaps" v-if="sceneData.displayTags.length > 0">

            <div :style="{ 'min-width': v[2].width + 'rem' }" v-for="v in sceneData.displayTags">
                <label><b>{{ v[0] }}</b></label>

                <template v-if="v[2].type == 'meter'">
                    <div>
                        <meter v-if="sceneData.displayTagMeta[v[1]]" :min="sceneData.displayTagMeta[v[1]].min"
                            :max="sceneData.displayTagMeta[v[1]].max" :high="sceneData.displayTagMeta[v[1]].hi"
                            :lo="sceneData.displayTagMeta[v[1]].lo" :value="sceneData.displayTagValues[v[1]]"></meter>

                        <span class="numval">{{ sceneData.displayTagValues[v[1]] }}</span>
                    </div>
                </template>

                <template v-if="v[2].type == 'text'">
                    <div>
                        {{ sceneData.displayTagValues[v[1]] }}
                    </div>
                </template>

                <template v-if="v[2].type == 'led'">
                    <div style="min-width: 4em">
                        <span class="numval"><small>{{ sceneData.displayTagValues[v[1]].toFixed(1) }}<small></small></span><input type="checkbox" 
                        :class="{ 'led': 1, 'led-red':v[2].color=='red', 'led-yellow':v[2].color=='yellow', 'led-green':v[2].color=='green', 'led-blue':v[2].color=='blue',  'led-purple':v[2].color=='purple'}"
                            v-bind:checked="sceneData.displayTagValues[v[1]]" disabled>
                    </div>
                </template>

                <template v-if="v[2].type == 'string_input'">
                    <div>
                        <input type="text" v-model="sceneData.displayTagValues[v[1]]"
                            v-on:change="setTagInputValue(sceneData.id, v[1], sceneData.displayTagValues[v[1]])">
                    </div>
                </template>

                <template v-if="v[2].type == 'numeric_input'">
                    <div>
                        <input type="number" v-model="sceneData.displayTagValues[v[1]]"
                            v-on:change="setTagInputValue(sceneData.id, v[1], sceneData.displayTagValues[v[1]])">
                    </div>
                </template>


                <template v-if="v[2].type == 'switch_input'">
                    <div>
                        <input type="checkbox" class="toggle"
                            v-bind:value="sceneData.displayTagValues[v[1]] ? true : false"
                            v-on:change="setTagInputValue(sceneData.id, v[1], sceneData.displayTagValues[v[1]])">
                    </div>
                </template>

                </div>
            </div>
        </div>

        <table border="0">
            <tbody>
                <tr v-for="(v, i) in sceneData.timers">
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

formatInterval = function (seconds) {
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds - (hours * 3600)) /
        60);
    var seconds = seconds - (hours * 3600) - (minutes * 60);
    var tenths = Math.floor((seconds - Math.floor(seconds)) *
        10);
    seconds = Math.floor(seconds);

    var time = "";

    time = ("" + hours).padStart(2, '0') + ":" + ("" + minutes).padStart(2, '0') + ":" + ("" + seconds).padStart(2, '0')
    return time;
}


module.exports = {
    template: '#scene-ui',
    props: ['unixtime', 'sceneData', 'cue'],
    data: function () {
        return ({ 'formatInterval': formatInterval })
    },
    methods: {
        'setTagInputValue': function (sc, tag, v) {
            /*api_link is global*/
            api_link.send(['inputtagvalue', sc, tag, v])
        }
    }
}

</script>