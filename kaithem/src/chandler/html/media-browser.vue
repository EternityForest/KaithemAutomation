<style scoped></style>

<!-- This file gives you  browser for active chandler media folders.
It takes a set of action button slots that get passed "filename"
-->
<template id="media-browser">
    <div class="card w-full flex-col gaps">
        <header>
            <h3>Media browser</h3>
        </header>
        <div class="tool-bar">
            <input :disabled="no_edit" v-model="soundsearch" v-on:change="soundsearchresults = []"
                v-on:keyup.enter="doSoundSearch(soundsearch)" placeholder="Filter Sounds" style="width:60%;">
            <button type="button" v-on:click="doSoundSearch(soundsearch)">Search</button>
            <button type="button" v-on:click="soundsearch = ''">Clear Search</button>
        </div>
        <div class="scroll h-24rem w-full padding">

            <div v-if="soundsearch.length > 0" class="w-full">
                <table border="1" class="w-full">
                    <tr>
                        <th>File</th>
                        <th>Action</th>
                    </tr>
                    <tr v-for="i in soundsearchresults">
                        <td v-bind:title="'Found in' + i[0]">{{ i[1] }}</td>
                        <td>
                            <slot :filename="soundfilesdir + i[1]" :relfilename="i[1]">
                            </slot>
                        </td>
                    </tr>
                </table>
            </div>

            <div v-if="soundsearch == ''">
                <h4>
                    <a title="View in file manager" v-bind:href="'/settings/files' + encodeURI(soundfilesdir)"
                        target="_blank">{{ soundfilesdir }}</a>
                </h4>

                <ul class="w-full">
                    <li v-on:click="setSoundfileDir('')"><a>&ltTOP DIRECTORY&gt</a></li>
                    <li v-on:click="setSoundfileDir(soundfilesdir)">
                        <a><i class="mdi mdi-refresh"></i>Refresh</a>
                    </li>
                    <li v-if="soundfilesdir"
                        v-on:click="setSoundfileDir(((soundfilesdir.match(/(.*)[\/\\]/)[1] || '').match(/(.*)[\/\\]/)[1] || '') + '/')">
                        <a>..</a>
                    </li>
                    <li v-on:click="setSoundfileDir(i[0])" v-for="i in soundfileslisting[0]">
                        <a>{{i[0] }}</a>
                        <slot v-if="selectfolders" :filename="i[0]" :relfilename="i[0].split('/').pop()">
                        </slot>
                    </li>
                </ul>

                <table border="1" class="w-full">
                    <thead>
                        <tr>
                            <th style="width: 40%;">File</th>
                            <th>Action</th>

                        </tr>
                    </thead>
                    <tr v-for="i of soundfileslisting[1]">
                        <td class="w-12rem">{{ i[0] }}</td>
                        <td>
                            <slot :filename="soundfilesdir + i[0]" :relfilename="i[1]">
                            </slot>
                        </td>
                    </tr>
                </table>
            </div>
        </div>
    </div>
</template>


<script>
var filebrowserdata = {
    'soundsearch': '',
    //The selected dir and [[folders][files]] in that dir, for the
    //sound file browser
    'soundfilesdir': '',
    'soundfileslisting': [
        [],
        []
    ],

    'soundsearchresults': [],


    'doSoundSearch': function (s) {
        window.api_link.send(["searchsounds", s])
    },
    'setSoundfileDir': function (i) {

        if (!((i == '') | (i[0] == '/'))) {
            this.soundfilesdir += i;
        }
        else {
            this.soundfilesdir = i;
        }
        this.soundfileslisting = [
            [],
            []
        ]
        window.api_link.send(['listsoundfolder', i])
    },
}

module.exports = {
    template: '#mediabrowser',
    //I is a data object having u,ch, and v, the universe channel and value.
    //Chinfo is the channel info list from the fixtues that you get with channelInfoForUniverseChannel
    props: ['no_edit', 'select_folder'],
    data: function () {
        function onsoundfolderlisting(e) {
            const v = e.data
            if (v[0] == this.$data.soundfilesdir) {
                this.$data.soundfileslisting = v[1]
            }
        }
        this.listener1 = onsoundfolderlisting.bind(this)

        window.addEventListener('onsoundfolderlisting', this.listener1)
        function onsoundsearchresults(e) {
            const v = e.data
            console.log(v)
            if (this.$data.soundsearch == v[0]) {
                this.$data.soundsearchresults = v[1]
            }

        }
        this.listener2 = onsoundsearchresults.bind(this)

        window.addEventListener('onsoundsearchresults', this.listener2)

        return (filebrowserdata)
    },

    destroyed: function () {
        window.removeEventListener('onsoundfolderlisting', this.listener1)
        window.removeEventListener('onsoundsearchresults', this.listener2)
    }
}

</script>