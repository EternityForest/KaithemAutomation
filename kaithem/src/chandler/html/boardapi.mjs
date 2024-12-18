/* This rather hacky file expects this to become the app data for a vue instance


 It's slowly being refactored after getting very out of hand.

It provides window.api_link

 It provides appData, appComputed, and appMethods to add to your vue instance.

 It also provides some globals:

 dictView, formatInterval

 Things are done oddly because:

 1. It was not originally planned to be this feature rich
 2. It started with Vue2


*/

import { useBlankDescriptions, formatInterval, dictView } from "./utils.mjs?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0";
import { kaithemapi, APIWidget } from "/static/js/widget.mjs"


let keysdown = {}

let appData = {}

let keyHandle = function (e) {
    if (keysdown[e.key] != undefined) {
        if (keysdown[e.key]) {
            return;
        }

    }
    keysdown[e.key] = true;
    e.preventRepeat();
    api_link.send(['event', "keydown." + e.key, 1, 'int', "__global__"])
}
let keyUpHandle = function (e) {
    if (keysdown[e.key] != undefined) {
        if (!keysdown[e.key]) {
            return;
        }

    }
    keysdown[e.key] = false;
    api_link.send(['event', "keyup." + e.key, 1, 'int', "__global__"])
}
let rebindKeys = function (data) {
    keyboardJS.reset()
    keyboardJS.bind(keyHandle)
    keyboardJS.bind(null, keyUpHandle)

}

function playAlert(m) {
    if (appData.uiAlertSounds.value) {
        var mp3_url = '/static/sounds/72127__kizilsungur__sweetalertsound3.opus';
        (new Audio(mp3_url)).play().catch(() => { })
    }
    if (m) {
        KaithemWidgetApiSnackbar(m, 60)
    }
}

function errorTone(m) {
    if (appData.uiAlertSounds.value) {
        var mp3_url = '/static/sounds/423166__plasterbrain__minimalist-sci-fi-ui-error.opus';
        (new Audio(mp3_url)).play().catch(() => { })
    }
    if (m) {
        KaithemWidgetApiSnackbar(m, 60)
    }
}
// Legacy compatibility equivalents for the old vue2 apis. TODO get rid of this
function old_vue_set(o, k, v) {
    o[k] = v
}

function old_vue_delete(o, k) {
    delete o[k]
}

function set(o, k, v) {

    if (o[k] == undefined) {
        old_vue_set(o, k, v)
    }
    for (var key in v) {
        // If values of same property are not equal,
        // objects are not equivalent
        if (o[k][key] !== v[key]) {
            old_vue_set(o[k], key, v[key])
        }
    }

    // If we made it this far, objects
    // are considered equivalent
    return true;
}



async function initializeState (board) {

    var v = await fetch("/chandler/api/all-cues/" + board, {
        method: "GET",
    })

    v = await v.json()

    for (var i in v) {
        handleCueInfo(i, v[i])
    }
}

let cueSetData = {}

