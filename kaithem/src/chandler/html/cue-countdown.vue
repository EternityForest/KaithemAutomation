<style scoped></style>


<template id="cue-cd">
    <div style="position: relative; width: fit-content;">
        <span v-if="group.active && cue && (cue.length || cue.relLength)"
        :data-count-ref="group.enteredCue"
        :data-count-bpm="group.bpm"
        :data-count-len="group.cuelen">
        </span>
    </div>
</template>



<script>

// See boardapi update_countdowns function to actually make it work

formatInterval = function (seconds) {

    var sign = ''

    if (seconds< 0){
        seconds = -seconds;
        sign = "-"
    }
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds - (hours * 3600)) /
        60);
    var seconds = seconds - (hours * 3600) - (minutes * 60);
    var tenths = Math.floor((seconds - Math.floor(seconds)) *
        10);
    seconds = Math.floor(seconds);

    var time = "";

    time = ("" + hours).padStart(2, '0') + ":" + ("" + minutes).padStart(2, '0') + ":" + ("" + seconds).padStart(2, '0')
    return sign+time;
}


module.exports = {
    template: '#cue-cd',
    props: ['cue', 'group'],
    data: function () {
        return ({ 'formatInterval': formatInterval })
    }
}

</script>