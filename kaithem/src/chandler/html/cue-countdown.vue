<style scoped></style>


<template id="cue-cd">
    <div style="position: relative; width: fit-content;">
        <meter style="height: calc(var(--control-height) * 1.5);" v-bind:high=" (cue.length>30)?(scene.cuelen*(60/scene.bpm))-10:(scene.cuelen*(60/scene.bpm))"
            v-if="scene.active && cue && cue.length" min=0 v-bind:max="scene.cuelen*(60/scene.bpm)"
            v-bind:value="unixtime-scene.enteredCue"></meter>
        <span style="position: absolute; left:2px; top:calc(var(--control-height) * 0.25)" v-if="scene.active && cue && cue.length">{{((scene.cuelen*(60/scene.bpm))-(unixtime-scene.enteredCue))>-0.1
            ? formatInterval((scene.cuelen*(60/scene.bpm))-(unixtime-scene.enteredCue)) : "NOW"}}
        </span>
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
    template: '#cue-cd',
    props: ['unixtime', 'cue', 'scene'],
    data: function () {
        return ({ 'formatInterval': formatInterval })
    }
}

</script>