let appMethods = {
    // Slowly we want to migrate to these two generic setters
    'setGroupProperty': async function (group, property, value) {

        // Serialization prevents tests from acting badly and might even be important
        // in the ui on slow connections
        if (appData.previousSerializedPromise.value) {
            await appData.previousSerializedPromise.value
        }

        var x = cueSetData[group + property]
        if (x) {
            clearTimeout(x);
            delete cueSetData[group + property]
        }
        var b = {}
        b[property] = value

        appData.previousSerializedPromise.value = fetch("/chandler/api/set-group-properties/" + group, {
            method: "PUT",
            body: JSON.stringify(b),
            headers: {
                "Content-type": "application/json; charset=UTF-8"
            }
        }).catch(
            function (e) {
                alert("Error setting property.")
            }
        );
        await appData.previousSerializedPromise.value
    },

    'setCueProperty': async function (cue, property, value) {

        if (appData.previousSerializedPromise.value) {
            await appData.previousSerializedPromise.value
        }

        var x = cueSetData[cue + property]
        if (x) {
            clearTimeout(x);
            delete cueSetData[cue + property]
        }

        var b = {}
        b[property] = value

        appData.previousSerializedPromise.value = fetch("/chandler/api/set-cue-properties/" + cue, {
            method: "PUT",
            body: JSON.stringify(b),
            headers: {
                "Content-type": "application/json; charset=UTF-8"
            }
        }).catch(
            function (e) {
                alert("Error setting property.")
            }
        );
        await appData.previousSerializedPromise.value
    },

    'setCuePropertyDeferred': function (cue, property, value) {
        //Set the property in 5 seconds, unless we get another command to set
        //it to something else.  Used for cue text and stuff that shouldn;t update live
        // so it doesn't refresh a millon times
        var x = cueSetData[cue + property]
        if (x) {
            clearTimeout(x);
        }

        cueSetData[cue + property] = setTimeout(function () {
            var b = {}
            b[property] = value

            fetch("/chandler/api/set-cue-properties/" + cue, {
                method: "PUT",
                body: JSON.stringify(b),
                headers: {
                    "Content-type": "application/json; charset=UTF-8"
                }
            }).catch(
                function (e) {
                    alert("Error setting property.")
                }
            ); delete cueSetData[cue + property]
        }, 3000)

    },

    'setGroupPropertyDeferred': function (group, property, value) {
        //Set the property in 5 seconds, unless we get another command to set
        //it to something else
        var x = cueSetData[group + property]
        if (x) {
            clearTimeout(x);
        }

        cueSetData[group + property] = setTimeout(function () {
            var b = {}
            b[property] = value

            fetch("/chandler/api/set-group-properties/" + group, {
                method: "PUT",
                body: JSON.stringify(b),
                headers: {
                    "Content-type": "application/json; charset=UTF-8"
                }
            }).catch(
                function (e) {
                    alert("Error setting property.")
                }
            ); delete cueSetData[group + property]
        }, 3000)

    },


    'saveToDisk': function () {
        api_link.send(['saveState'])
    },

    'sendev': function (where) {
        api_link.send(['event', this.evtosend, this.evval, this.evtypetosend, where])
    },

    'groupev': function (evt, where) {
        if (confirm_for_group(where)) {
            api_link.send(['event', evt, '', 'str', where])
        }
    },

    'refreshhistory': function (sc) {
        api_link.send(['getcuehistory', sc]);
    },
    'setCueVal': function (sc, u, ch, val) {
        if (this.cuevals[sc]) {
            if (this.cuevals[sc][u]) {
                if (this.cuevals[sc][u]['__preset__']) {
                    api_link.send(['scv', sc, u, "__preset__", null]);
                }
            }
        }
        val = isNaN(parseFloat(val)) ? val : parseFloat(val)
        api_link.send(['scv', sc, u, ch, val]);
    },



    'selectcue': function (sc, cue) {
        if (this.cueSelectTimeout) {
            clearTimeout(this.cueSelectTimeout)
        }
        this.selectedCues[sc] = cue
        this.getcuedata(this.groupcues[sc][cue])
    },


    'selectgroup': function (sc, sn) {
        this.getcuedata(this.groupcues[sn][this.selectedCues[
            sc] || 'default'])
        if (this.cuePage[sn] == undefined) {
            this.cuePage[sn] = 0
        }
        this.editingGroup = sc;
        this.groupname = sn;
        this.recomputeformattedCues();
    },
    'delgroup': function (sc) {
        var r = confirm("Really delete group?");
        if (r == true) {
            api_link.send(['del', sc]);
        }
    },

    'go': function (sc) {

        api_link.send(['go', sc]);
    },

    'goByName': function (sn) {

        api_link.send(['gobyname', sn]);
    },

    'stopByName': function (sn) {

        api_link.send(['stopbyname', sn]);
    },

    'shortcut': function (sc) {
        api_link.send(['shortcut', this.sc_code]);
        this.sc_code = ''

    },

    'stop': function (sc, sn) {
        var x = confirm(
            "Really stop group? The cue and all variables will be reset."
        )

        if (x) {
            api_link.send(['stop', sc]);
        }
    },


    'setalpha': function (sc, v) {
        api_link.send(['setalpha', sc, v]);
        this.alphas[sc] = v
    },

    'setfade': function (sc, v) {

        api_link.send(['setfade', sc, v]);
    },


    'nextcue': function (sc) {
        if (confirm_for_group(sc)) {
            api_link.send(['nextcue', sc]);
        }
    },

    'prevcue': function (sc) {
        if (confirm_for_group(sc)) {
            api_link.send(['prevcue', sc]);
        }
    },

    'add_cue': function (sc, v,after_cue) {
        api_link.send(['add_cue', sc, v, parseFloat(after_cue.number)*1000]);
        //There's a difference between "not there" undefined and actually set to undefined....
        if (this.groupcues[sc][v] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            old_vue_set(this.groupcues[sc], v, undefined);
            this.recomputeformattedCues();
        };
        const t = this
        if (this.cueSelectTimeout) {
            clearTimeout(this.cueSelectTimeout)
        }
        this.cueSelectTimeout = setTimeout(function () {
            old_vue_set(t.selectedCues,
                sc, v)
        }, 350)
    },

    'clonecue': function (sc, cue, v) {
        api_link.send(['clonecue', cue, v]);
        //There's a difference between "not there" undefined and actually set to undefined....
        if (this.groupcues[sc][v] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            old_vue_set(this.groupcues[sc], v, undefined);
            this.recomputeformattedCues();
        };
        const t = this
        if (this.cueSelectTimeout) {
            clearTimeout(this.cueSelectTimeout)
        }
        this.cueSelectTimeout = setTimeout(function () {
            old_vue_set(t.selectedCues,
                sc, v)
        }, 350)

    },
    'gotonext': function (currentcueid, group) {
        if (!confirm_for_groups(group)) {
            return
        }
        nextcue = this.cuemeta[currentcueid].next

        cue = nextcue || (this.cuemeta[currentcueid].defaultnext)
        if (!cue) {
            return
        }
        api_link.send(['add_cue', this.groupname, nextcue]);
        api_link.send(['getcuedata', cue]);

        //There's a difference between "not there" undefined and actually set to undefined....
        if (this.groupcues[cue] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            set(this.groupcues[this.groupname], cue,
                undefined);
        }
        setTimeout(function () {
            old_vue_set(this.selectedCues,
                this.groupname, cue)
        },
            30)
    },
    'rmcue': function (cue) {
        if (!confirm("Delete cue?")) {
            return;
        }
        this.selectedCues[this.groupname] = 'default'
        api_link.send(['rmcue', cue]);
    },

    'uploadFileFromElement': function (e, type) {
        // Type says what to do with it
        let t = document.getElementById(e)

        async function readText(target) {
            const file = target.files.item(0)
            const text = await file.text();

            api_link.send(['fileUpload', text, type]);
        }

        readText(t)
    },
    'downloadSetup': function () {
        appData.downloadReqId.value = Math.random().toString();
        api_link.send(['downloadSetup', appData.downloadReqId.value]);
    },
    'jumptocue': function (cue, group) {
        if (confirm_for_group(group)) {
            api_link.send(['jumptocue', cue]);
        }
    },
    'getcuedata': function (c) {

        api_link.send(['getcuedata', c]);
    },
    'getcuemeta': function (c) {

        api_link.send(['getcuemeta', c]);
    },
    'setnext': function (sc, cue, v) {
        api_link.send(['setnext', sc, cue, v]);
    },

    'setprobability': function (sc, cue, v) {
        api_link.send(['setprobability', sc, cue, v]);
    },

    'promptsetnumber': function (cue) {
        api_link.send(['setnumber', cue, Number(prompt(
            "Enter new number for this cue:"))]);
    },

    'setnumber': function (cue, v) {
        api_link.send(['setnumber', cue, v]);
    },

    //Only for things of the form command/property, object/operand, argument/value
    'apiCommand': function (sc, p, v) {

        api_link.send([p, sc, v]);
    },

    'closePreview': function (s) {
        document.getElementById("soundpreviewdialog").close();
        document.getElementById("soundpreview").pause()
    },

    'setrandomize': function (sc, v) {

        api_link.send(['setrandomize', sc, v]);
    },

    'setcrossfade': function (sc, v) {

        this.groupmeta[sc].crossfade = v;
        api_link.send(['setcrossfade', sc, v]);
    },
    'setmqtt': function (sc, v) {

        this.groupmeta[sc].mqttServer = v;
        api_link.send(['setMqttServer', sc, v]);
    },

    "setmqttfeature": function (sc, feature, v) {
        api_link.send(['setmqttfeature', sc, feature, v]);
    },

    'setvisualization': function (sc, v) {

        this.groupmeta[sc].musicVisualizations = v;
        api_link.send(['setMusicVisualizations', sc, v]);
    },

    'setcommandtag': function (sc, v) {

        this.groupmeta[sc].commandTag = v;
        api_link.send(['setgroupcommandtag', sc, v]);
    },

    'setinfodisplay': function (sc, v) {

        this.groupmeta[sc].infoDisplay = v;
        api_link.send(['setinfodisplay', sc, v]);
    },
    'setbpm': function (sc, v) {
        api_link.send(['setbpm', sc, v]);
    },
    'tap': function (sc) {
        api_link.send(['tap', sc, api_link.now() / 1000]);
    },
    'testSoundCard': function (sc, c) {
        api_link.send(['testSoundCard', sc, c]);
    },


    'addGroup': function () {
        api_link.send(['addgroup', this.newgroupname]);
    },

    'addMonitorGroup': function () {
        api_link.send(['addmonitor', this.newgroupname]);
    },


    'addRangeEffect': function (fix) {
        this.addThisFixToCurrentCue(fix,
            prompt("Bulb # offset(2 represents the first identical fixture after this one, etc)", 1),
            prompt("Range effect length(# of identical fixtures to cover with pattern)"),
            prompt("Channel spacing between first channel of successive fixtures(If fix #1 is on DMX1 and fix #2 is on 11, spacing is 10). 0 if spacing equals fixture channel count."))
    },

    'addThisFixToCurrentCue': function (fix, idx, len, spacing) {
        //Idx and len are for adding range patters to an array of identical fixtures.
        //Otherwise they should be one
        idx = parseInt(idx)

        if (idx != 1) {
            fix = fix + "[" + idx + "]"

        }

        api_link.send(['add_cuef', this.groupcues[
            this.groupname]
        [this.selectedCues[this.groupname]],
            fix, idx, len, spacing
        ]);

    },
    'rmFixCue': function (cue, fix) {
        api_link.send(['rmcuef', cue, fix]);

    },

    'addValToCue': function () {
        if (!this.newcueu) {
            return
        }
        api_link.send(['add_cueval', this.groupcues[
            this.groupname]
        [this.selectedCues[this.groupname]],
            this.newcueu, this.newcuevnumber
        ]);
        if (parseInt(this.newcuevnumber) != NaN) {
            this.newcuevnumber = (parseInt(this.newcuevnumber) + 1).toString()
        }

    },

    'addTagToCue': function () {
        if (!this.newcuetag) {
            return
        }
        api_link.send(['add_cueval', this.groupcues[
            this.groupname]
        [this.selectedCues[this.groupname]],
            this.newcuetag, "value"
        ]);

    },
    'editMode': function () {
        keyboardJS.reset();
        this.keybindmode = "edit";
    },
    'runMode': function () {
        rebindKeys();
        this.keybindmode = "run";
    },
    'refreshPorts': function () {
        api_link.send(['getserports'])
    },
    'pushSettings': function () {
        api_link.send(['setconfuniverses', this.configuredUniverses])
    },

    'newCueFromSlide': function (sc, i) {

        api_link.send(['newFromSlide', sc, i])
    },

    'newCueFromSound': function (sc, i) {

        api_link.send(['newFromSound', sc, i])
    },


    'setEventButtons': function (sc, i) {

        api_link.send(['seteventbuttons', sc, i])
    },
    'setTagInputValue': function (sc, tag, v) {

        api_link.send(['inputtagvalue', sc, tag, v])
    }
}

