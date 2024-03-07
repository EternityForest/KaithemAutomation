<style scoped>
.comboboxdropdown {
    position: absolute;
    backdrop-filter: blur(2px);
    border-radius: 1em;
    border-style: solid;
    border-color: black;
    border-width: 2px;
    max-height: 24em;
    min-width: 8em;
    width: 180%;
    z-index: 1000;
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
        <input v-bind:value="value" v-on:input="$emit('input', $event.target.value); focused = true"
            v-on:change="focused = false; $emit('change', $event.target.value);" v-on:focus="focused = true;">
        <button title="Show/Hide selector" style="width:3em;" v-on:click="showmenu = !(showmenu | (focused)); focused = false;"
            v-bind:class="{ 'highlight': showmenu }">...</button>
    </div>
    <div v-if="showmenu || (focused)" class="comboboxdropdown paper">
            <div style="overflow: scroll; margin: 0.8em; border: 1px solid; height: 18em;">
                <div v-for="i in pinned"
                    v-if="(!value) || i[0].toLowerCase().includes(value.toLowerCase()) || i[1].toLowerCase().includes(value.toLowerCase()) || showmenu">
                    <button v-on:click="$emit('input', i[0]); $emit('change', i[0]); showmenu = false; focused = false;"
                        tabindex=-1>{{ i[0] }}</button><br>
                    <p style="margin-left: 1em;">{{ i[1] }}</p>
                </div>

                <div v-for="i in options"
                    v-if="(!value) || i[0].toLowerCase().includes(value.toLowerCase()) || i[1].toLowerCase().includes(value.toLowerCase()) || showmenu">
                    <button v-on:click="$emit('input', i[0]); $emit('change', i[0]); showmenu = false; focused = false;"
                        tabindex=-1>{{ i[0] }}</button><br>
                    <p style="margin-left: 1em;">{{ i[1] }}</p>
                </div>
            </div>
            <button title="Show/Hide selector" style="width:auto; margin: 0.4em" v-on:click="showmenu = !(showmenu | (focused)); focused = false;"
                v-bind:class="{ 'highlight': showmenu }">Cancel</button>
    </div>
    </div>
</template>

<script>
//Important note: There are two ways to open the menu. Clicking the menu button turns off filtering.
module.exports = {

    props: {
        'pinned': { type: Array, default: function () { return [] } },
        'options': { type: Array, default: function () { return [] } },
        'value': { type: String, default: '' }
    },
    name: 'ComboBox',
    data: function () {
        return (
            {
                'showmenu': false,
                focused: false
            })
    }
}

</script>