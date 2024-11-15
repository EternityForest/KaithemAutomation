<style scoped></style>

<template>
<section popover id="presetsDialog" ontoggle="globalThis.handleDialogState" class="margin modal flex-item window paper" style="width: 32em; max-height: 90vh">
    <h3>Presets<button type="button" popovertarget="presetsDialog" popovertargetaction="hide">
            <i class="mdi mdi-close"></i>Close</button>
    </h3>
    <details class="help">
        <summary>Help</summary>
        <p> A preset is a set of values that may be quickly applied to
            any feature.
            Create them in the cue values section. They are loaded and
            saved with the "setup" file.
            Empty fields in a preset have no effect, they leave that
            value alone, so you can, for example,
            make a preset that sets the color without setting the XY
            values.
        </p>

        <p>Presets named presetname@fixture are scoped to that fixture
            or fixture type only.
            They only appear for fixture or fixture type.
            They will override any generic "presetname" preset for that
            fixture.

        </p>
    </details>
    <div class="tool-bar">
        <input type="text" v-model="filterPresets" placeholder="Filter">
        <button type="button" class="nogrow" @click="filterPresets = ''"><span class="mdi mdi-backspace"></span></button>
    </div>
    <div class="scroll" style="max-height: 36rem; margin-bottom: 0.5em">
        <dl>
            <template v-for="ps, i of dictView(presets, [])">
                <dt v-if="ps[0].toLowerCase().includes(filterPresets.toLowerCase())">
                    <div class="tool-bar">
                        <b>{{ ps[0] }}</b>
                        <button type="button" popovertarget="presetImageLabel" v-on:click="selectingImageLabelForPreset = ps[0];">
                            <i class="mdi mdi-image-edit-outline"></i>
                            Image</button>

                        <button class="button" type="button" popovertarget="iframeDialog" @click="iframeDialog = getExcalidrawPresetLink(ps[0])">
                            <i class="mdi mdi-fountain-pen-tip"></i>
                            Draw</button>

                        <button type="button" v-on:click="deletePreset(ps[0])"><i class="mdi mdi-delete"></i>Delete</button>
                        <button type="button" v-on:click="renamePreset(ps[0])"><i class="mdi mdi-pencil"></i>Rename</button>
                        <button type="button" v-on:click="copyPreset(ps[0]); filterPresets = ''"><i class="mdi mdi-copy"></i>Copy</button>
                    </div>
                </dt>
                <dd v-if="ps[0].toLowerCase().includes(filterPresets.toLowerCase())">

                    <img v-if="getpresetimage(ps[0])" style="max-height: 8em; max-width: 8em;" :src="'../WebMediaServer?file=' + encodeURIComponent(getpresetimage(ps[0]))">
                    <details>
                        <summary>Values</summary>
                        <div class="stacked-form">
                            <label v-for="val, field of ps[1].values">
                                {{ field }}<input :disabled="no_edit" v-model="ps[1].values[field]" v-on:change="ps[1].values[field] = $event.target.value.trim(); updatepreset(ps[0], ps[1]);">
                            </label>
                        </div>
                    </details>

                </dd>
            </template>

        </dl>
    </div>
</section>
</template>

<script>
import {
    dictView,
    useBlankDescriptions
} from "./utils.mjs?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61";

var data = {
    "filterPresets": "",
}

module.exports = {
    template: '#template',

    props: [
        "getpresetimage", "presets", "no_edit", "updatepreset"
    ],
    data: function () {
        return (data)
    },
    methods: {
        dictView: dictView,
        useBlankDescriptions: useBlankDescriptions,
    },
    "components": {
        "combo-box": window.httpVueLoader("/static/vue/ComboBox.vue"),
    },
    computed: {

    }
}
</script>