let appComputed = {
    "currentcue": function () {
        if (this.selectedCues[this.groupname] == undefined) {
            return null
        }
        return (this.cuemeta[this.groupcues[this.groupname]
        [this.selectedCues[this.groupname]]
        ])
    },
    "currentcueid": function () {
        if (this.selectedCues[this.groupname] == undefined) {
            return null
        }
        return (this.groupcues[this.groupname][this
            .selectedCues[
            this.groupname]
        ])
    },

    'formatCues': function () {
        var z = {}
        var filt = true
        //list cue objects
        for (var i in this.groupcues[this.groupname]) {
            var m = this.cuemeta[this.groupcues[this.groupname]
            [i]]
            if (m !== undefined) {
                if ((!filt) | i.includes(this.cuefilter)) {
                    z[i] = m
                }
            }
        }
        if (!filt) {
            this.formattedCues = this.dictView(z, ['number'], undefined, this.cuePage[this.groupname]).filter((item) => item[1].id)
            return this.formattedCues
        }
        else {
            return this.dictView(z, ['number'], undefined, this.cuePage[this.groupname]).filter((item) => item[1].id)
        }
    },

    'formatAllGroups': function () {
        /*Sorted list of group objects*/
        var flt = this.groupfilter
        var x = this.dictView(this.groupmeta, [
            '!priority', '!started', 'name'
        ]).filter(
            function (x) {
                return (x[1].name && x[1].name.includes(
                    flt))
            });
        return x

    },

    'formatGroups': function () {
        var flt = this.groupfilter

        return this.dictView(this.groupmeta, [
            '!priority', '!started', 'name'
        ]).filter(
            function (x) {
                return (x[1].name && x[1].name.includes(
                    flt) && (!(x[1].hide)))
            });

    },



}
window.boardname = window.location.pathname.split('/')[3];

