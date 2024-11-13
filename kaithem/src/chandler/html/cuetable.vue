<style scoped></style>

<template id="cue-table">
    <div>
        <div class="tool-bar">
            <p style="flex-grow: 300;">
                <input v-model="cuefilter" placeholder="Search Cues"  @change="page = 0" />
                <button type="button" v-on:click="cuefilter = ''"><i class="mdi mdi-backspace"></i></button>
            </p>

            <label>Page
                <input v-model="page" type="number" min="0" max="99" />
            </label>
            <button type="button" v-on:click="page -= 1" :disabled="page == 0">
                <span class="mdi mdi-page-previous"></span>
                Prev</button>
            <button type="button" v-on:click="page += 1">
                <span class="mdi mdi-page-next"></span>
                Next</button>
        </div>

        <div style="overflow-y: auto;max-height:12em;">

            <table class="reflow w-full" border="1">

                <thead>
                    <slot name="header"></slot>
                </thead>

                <tbody>
                    <template v-for="i in formatCues()">
                        <slot name="row" :i="i"></slot>
                    </template>
                </tbody>

            </table>
        </div>
    </div>
</template>


<script>
console.log('Cue Table')
var cuetabledata =
{
    'page': 0,
    'cuefilter': '',
}

module.exports = {
    template: '#cue-table',
    //I is a data object having u,ch, and v, the universe channel and value.
    //Chinfo is the channel info list from the fixtues that you get with channelInfoForUniverseChannel
    props: ['groupname', 'groupcues', 'cuemeta',],
    methods: {
        'formatCues': function () {
            var z = {}
            var filt = true
            //list cue objects
            for (var i in this.groupcues[this.groupname]) {
                var m = this.cuemeta[this.groupcues[this.groupname]
                [i]]
                if (m !== undefined) {
                    if ((!filt) | i.toLowerCase().includes(this.cuefilter.toLowerCase())) {
                        z[i] = m
                    }
                }
            }
            if (!filt) {
                this.formattedCues = this.dictView(z, ['number'], undefined, this.page).filter((item) => item[1].id)
                return this.formattedCues
            }
            else {
                return this.dictView(z, ['number'], undefined, this.page).filter((item) => item[1].id)
            }
        },
        'dictView': function (dict, sorts, filterf, page) {
            //Given a dict  and a list of sort keys sorts,
            //return a list of [key,value] pairs sorted by the sort
            //keys. Earlier sort keys take precendence.

            // the lowest precedence sort key is the actual dict key.

            //Keys starting with ! are interpreted as meanng to sort in descending order

            var o = []

            const usePages = page !== undefined
            page = page || 0
            var toSkip = page * 50

            Object.keys(dict).forEach(
                function (key, index) {
                    if (filterf == undefined || filterf(key, dict[key])) {
                        toSkip -= 1

                        if (toSkip > 0) {
                            return
                        }
                        else {
                            // overlap between pages
                            if (toSkip < -60) {
                                if (usePages) {
                                    return
                                }
                            }
                            o.push([key, dict[key]])
                        }
                    }
                })

            var l = []
            for (var i of sorts) {
                //Convert to (reverse, string) tuple where reverse is -1 if str started with an exclamation point
                //Get rid of the fist char if so
                l.push([
                    i[0] == '!' ? -1 : 1,
                    i[0] == "!" ? i.slice(1) : i
                ])
            }

            o.sort(function (a, b) {
                //For each of the possible soft keys, check if they
                //are different. If so, compare and possible reverse the ouptut

                var d = a[1]
                var d2 = b[1]
                for (var i of l) {
                    var key = i[1]
                    var rev = i[0]
                    if (!(d[key] == d2[key])) {
                        return (d[key] > d2[key] ? 1 : -1) * rev
                    }

                }
                // Fallback sort is the keys themselves
                if (a[0] != b[0]) {
                    return (a[0] > b[0]) ? 1 : -1
                }
                return 0
            });
            return (o)
        }
    },
    data: function () {
        return (cuetabledata)
    }
}

</script>