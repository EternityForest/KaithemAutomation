<style scoped></style>

<template id="telemetry">
    <div>
        <p>This table shows the slideshow displays that are active or seen
            recently.</p>
        <p>Only one display per IP/group can be shown. Battery status only
            works in Chrome</p>
        <p>Ding plays a tone to identify and test the display. You can
            assign displays friendly names to help
            identify them.</p>
        <p>Be careful with refresh! Some browsers may respond badly if the
            network is messed up.</p>

        <table>
            <tr>
                <th>
                    Connection
                </th>
                <th>
                    Name
                </th>
                <th>Status</th>
                <th>Last Seen</th>
                <th>Battery</th>
                <th>Action</th>
            </tr>
            <tr v-for="v, i of telemetry" :class="{ 'error': v.ts < (unixtime - 70) }">
                <td>{{ i }}</td>
                <td>{{ v.name }}</td>
                <td :class="{ 'error': v.status.includes('FAIL') }">
                    {{ v.ts < (unixtime - 70) ? 'LOST CONNECTION' : v.status }}
                </td>
                <td>{{ formatTime(v.ts) }}</td>
                <td :class="{ 'error': (v.battery || {}).charging == false }">
                    {{ v.battery || '' }}</td>
                <td>
                    <button type="button" @click="mediaLinkCommand(v.group, v.id, ['testAudio'])">Ding</button>
                    <button type="button" @click="promptRenameDisplay(v.group, v.id)">Rename</button>
                    <button type="button" @click="mediaLinkCommand(v.group, v.id, ['refresh'])">Refresh</button>
                </td>

            </tr>
        </table>
    </div>
</template>


<script>
module.exports = {
    template: '#telemetry',
    //I is a data object having u,ch, and v, the universe channel and value.
    //Chinfo is the channel info list from the fixtues that you get with channelInfoForUniverseChannel
    props: ['telemetry'],
    data: function () {
        return {}
    },
    methods: {
        formatTime: function (ts) {
            return new Date(ts * 1000).toLocaleString();
        }
    }
}

</script>