let appDataDefaults = {
    //https://stackoverflow.com/questions/6312993/javascript-seconds-to-time-string-with-format-hhmmss
    'boardname': window.location.pathname.split('/')[3],
    'formatInterval': formatInterval,
    'clock': 'time_should_be_here',
    'console': console,
    'sc_code': "",
    'unixtime': 0,
    'serports': [],
    'shortcuts': [],
    //Index by name
    'fixtureAssignments': {},
    'newfixname': '',
    'newfixtype': '',
    'newfixaddr': '',
    'newfixuniverse': '',
    //Fixture error info str
    'ferrs': '',
    'evfilt': '',
    'newcueu': '',
    'newcuetag': '',
    'newcuevnumber': '',
    'newgroupname': '',
    //For each group what page are we on
    'cuePage': {},
    'nuisianceRateLimit': [10, Date.now()],

    'previousSerializedPromise': null,

    'no_edit': !kaithemapi.checkPermission("system_admin"),

    'evlog': [
    ],
    'soundCards': {},

    //What universe if any to show the full settings page for
    'universeFullSettings': false,

    'fixtureassg': '',
    'showevents': false,

    'availableTags': {},
    "midiInputs": [],
    "blendModes": [],

    'soundfolders': [],
    'showimportexport': false,
    'evtosend': '',
    'evtypetosend': 'float',
    'evval': '',
    'savedThisSession': false,
    'grouptab': 'cue',
    'showPresets': false,
    'configuredUniverses':
    {
        'blah': { 'type': 'enttec', 'interface': 'xyz' }
    },
    'fixtureClasses': {},

    //Filter which groups are shown in the list
    'groupfilter': '',
    'cuefilter': '',
    'currentBindingBank': 'default',
    'localStorage': localStorage,
    'keybindmode': 'edit',
    'showAddChannels': false,
    //Keep track of what timers are running in a group
    'grouptimers': {},
    //Formatted for display
    'cuevals': {},
    'useBlankDescriptions': useBlankDescriptions,
    "slideshow_telemetry": {},
    'showslideshowtelemetry': false,
    'formatCueVals': function (c) {
        //Return a simplified version of the data in cuevals
        //Meant for direct display
        let op = {}
        for (var i in c) {
            op[i] = {}
            for (var j in c[i]) {
                op[i][j] = c[i][j].v
            }
        }
        return op
    },

    'del': function (a, b) {
        old_vue_delete(a, b)
    },

    'doRateLimit': function () {
        this.nuisianceRateLimit[0] += (Date.now() - this.nuisianceRateLimit[1]) / 180000
        this.nuisianceRateLimit[0] = Math.min(12, this.nuisianceRateLimit[0])
        if (this.nuisianceRateLimit[0] > 0) {
            this.nuisianceRateLimit[0] -= 1
            return true;
        }
    },

    'lookupFixtureType': function (f) {
        for (var i in this.fixtureAssignments) {
            if (("@" + this.fixtureAssignments[i].name) == f) {
                return this.fixtureAssignments[i].type;
            }
        }
        return '';
    },


    'lookupFixtureColorProfile': function (f) {
        // If fixture has no color profile, the profile is just the type
        let x = ''
        for (var i in this.fixtureAssignments) {
            if (("@" + this.fixtureAssignments[i].name) == f) {
                x = this.fixtureAssignments[i].type;
                break;
            }
        }
        if (x.length > 0) {
            let c = this.fixtureClasses[x]
            if (c) {
                if (c.color_profile && c.color_profile.length > 0) {
                    return c.color_profile
                }
            }
        }
        return x;
    },
    'getfixtureassg': function () {
        api_link.send(['getfixtureassg'])
    },

    'getChannelCompletions': function (u) {
        var x = this.configuredUniverses[u];
        if (x) {
            return useBlankDescriptions(x.channelConfig);
        }
    },

    'dictView': dictView,




    'toggleTransparent': function (cue, u, c, v) {
        if (v != null) {
            this.setCueVal(cue, u, c, null)
        }
        else {
            this.setCueVal(cue, u, c, null)
        }
    },
    'promptRename'(s) {
        var x = prompt(
            "Enter new name for group(May break existing references to group)"
        )

        if (x != null) {

            api_link.send(['setgroupname', s, x])
        }
    },

    'promptRenameCue'(sc, s) {
        var x = prompt(
            "Enter new name for cue(May break existing references to cue)"
        )

        if (x != null) {

            api_link.send(['rename_cue', sc, s, x])
        }
    },
    'deleteUniverse': function (u) {
        console.log(u)
        old_vue_delete(this.configuredUniverses, u)
    },


    'fuzzyIncludes'(s, search) {
        for (var i of search.toLowerCase().split(" ")) {
            if (!s.toLowerCase().includes(i)) {
                return 0;
            }
        }
        return 1;
    },

    //Current per group alpha channel
    'alphas': {},
    'groupmeta': {},
    'groupname': null,
    'editingGroup': null,
    'universes': {},
    'cues': {},
    'newcuename': '',
    'cuemeta': {},
    'availableCommands': {},
    // per scene user selected for editing
    'selectedCues': {},
    'showPages': false,
    'uiAlertSounds': true,
    // Used for things that auto select cues after a delay to set things
    // up but also are cancelable.
    'cueSelectTimeout': 0,
    //go from cue name to cue id
    //groupcues[groupuuid][cuename]=cueid
    'groupcues': {},
    'formattedCues': [],
    //Indexed by universe then channel number
    'channelInfoByUniverseAndNumber': {},
    //same info as groupvals, indexed hierarchally, as [universe][channel]
    //Actual objs are shared too so changing one obj change in in the other.

    'presets': {},
    //All alarms active on server
    'sys_alerts': {},



    'deletePreset': function (p) {
        if (confirm("Really Delete")) {
            delete this.presets[p];
            api_link.send(['preset', p, null]);

        }
    },


    'addTimeToGroup': function (group) {
        var t = prompt("Add minutes?")
        if (t) {
            api_link.send(["addTimeToGroup", group, t])
        }
    },

    'renamePreset': function (p) {
        var n = prompt("Preset Name?")

        if (n && n.length) {
            var b = this.presets[p]
            if (b) {
                delete this.presets[p];
                api_link.send(['preset', p, null]);

                this.presets[n] = b;
                api_link.send(['preset', n, b]);
            }
        }
    },

    'copyPreset': function (p) {
        var n = prompt("Copy to name?")

        if (n && n.length) {
            var b = this.presets[p]
            if (b) {
                this.presets[n] = JSON.parse(JSON.stringify(b));
                api_link.send(['preset', n, b]);
            }
        }
    },

    'savePreset': function (v, suggestedname) {
        /*Prompt saving data from the cuevals dict as a preset*/

        var n = prompt("Preset Name?", suggestedname || "")
        console.log("Saving preset", n, v)

        var v2 = this.presets[n] || {}
        v2.values = {}

        // Just the vals
        for (var i in v) {
            if (i == "__length__") { continue }
            if (i == "__spacing__") { continue }
            if (i == "__preset__") { continue }

            v2.values[i] = v[i].v
        }


        if (n && n.length) {
            this.presets[n] = v2;
            api_link.send(['preset', n, v2]);

        }
    },

    'debugCueLen': async function (cuelenstr, force) {
        if (!force) {
            if (!isNaN(parseFloat(cuelenstr))) {
                return
            }
        }

        let x = fetch("/chandler/api/eval-cue-length?rule=" + cuelenstr, {
            method: "GET"
        })

        x = await x
        alert("Cue len: " + cuelenstr + ". If cue started now, it would end at " + await x.text())
    },
    'getPresetImage': function (preset) {
        // Can use generic preset image if specific not available
        if (this.presets[preset]?.label_image) {
            return (this.presets[preset]?.label_image)
        }

        if (this.presets[preset.split('@')[0]]?.label_image) {
            return (this.presets[preset.split('@')[0]]?.label_image)
        }
        return "1x1.png"
    },


    'updatePreset': function (i, v) {
        /*Update given a name and the modified data as would be found in the presets file*/
        this.presets[i] = v;
        api_link.send(['preset', i, v]);
    },
    'recomputeformattedCues': function () {

    },
    'channelInfoForUniverseChannel': function (u, c) {
        if (this.channelInfoByUniverseAndNumber[u] == undefined) {
            return undefined
        }
        if (this.channelInfoByUniverseAndNumber[u][c] == undefined) {
            return undefined
        }

        return this.channelInfoByUniverseAndNumber[u][c][1]
    },

    'prompt': prompt,
}

