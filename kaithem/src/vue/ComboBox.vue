<style scoped>
.comboboxdropdown_inner {
        /* z stack fix*/
        transform: translate(0,0);
    position: absolute;
    backdrop-filter: blur(2px);
    border-radius: 1em;
    border-style: solid;
    border-color: black;
    border-width: 2px;
    max-height: 24em;
    min-width: 8em;
    width: 180%;
    z-index: 10;
    height: unset;
    max-width: 100%;
}


.comboboxdropdown_wrapper{

    position: absolute;
    max-height: 24em;

    min-height: 12em;
    min-width: 8em;
    width: 180%;
    z-index: 10;
    height: unset;
    max-width: calc(min(100%, 32em));
}

.highlight {
    border-color: green;
}
</style>

<template>
<div style="display:inline-block;position:relative; overflow: visible;">

        <datalist :id="uid">
                <option  v-for="i in pinned" :value="i[0]">{{ i[1] }}</option>

                <option  v-for="i in options" :value="i[0]">{{ i[1] }}</option>

        </datalist>

        <input  :disabled="disabled" 
         :data-testid="testid"
         :list="uid"
         v-bind:value="modelValue" 
         v-on:input="$emit('update:modelValue', $event.target.value)" 
         v-on:change="$emit('update:modelValue', $event.target.value); $emit('change', $event.target.value); "
         style="flex-basis: 4rem; min-width: 4rem;">
    
    
</div>
</template>

<script>
//Important note: There are two ways to open the menu. Clicking the menu button turns off filtering.
module.exports = {

    emits: ['change', 'input', 'update:modelValue'],
    props: {
        'pinned': {
            type: Array,
            default: function () {
                return []
            }
        },
        'options': {
            type: Array,
            default: function () {
                return []
            }
        },
        'modelValue': {
            type: String,
            default: ''
        },
        'disabled': {
            type: Boolean,
            default: false
        },
        "testid": {
            type: String,
            default: ''
        }
    },
    name: 'ComboBox',
    data: function () {
        return ({
            'log': console.log,
            uid: Date.now()+Math.random(),
        })
    }
}
</script>
