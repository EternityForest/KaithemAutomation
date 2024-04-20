<style scoped></style>


<template id="cue-cd">
    <div style="position: relative; width: fit-content;">
        <meter style="height: calc(var(--control-height) * 1.5);" v-bind:high=" (cue.length>30)?(scene.cuelen*(60/scene.bpm))-10:(scene.cuelen*(60/scene.bpm))"
            v-if="scene.active && cue && cue.length" min=0 v-bind:max="scene.cuelen*(60/scene.bpm)"
            v-bind:data-meter-ref="scene.enteredCue"></meter>
        <span class="outline-text" style="position: absolute; left:2px; top:calc(var(--control-height) * 0.25)" v-if="scene.active && cue && cue.length"
        :data-count-ref="scene.enteredCue"
        :data-count-len="scene.cuelen">
        </span>
    </div>
</template>



<script>

// See boardapi update_countdowns function to actually make it work

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
    props: ['cue', 'scene'],
    data: function () {
        return ({ 'formatInterval': formatInterval })
    }
}

</script>