for (var i in appDataDefaults) {
    appData[i] = Vue.ref(appDataDefaults[i])
}

function handleCueInfo(id, cue) {
    //Make an empty list of cues if it's not there yet
    if (appData.groupcues.value[cue.group] == undefined) {
        old_vue_set(appData.groupcues.value, cue.group, {});
    };
    old_vue_set(appData.groupcues.value[cue.group], cue.name, id);


    //Make an empty list of cues as a placeholder till the real data arrives
    if (appData.cuemeta.value[id] == undefined) {
        old_vue_set(appData.cuemeta.value, id, {});
    };
    set(appData.cuemeta.value, id, cue);
}



function f(v) {
    let c = v[0]


    if (c == 'soundfolders') {
        appData.soundfolders.value = v[1]
    }
    else if (c == 'ui_alert') {
        playAlert(v[1])
    }

    else if (c == 'slideshow_telemetry') {
        if (v[2] == null) {
            delete appData.slideshow_telemetry.value[v[1]]
        }
        else {
            if (v[2].status != (appData.slideshow_telemetry.value[v[1]] || {}).status) {
                if (v[2].status.includes("FAILED")) {
                    if (appData.doRateLimit.value()) {
                        errorTone('A slideshow display may need attention');
                        appData.showslideshowtelemetry.value = true;
                    }
                }
            }

            appData.slideshow_telemetry.value[v[1]] = v[2]
        }
    }

    else if (c == 'grouptimers') {
        if (appData.groupmeta.value[v[1]]) {
            appData.groupmeta.value[v[1]].timers = v[2]
        }
    }
    else if (c == 'cuehistory') {
        appData.groupmeta.value[v[1]].history = v[2]
    }
    else if (c == "groupmeta") {
        if (v[2].cue) {
            if (appData.cuemeta.value[v[2].cue] == undefined) {
                appMethods.getcuemeta(v[2].cue)
            }
        }

        if (v[2].alpha != undefined) {
            old_vue_set(appData.alphas.value, v[1], v[2].alpha);
        }

        //Just update existing data if we can
        if (appData.groupmeta.value[v[1]]) {
            set(appData.groupmeta.value, v[1], v[2])
        }
        else {
            var meta = v[2];
            set(appData.groupmeta.value, v[1], meta);
        }

        if (appData.selectedCues.value[v[1]] == undefined) {
            old_vue_set(appData.selectedCues.value, v[1], 'default')
        }
        //Make an empty list of cues as a placeholder till the real data arrives
        if (appData.groupcues.value[v[1]] == undefined) {
            old_vue_set(appData.groupcues.value, v[1], {});
        };
    }

    else if (c == "cuemeta") {
        handleCueInfo(v[1], v[2]);
        appData.recomputeformattedCues.value();
    }

    else if (c == "event") {

        appData.evlog.value.unshift(v[1])
        if (appData.evlog.value.length > 250) {
            appData.evlog.value = appData.evlog.value.slice(0, 250)
        }

        if (v[1][0].includes("error")) {
            appData.showevents.value = true;
            errorTone('');
        }
    }
    else if (c == "serports") {
        appData.serports.value = v[1]
    }

    else if (c == 'alerts') {
        if (JSON.stringify(appData.sys_alerts.value) != JSON.stringify(v[1])) {
            if (v[1]) {
                errorTone()
            }
        }

        appData.sys_alerts.value = v[1]
    }
    else if (c == 'confuniverses') {
        appData.configuredUniverses.value = v[1]
    }
    else if (c == 'universe_status') {
        appData.universes.value[v[1]].status = v[2]
        appData.universes.value[v[1]].ok = v[3]
        appData.universes.value[v[1]].telemetry = v[4]
    }

    else if (c == "varchange") {
        if (appData.groupmeta.value[v[1]]) {
            appData.groupmeta.value[v[1]]['vars'][v[2]] = v[3]
        }
    }
    else if (c == "delcue") {
        c = appData.cuemeta.value[v[1]]
        old_vue_delete(appData.cuemeta.value, v[1]);
        old_vue_delete(appData.cuevals.value, v[1]);
        old_vue_delete(appData.groupcues.value[c.group], c.name);
        appData.recomputeformattedCues.value();
    }

    else if (c == "cnames") {
        old_vue_set(appData.channelInfoByUniverseAndNumber.value, v[1], v[2])
    }
    else if (c == "universes") {
        appData.universes.value = v[1]
    }
    else if (c == "soundoutputs") {
        appData.soundCards.value = v[1]
    }

    else if (c == 'soundsearchresults') {
        const event = new Event("onsoundsearchresults");
        event.data = [v[1], v[2]]
        window.dispatchEvent(event)
    }
    else if (c == "cuedata") {
        let d = {}
        old_vue_set(appData.cuevals.value, v[1], d)

        for (var i in v[2]) {

            if (!(i in appData.channelInfoByUniverseAndNumber.value)) {
                api_link.send(['getcnames', i])
            }
            old_vue_set(appData.cuevals.value[v[1]], i, {})

            for (var j in v[2][i]) {
                let y = {
                    "u": i,
                    'ch': j,
                    "v": v[2][i][j]
                }
                old_vue_set(appData.cuevals.value[v[1]][i], j, y)
                //The other 2 don't need to be reactive, v does
                old_vue_set(y, 'v', v[2][i][j])

            }
        }
    }

    else if (c == "commands") {
        appData.availableCommands.value = v[1]
    }

    else if (c == "scv") {
        let x = []

        let cue = v[1]
        let universe = v[2]
        let channel = v[3]
        let value = v[4]



        //Empty universe dict, we are not set up to listen to this yet
        if (!appData.cuevals.value[cue]) {
            return
        }
        if (!appData.cuevals.value[cue][universe]) {
            appData.cuevals.value[cue][universe] = {}
        }

        var needRefresh = false;

        if (v[4] !== null) {

            let y = {
                "u": universe,
                'ch': channel,
                "v": value
            }
            old_vue_set(y, 'v', value)
            old_vue_set(appData.cuevals.value[cue][universe], channel, y)
        }
        else {
            old_vue_delete(appData.cuevals.value[cue][universe], channel)
            needRefresh = 1;
        }

        if (Object.entries(appData.cuevals.value[cue][universe]).length == 0) {
            old_vue_delete(appData.cuevals.value[cue], universe)
        }
    }


    else if (c == "go") {

        old_vue_set(appData.groupmeta.value[v[1]], 'active', true)

    }

    else if (c == "refreshPage") {
        window.reload()
    }

    else if (c == "stop") {

        old_vue_set(appData.groupmeta.value[v[1]], 'active', false)

    }
    else if (c == "ferrs") {

        appData.ferrs.value = v[1]

    }
    else if (c == "fixtureclasses") {

        appData.fixtureClasses.value = v[1]
    }
    else if (c == "fixtureclass") {
        if (v[2] == null) {
            old_vue_delete(appData.fixtureClasses.value, v[1])
        }
        else {
            old_vue_set(appData.fixtureClasses.value, v[1], v[2])
        }
    }

    else if (c == "fixtureAssignments") {

        appData.fixtureAssignments.value = v[1]
    }

    else if (c == "del") {
        old_vue_delete(appData.selectedCues.value, v[1])
        old_vue_delete(appData.groupmeta.value, v[1])
        old_vue_delete(appData.mtimes.value, v[1])
        appData.editingGroup.value = null

    }

    else if (c == 'soundfolderlisting') {
        // Handled in media-browser.vue
        const event = new Event("onsoundfolderlisting");
        event.data = [v[1], v[2]]
        window.dispatchEvent(event)
    }

    else if (c == 'fixturePresets') {
        appData.presets.value = v[1]
    }

    else if (c == 'preset') {
        appData.presets.value[v[1]] = v[2]
    }

    else if (c == 'fileDownload') {

        if (v[1] == appData.downloadReqId.value) {
            const file = new File([v[2]], v[3], {
                type: 'text/plain',
            })

            const link = document.createElement('a')
            const url = URL.createObjectURL(file)

            link.href = url
            link.download = file.name
            document.body.appendChild(link)
            link.click()

            document.body.removeChild(link)
            window.URL.revokeObjectURL(url)
        }
    }

    else if (c == 'shortcuts') {
        appData.shortcuts.value = v[1]
    }

    else if (c == 'availableTags') {
        appData.availableTags.value = v[1]

    }
    else if (c == 'midiInputs') {
        appData.midiInputs.value = v[1]
    }

    else if (c == "blendModes") {
        appData.blendModes.value = v[1]
    }
}

