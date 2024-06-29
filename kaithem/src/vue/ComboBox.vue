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
    min-width: 8em;
    width: 180%;
    z-index: 10;
    height: unset;
    max-width: 100%;
}

.highlight {
    border-color: green;
}
</style>

<template>
<div style="display:inline-block;position:relative; overflow: visible;">
    <div class="tool-bar">
        <input  :disabled="disabled" 
         v-bind:value="modelValue" 
         v-on:input="$emit('update:modelValue', $event.target.value); focused = true" 
         v-on:change="focused = false; $emit('update:modelValue', $event.target.value); $emit('change', $event.target.value); "
         v-on:focus="focused = true;"
         v-on:blur="blurTimer()"
         style="flex-basis: 4rem; min-width: 4rem;"
         >
        <button 
        v-on:blur="buttonBlurTimer()"
        :disabled="disabled" title="Show/Hide selector" style="width:3rem; max-width: 3rem;" 
        v-on:click="showmenu = !(showmenu); focused = false; $event.target.focus()" 
        v-bind:class="{ 'highlight': showmenu }"> <i class="mdi mdi-dots-horizontal"></i></button>
    </div>
    <div v-if="showmenu || (focused)" class="comboboxdropdown_wrapper" >
        <div class="comboboxdropdown_inner paper">
            <div style="overflow: scroll; margin: 0.8em; border: 1px solid; height: 18em;">
                <template v-for="i in pinned">
                    <div v-if="(!modelValue) || i[0].toLowerCase().includes(modelValue.toLowerCase()) || i[1].toLowerCase().includes(modelValue.toLowerCase()) || showmenu">
                        <button type="button" :disabled="disabled" v-on:click="$emit('update:modelValue', i[0]); $emit('change', i[0]); showmenu = false; focused = false;" tabindex="-1">{{ i[0] }}</button><br>
                        <p style="margin-left: 1em;">{{ i[1] }}</p>
                    </div>
                </template>

                <template v-for="i in options">
                    <div v-if="(!modelValue) || i[0].toLowerCase().includes(modelValue.toLowerCase()) || i[1].toLowerCase().includes(modelValue.toLowerCase()) || showmenu">
                        <button type="button" :disabled="disabled" v-on:click="$emit('update:modelValue', i[0]); $emit('change', i[0]); showmenu = false; focused = false;" tabindex="-1">{{ i[0] }}</button><br>
                        <p style="margin-left: 1em;">{{ i[1] }}</p>
                    </div>
                </template>
            </div>
            <button title="Show/Hide selector" style="width:auto; margin: 0.4em" v-on:click="showmenu = !(showmenu | (focused)); focused = false;" v-bind:class="{ 'highlight': showmenu }">Cancel</button>
        </div>
    </div>
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
        }
    },
    name: 'ComboBox',
    data: function () {
        return ({
            'log': console.log,
            'showmenu': false,
            focused: false,
            blurTimer: function () {
                setTimeout(() => {
                    this.focused = false;
                }, 120)
            },

            buttonBlurTimer: function () {
                setTimeout(() => {
                    this.showmenu = false;
                }, 120)

            }
        })
    }
}
</script>
