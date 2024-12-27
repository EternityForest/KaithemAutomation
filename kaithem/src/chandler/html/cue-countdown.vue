<style scoped></style>


<template id="cue-cd">
    <div v-if="group.active && cue && (cue.length || cue.relLength)" style="position: relative; width: fit-content;">
        <i class="mdi mdi-clock-end"></i>
        <span :data-count-ref="group.enteredCue" :data-count-bpm="group.bpm" :data-count-len="group.cuelen">
        </span>
    </div>
</template>



<script>
import { formatInterval } from "./utils.mjs";

// See boardapi update_countdowns function to actually make it work



export default {
    template: '#cue-cd',
    props: ['cue', 'group'],
    data: function () {
        return ({ 'formatInterval': formatInterval })
    }
}

</script>