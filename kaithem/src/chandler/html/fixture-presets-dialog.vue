<style scoped></style>

<template id="h-fader">
    <div popover id="presetForFixture" v-if="fixture" class="card paper flex-col"
        style="background: var(--alt-control-bg); position: fixed; width:90vw; height: 90vh; top:5vh; left:5vw; z-index: 100">
        <header>Presets for {{ fixture }}</header>
        <button class="w-full nogrow" popovertarget="presetForFixture"
            popovertargetaction="hide">
            <i class="mdi mdi-close"></i>Close
        </button>
        <div class="flex-row nogrow max-h-12rem scroll" style="align-items:flex-start;align-content:flex-start">
            <template v-for="ps of recentPresets.toReversed()">
                <button
                    v-if="!ps.includes('@') || ps.endsWith(fixture) || ps.endsWith('@' +fixturetype)"
                    @click="setFixturePreset(currentcueid, fixture, ps);"
                    :disabled="no_edit" class="preset-button"
                    popovertarget="presetForFixture"
                    popovertargetaction="hide"></button>
                    <img v-if="getpresetimage(ps)"
                        :src="'../WebMediaServer?file=' + encodeURIComponent(getpresetimage(ps))">
                    <div>{{ ps.split('@')[0] }}</div>
                </button>

            </template>
            <div style="flex-grow: 2;"></div>

        </div>

        <div class="tool-bar">
            <input v-model="presetFilter" placeholder="Search Presets..." />
            <button @click="presetFilter = ''" class="nogrow"><i class="mdi mdi-backspace"></i></button>
        </div>
        <div class="flex-row grow scroll"
            style="background: var(--alt-control-bg); align-items:flex-start;align-content:flex-start">
            <button
                v-for="ps of dictView(presets, [], function (k, v) { if ((((!k.includes('@')) || k.endsWith(fixture) || k.endsWith('@' +fixturetype))) && k.includes(presetFilter)) { return 1 } })"
                @click="setFixturePreset(currentcueid, fixture, ps[0]);"
                :disabled="no_edit" class="preset-button"
                popovertarget="presetForFixture"
                popovertargetaction="hide"
                >
                <img v-if="getpresetimage(ps[0])"
                    :src="'../WebMediaServer?file=' + encodeURIComponent(getpresetimage(ps[0]))">

                <div>{{ ps[0].split('@')[0] }}</div>
            </button>
        </div>

    </div>

</template>


<script type="module">
import { dictView } from  "./utils.mjs?cache_version=452dc529-8f57-41e0-8fb3-c485ce1dfd61";
var data =
{

    'recentPresets': [],
    'presetFilter':'',

    'setFixturePreset': function (sc, fix, preset) {
        const deleteIndex = this.recentPresets.indexOf(preset);

        if (deleteIndex > -1) {
            this.recentPresets = this.recentPresets.toSpliced(deleteIndex, 1);
        }
        this.recentPresets = this.recentPresets.slice(-8);
        this.recentPresets.push(preset);

        var generic = false

        // Use a fixture specific preset if available
        var selectedPreset = this.presets[preset + '@' + fix]

        // Else use a type specific preset
        if (selectedPreset == undefined) {
            selectedPreset = this.presets[preset + '@' + this.fixturetype]
        }

        if (selectedPreset == undefined) {
            selectedPreset = this.presets[preset]
            // Could not find fixture or type specific preset.
            if (preset.indexOf('@') == -1) {
                generic = true
            }
        }

        if (selectedPreset == undefined) {
            return
        }

        selectedPreset = JSON.parse(JSON.stringify(selectedPreset))

        // if (generic) {
        //     // If using a generic preset, we want to apply the white
        //     // balance correction if at all possible.
        //     var cal_white = this.presets['cal.white@' + fix]
        //     var cal_white = cal_white || this.presets['cal.white@' + this.lookupFixtureType(fix)]
        //     if (cal_white) {
        //         for(i of ['red', 'green', 'blue', 'white']) {
        //             if (cal_white.values[i] != undefined) {
        //                 if(selectedPreset.values[i] != undefined) {
        //                     selectedPreset.values[i] *= (cal_white.values[i] / 255)
        //                     selectedPreset.values[i] = parseInt(selectedPreset.values[i])
        //                 }
        //             }
        //         }
        //     }
        // }

        for (var i in this.currentvals) {
            if (selectedPreset.values[i] != undefined) {
                window.api_link.send(['scv', sc, fix, i, selectedPreset.values[i]]);
            }
        }
    },
}

module.exports = {
    template: '#template',

    props: ['presets', 'fixture', 'fixturetype', 'currentcueid', 'currentvals', 'getpresetimage', "no_edit"],
    data: function () {
        return (data)
    },
    methods: {
        dictView: dictView
    }
}

</script>