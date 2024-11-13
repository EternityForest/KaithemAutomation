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
import { formatInterval} from "./utils.mjs?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61";

// See boardapi update_countdowns function to actually make it work



module.exports = {
    template: '#cue-cd',
    props: ['cue', 'group'],
    data: function () {
        return ({ 'formatInterval': formatInterval })
    }
}

</script>