async function initChandlerVueModel(board, va) {
    await initializeState(board)

    api_link.upd = f
    api_link.send(['get_state']);
    api_link.send(['getCommands']);


    // Exact sync on half seconds
    function unix_time_upd() {
        appData.unixtime.value = api_link.now() / 1000
        setTimeout(unix_time_upd,
            10000 - (api_link.now() % 10000))
    }

    unix_time_upd()

    function clock_upd() {
        var c = new Date(api_link.now()).toLocaleTimeString()
        const el = document.getElementById("toolbar-clock")
        if (el) {
            el.innerHTML = c;
        }

        setTimeout(clock_upd,
            1000 - (api_link.now() % 1000))
    }

    clock_upd()

    var update_meters = function () {
        var u = api_link.now() / 1000

        for (var i of document.querySelectorAll('[data-meter-ref]')) {
            i.value = u - parseFloat(i.dataset.meterRef)
        }

        for (var i of document.querySelectorAll('[data-count-ref]')) {
            let l = parseFloat(i.dataset.countLen) * (60 / parseFloat(i.dataset.countBpm))
            let e = parseFloat(i.dataset.countRef) + l

            i.innerHTML = formatInterval(e - u)
        }

    }
    setInterval(update_meters, 200)
}

var confirm_for_group = function (sc) {
    if (appData.groupmeta.value[sc].requireConfirm) {
        if (confirm("Confirm Action for Group: " + appData.groupmeta.value[sc].name)) {
            return true
        }
    }
    else {
        return true
    }
}

var shortcut = function (sc) {
    return function () {
        api_link.send(['shortcut', sc]);

    }
}
var next = function (sc) {
    return function () {
        api_link.send(['nextcuebyname', sc]);

    }
}
var goto = function (sc, cue) {
    return function () {
        api_link.send(['jumpbyname', sc, cue]);

    }
}



var script = document.createElement('script');
script.onload = function () {
    const boardname = window.location.pathname.split('/')[3];
    initChandlerVueModel(boardname)
};

let api_link = new APIWidget("WebChandlerConsole:" + appData.boardname.value);
window.api_link = api_link

export {
    api_link,
    useBlankDescriptions,
    initChandlerVueModel,
    shortcut,
    next,
    goto,
    formatInterval,
    confirm_for_group,
    dictView,
    appComputed,
    appMethods,
    appData,
    initializeState
}