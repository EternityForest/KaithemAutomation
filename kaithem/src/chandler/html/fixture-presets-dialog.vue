<style scoped></style>

<template>
    <div popover id="presetForFixture" v-if="fixture" class="card paper flex-col"
        style="background: var(--alt-control-bg); position: fixed; width:98vw; height: 90vh; top:1vh; left:1vw; z-index: 100">
        <header>Presets for {{ fixture }}
            <span v-if="fordestination"> destination value</span>
        </header>
        <button class="w-full nogrow" popovertarget="presetForFixture" popovertargetaction="hide">
            <i class="mdi mdi-close"></i>Close
        </button>
        <div class="flex-row nogrow max-h-12rem scroll" style="align-items:flex-start;align-content:flex-start">
            <template v-for="ps of recentPresets.toReversed()">
                <button v-if="checkPresetUsablility(ps)" @click="setFixturePreset(currentcueid, fixture, ps);"
                    :disabled="no_edit" class="preset-button preset-icon" popovertarget="presetForFixture"
                    popovertargetaction="hide">
                    <img v-if="getpresetimage(ps)"
                        :src="'../WebMediaServer?file=' + encodeURIComponent(getpresetimage(ps))">
                    <div class="label" :style="{ 'background-color': presets[ps]?.html_color || 'transparent' }">
                        {{ ps.split('@')[0] }}</div>
                    <div class="label-bottom" :style="{ 'background-color': ps[1]?.html_color || 'transparent' }">
                        <small>
                            {{ ps.split('@')[1] || '' }}
                        </small>
                    </div>
                    <div class="sheen"></div>
                </button>

            </template>
            <div style="flex-grow: 2;"></div>

        </div>

        <div class="tool-bar">
            <input v-model="presetFilter" placeholder="Search Presets..." />
            <button @click="presetFilter = ''" class="nogrow"><i class="mdi mdi-backspace"></i></button>
        </div>
        <div class="flex-row grow scroll" data-testid="presets-list"
            style="background: var(--alt-control-bg); align-items:flex-start;align-content:flex-start">
            <button
                v-for="ps of dictView(presets, sorts, function (k, v) { if (checkPresetUsablility(k)) { return 1 } })"
                @click="setFixturePreset(currentcueid, fixture, ps[0]);" :disabled="no_edit"
                class="preset-button preset-icon" popovertarget="presetForFixture" popovertargetaction="hide">
                <img v-if="getpresetimage(ps[0])"
                    :src="'../WebMediaServer?file=' + encodeURIComponent(getpresetimage(ps[0]))">


                <div class="label" :style="{ 'background-color': ps[1]?.html_color || 'transparent' }">
                    {{ ps[0].split('@')[0] }}</div>
                <div class="label-bottom" :style="{ 'background-color': ps[1]?.html_color || 'transparent' }"><small>
                        {{ ps[0].split('@')[1] || '' }}
                    </small>
                </div>

                <div class="sheen"></div>

            </button>
        </div>
        <div style="h-2rem"></div>

    </div>
</template>

<script>
import {
    dictView
} from "./utils.mjs?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0";
var data = {

    'recentPresets': [],
    'presetFilter': '',

    'sorts': ["category", "!values.green", "!values.red", "!values.blue", "!values.white", "!values.dim"],
    'setFixturePreset': function (sc, fix, preset) {
        console.log('setFixturePreset', sc, fix, preset)
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

        console.log(selectedPreset)

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

            // If just editing destinations
            // don't use the special vals.
            if (this.fordestination) {
                if (i.includes('__')) {
                    continue
                }
            }

            if (i == "__length__") {
                continue
            }
            if (i == "__spacing__") {
                continue
            }
            if (typeof (selectedPreset.values[i]) == 'string') {
                if(selectedPreset.values[i].length == 0) {
                    continue
                }
                
            }

            if (selectedPreset.values[i] == '-1') {
                continue
            }
            if (selectedPreset.values[i] != undefined) {
                if (this.fordestination) {
                    window.api_link.send(['scv', sc, fix, "__dest__." + i, selectedPreset.values[i]]);
                }
                else {
                    window.api_link.send(['scv', sc, fix, i, selectedPreset.values[i]]);
                }
            }
        }
        if (!this.fordestination) {
            window.api_link.send(['scv', sc, fix, '__preset__', preset]);
        }
    },
}

module.exports = {
    template: '#template',

    props: ['presets', 'fixture', 'fordestination', 'fixtureclasses', 'fixturetype', 'currentcueid', 'currentvals', 'getpresetimage', "no_edit"],
    data: function () {
        return (data)
    },
    methods: {
        dictView: dictView,
        checkPresetUsablility(preset) {
            if (!preset.toLocaleLowerCase().includes(this.presetFilter.toLocaleLowerCase())) {
                return false
            }
            if (!preset.includes('@')) {
                return true
            }
            if (preset.endsWith(this.fixture)) {
                return true
            }

            if (this.fixturetype) {
                if (preset.endsWith("@" + this.fixturetype)) {
                    return true
                }
            }


            let clsdata = this.fixtureclasses[this.fixturetype]

            if (!clsdata) {

                return false
            }

            if (clsdata) {
                if (clsdata.color_profile) {
                    if (preset.includes("@") && clsdata.color_profile.startsWith(preset.split("@")[1])) {
                        return true
                    }
                }
            }

            return false
        }
    }
}
</script>
