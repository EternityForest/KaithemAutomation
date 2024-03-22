${ vars }

/* This rather hacky file expects this to become the app data for a vue instance
 named vueapp, and provides the chandler API that way.

 It's slowly being refactored after getting very out of hand.

 It expects an APIWidget rendered with the name api_link

 It provides appData, appComputed, and appMethods to add to your vue instance.

 Things are done oddly because:

 1. It was not originally planned to be this feature rich
 2. It started with Vue2
 

*/

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

function useBlankDescriptions(l, additional) {
    var l2 = [];
    for (i in l) {
        l2.push([i, '']);
    }
    if (additional) {
        for (i in additional) {
            l2.push([i, additional[i]]);

        }
    }
    return l2;
}



formatInterval = function (seconds) {
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds - (hours * 3600)) /
        60);
    var seconds = seconds - (hours * 3600) - (minutes * 60);
    var tenths = Math.floor((seconds - Math.floor(seconds)) *
        10);
    seconds = Math.floor(seconds);

    var time = "";

    time = ("" + hours).padStart(2, '0') + ":" + ("" + minutes).padStart(2, '0') + ":" + ("" + seconds).padStart(2, '0')
    return time;
}


getValueRange = function (d, v) {
    //Given a channel info list structure thing and a value, return the [min,max,name] of the range
    //that the value is in
    if (d == undefined) { return ([0, 255, "Unknown"]) }
    var c = 0
    for (i of d) {
        if (c > 2) {
            if (i[1] >= v) {
                //Better to return Unknown then bad data
                if (i.length == 3) {
                    return (i)
                }
            }
        }
        c += 1
    }
    return ([0, 255, "Unknown"])
}



appMethods = {


    // Slowly we want to migrate to these two generic setters
    'setSceneProperty': function (scene, property, value) {
        api_link.send(['setSceneProperty', scene, property, value])

    },
    'setCueProperty': function (cue, property, value) {
        api_link.send(['setCueProperty', cue, property, value])

    },

    'saveToDisk': function () {
        api_link.send(['saveState'])
    },

    'saveLibrary': function () {

        api_link.send(['saveLibrary'])
    },
    'sendev': function (where) {
        api_link.send(['event', this.evtosend, this.evval, this.evtypetosend, where])
    },

    'sceneev': function (evt, where) {
        api_link.send(['event', evt, '', 'str', where])
    },

    'refreshhistory': function (sc) {
        api_link.send(['getcuehistory', sc]);
    },
    'setCueVal': function (sc, u, ch, val) {
        val = isNaN(parseFloat(val)) ? val : parseFloat(val)
        this.lockedFaders[sc + ":" + u + ":" + ch] = true;
        api_link.send(['scv', sc, u, ch, val]);
    },

    'setFixturePreset': function (sc, fix, preset) {
        for (i in this.cuevals[sc][fix]) {
            if ((!(preset[i] == undefined)) && preset[i].toString().length) {
                api_link.send(['scv', sc, fix, i, preset[i]]);
                this.cuevals[sc][fix][i].v = preset[i]
            }

        }
    },


    'setCueValNolock': function (sc, u, ch, val) {
        val = isNaN(parseFloat(val)) ? val : parseFloat(val)
        api_link.send(['scv', sc, u, ch, val]);
    },
    'unlockCueValFader': function (sc, u, ch) {
        delete this.lockedFaders[sc + ":" + u + ":" + ch];
    },

    'selectcue': function (sc, cue) {
        this.selectedCues[sc] = cue
        this.getcuedata(this.scenecues[sc][cue])
    },
    'getallcuemeta': function (sn) {
        api_link.send(['getallcuemeta', sn]);

    },
    'selectscene': function (sc, sn) {
        this.getcuedata(this.scenecues[sn][this.selectedCues[
            sc] || 'default'])
        this.editingScene = sc;
        this.scenename = sn;
        api_link.send(['gsd', sn]);
        api_link.send(['getallcuemeta', sn]);
        this.recomputeformattedCues();
    },
    'delscene': function (sc) {
        var r = confirm("Really delete scene?");
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
            "Really stop scene? The cue and all variables will be reset."
        )

        if (x) {
            api_link.send(['stop', sc]);
        }
    },


    'setalpha': function (sc, v) {
        this.lockedFaders[sc] = true;
        api_link.send(['setalpha', sc, v]);
        this.alphas[sc] = v
    },
    'unlockAlpha': function (sc) {
        delete this.lockedFaders[sc];
    },


    'setfade': function (sc, v) {

        api_link.send(['setfade', sc, v]);
    },


    'settriggershortcut': function (sc, v) {

        api_link.send(['setCueTriggerShortcut', sc, v]);
    },
    'nextcue': function (sc) {
        api_link.send(['nextcue', sc]);
    },
    'prevcue': function (sc) {
        api_link.send(['prevcue', sc]);
    },

    'add_cue': function (sc, v) {
        api_link.send(['add_cue', sc, v]);
        //There's a difference between "not there" undefined and actually set to undefined....
        if (this.scenecues[sc][v] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            old_vue_set(this.scenecues[sc], v, undefined);
            this.recomputeformattedCues();
        };
        setTimeout(function () {
            old_vue_set(this.selectedCues,
                sc, v)
        }, 70)
    },

    'clonecue': function (sc, cue, v) {
        api_link.send(['clonecue', cue, v]);
        //There's a difference between "not there" undefined and actually set to undefined....
        if (this.scenecues[sc][v] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            old_vue_set(this.scenecues[sc], v, undefined);
            this.recomputeformattedCues();
        };
        setTimeout(function () {
            old_vue_set(this.selectedCues,
                sc, v)
        }, 70)

    },
    'gotonext': function (currentcueid) {
        nextcue = this.cuemeta[currentcueid].next

        cue = nextcue || (this.cuemeta[currentcueid].defaultnext)
        if (!cue) {
            return
        }
        api_link.send(['add_cue', this.scenename, nextcue]);
        api_link.send(['getcuedata', cue]);

        //There's a difference between "not there" undefined and actually set to undefined....
        if (this.scenecues[cue] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            set(this.scenecues[this.scenename], cue,
                undefined);
        }
        setTimeout(function () {
            old_vue_set(this.selectedCues,
                this.scenename, cue)
        },
            30)
    },
    'rmcue': function (cue) {
        if (!confirm("Delete cue?")) {
            return;
        }
        this.selectedCues[this.scenename] = 'default'
        api_link.send(['rmcue', cue]);
    },
    'jumptocue': function (cue) {
        api_link.send(['jumptocue', cue]);
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

    'setfadein': function (cue, v) {
        api_link.send(['setfadein', cue, v]);
    },

    'setSoundFadeOut': function (cue, v) {
        api_link.send(['setSoundFadeOut', cue, v]);
    },

    'setSoundFadeIn': function (cue, v) {
        api_link.send(['setSoundFadeIn', cue, v]);
    },

    'setCueVolume': function (cue, v) {
        api_link.send(['setCueVolume', cue, v]);
    },
    'setCueLoops': function (cue, v) {
        api_link.send(['setCueLoops', cue, v]);
    },
    'setreentrant': function (cue, v) {
        api_link.send(['setreentrant', cue, v]);
    },
    'settrack': function (cue, v) {
        api_link.send(['settrack', cue, v]);
    },

    'setcuenotes': function (cue, v) {
        api_link.send(['setcuenotes', cue, v]);
    },

    'setrellen': function (cue, v) {
        api_link.send(['setrellen', cue, v]);
    },
    'setblend': function (sc, v) {
        api_link.send(['setblend', sc, v]);
    },
    'setblendparam': function (sc, k, v) {

        api_link.send(['setblendarg', sc, k, v]);
    },

    //Only for things of the form command/property, object/operand, argument/value
    'apiCommand': function (sc, p, v) {

        api_link.send([p, sc, v]);
    },

    'previewSound': function (s) {

        document.getElementById("soundpreviewdialog").show();
        var t = ['.mp3', '.ogg', '.wav', '.oga', '.opus', '.aac', '.flac']
        for (let i of t) {
            if (s.endsWith(i)) {
                document.getElementById("soundpreview").src = "WebMediaServer?file=" + encodeURIComponent(s);
                document.getElementById("soundpreview").currentTime = 0;
                document.getElementById("soundpreview").play();
                document.getElementById("textpreview").src = "";
                document.getElementById("textpreview").style.display = 'none'
                document.getElementById("soundpreview").style.display = 'block'
                return
            }
        }
        document.getElementById("textpreview").src = "WebMediaServer?file=" + encodeURIComponent(s);
        document.getElementById("soundpreview").src = ""
        document.getElementById("textpreview").style.display = 'block'
        document.getElementById("soundpreview").style.display = 'none'

    },

    'closePreview': function (s) {
        document.getElementById("soundpreviewdialog").close();
        document.getElementById("soundpreview").pause()
    },

    'setlength': function (sc, v) {

        api_link.send(['setlength', sc, v]);
    },
    'setrandomize': function (sc, v) {

        api_link.send(['setrandomize', sc, v]);
    },

    'setdalpha': function (sc, v) {

        this.scenemeta[sc].alpha = v;
        api_link.send(['setdalpha', sc, v]);
    },


    'setcrossfade': function (sc, v) {

        this.scenemeta[sc].crossfade = v;
        api_link.send(['setcrossfade', sc, v]);
    },
    'setmqtt': function (sc, v) {

        this.scenemeta[sc].mqttServer = v;
        api_link.send(['setMqttServer', sc, v]);
    },

    "setmqttfeature": function (sc, feature, v) {
        api_link.send(['setmqttfeature', sc, feature, v]);
    },

    'setvisualization': function (sc, v) {

        this.scenemeta[sc].musicVisualizations = v;
        api_link.send(['setMusicVisualizations', sc, v]);
    },

    'setcommandtag': function (sc, v) {

        this.scenemeta[sc].commandTag = v;
        api_link.send(['setscenecommandtag', sc, v]);
    },

    'setdefaultnext': function (sc, v) {

        this.scenemeta[sc].defaultNext = v;
        api_link.send(['setDefaultNext', sc, v]);
    },
    'setinfodisplay': function (sc, v) {

        this.scenemeta[sc].infoDisplay = v;
        api_link.send(['setinfodisplay', sc, v]);
    },
    'setutility': function (sc, v) {

        this.scenemeta[sc].utility = v;
        api_link.send(['setutility', sc, v]);
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


    'addScene': function () {
        api_link.send(['addscene', this.newscenename]);
    },

    'addMonitorScene': function () {
        api_link.send(['addmonitor', this.newscenename]);
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

        api_link.send(['add_cuef', this.scenecues[
            this.scenename]
        [this.selectedCues[this.scenename]],
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
        api_link.send(['add_cueval', this.scenecues[
            this.scenename]
        [this.selectedCues[this.scenename]],
            this.newcueu, this.newcuevnumber
        ]);
        if (parseInt(this.newcuevnumber) != NaN) {
            this.newcuevnumber = parseInt(this.newcuevnumber) + 1
        }

    },

    'editMode': function () {
        keyboardJS.reset();
        this.keybindmode = "edit";
    },
    'runMode': function () {
        rebind();
        this.keybindmode = "run";
    },
    'refreshPorts': function () {
        api_link.send(['getserports'])
    },
    'pushSettings': function () {
        api_link.send(['setconfuniverses', this.configuredUniverses])
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
        api_link.send(['listsoundfolder', i])
    },
    'setSoundOutput': function (cueid, i) {

        api_link.send(['setcuesoundoutput', cueid, i])
    },

    'setCueSoundStart': function (cueid, i) {

        api_link.send(['setcuesoundstartposition', cueid, i])
    },

    'setCueSlide': function (cueid, i) {

        api_link.send(['setcueslide', cueid, i])
    },



    'setCueMediaSpeed': function (cueid, i) {

        api_link.send(['setcuemediaspeed', cueid, i])
    },

    'setCueMediaWindup': function (cueid, i) {

        api_link.send(['setcuemediawindup', cueid, i])
    },

    'setCueMediaWinddown': function (cueid, i) {

        api_link.send(['setcuemediawinddown', cueid, i])
    },
    'setSoundfile': function (cueid, i) {

        api_link.send(['setcuesound', cueid, i])
    },
    'setSceneSoundOutput': function (cueid, i) {

        api_link.send(['setscenesoundout', cueid, i])
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

    'setHide': function (sc, i) {

        api_link.send(['sethide', sc, i])
    },

    'setTagInputValue': function (sc, tag, v) {

        api_link.send(['inputtagvalue', sc, tag, v])
    },

    'setDisplayTags': function (sc, i) {

        api_link.send(['setdisplaytags', sc, i])
    },

    'setSceneNotes': function (sc, i) {

        api_link.send(['setNotes', sc, i])
    }
}

appComputed = {
    "currentcue": function () {
        return (this.cuemeta[this.scenecues[this.scenename]
        [this.selectedCues[this.scenename]]
        ])
    },
    "currentcueid": function () {
        return (this.scenecues[this.scenename][this
            .selectedCues[
            this.scenename]
        ])
    },

    'formatCues': function () {
        z = {}
        var filt = true
        //list cue objects
        for (i in this.scenecues[this.scenename]) {
            m = this.cuemeta[this.scenecues[this.scenename]
            [i]]
            if (m !== undefined) {
                if ((!filt) | i.includes(this.cuefilter)) {
                    z[i] = m
                }
            }
        }
        if (!filt) {
            this.formattedCues = this.dictView(z, ['number']).filter((item) => item[1].id)
            return this.formattedCues
        }
        else {
            return this.dictView(z, ['number']).filter((item) => item[1].id)
        }
    },

    'formatAllScenes': function () {
        /*Sorted list of scene objects*/
        var flt = this.scenefilter
        var x = this.dictView(this.scenemeta, [
            '!priority', '!started', 'name'
        ]).filter(
            function (x) {
                return (x[1].name && x[1].name.includes(
                    flt))
            });
        return x

    },

    'formatScenes': function () {
        var flt = this.scenefilter

        return this.dictView(this.scenemeta, [
            '!priority', '!started', 'name'
        ]).filter(
            function (x) {
                return (x[1].name && x[1].name.includes(
                    flt) && (!(x[1].hide)))
            });

    },



}


//# sourceURL=appcode.js 
appData = {
    //https://stackoverflow.com/questions/6312993/javascript-seconds-to-time-string-with-format-hhmmss
    'formatInterval': formatInterval,
    'console': console,
    'sc_code': "",
    'unixtime': 0,
    'serports': [],
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
    'newcuevnumber': '',
    'newscenename': '',
    'specialvars': [
        ["_", "Output of the previous action"]
    ],

    'evlog': [
    ],
    'soundCards': KaithemSoundCards,

    //What universe if any to show the full settings page for
    'universeFullSettings': false,

    'fixtureassg': '',
    'showevents': false,

    'example_events': [['now', "Run when script loads"], ['cue.exit', 'When exiting the cue'], ['cue.enter', 'When entering a cue'], ['button.a', 'A button in scenes sidebar']
    ['keydown.a', "When a lowercase A is pressed in the Send Events mode on the console"], ["=log(90)", 'Example polled expression. =Expressions are polled every few seconds or on certain triggers.'],
    ['@january 5th', "Run every jan 5 at midnight"], ['@every day at 2am US/Pacific', 'Time zones supported'],
    ['@every 10 seconds', 'Simple repeating trigger'],
    ["=isNight()", 'Run if it is nighttime(polled)'], ["=isNight()", 'Run if it is nighttime(polled)'],
    ["=tv('/system/alerts.level') >= 30 ", "Run if the highest priority alert is warning(30), error(40), or critical(50) level"],
    ["=isDark()", 'Run if it is civil twilight'],
    ["=tv('TagPointName')", 'Run when tag point becomes nonzero(instant, poll is triggered on change)'],
    ["script.poll", 'Run every fast(~24Hz) polling cycle of the script, not the same as =expressions']],


    'availableTags': availableTags,
    'completers': {

        'gotoSceneNamesCompleter': function (a) {
            var c = []


            var x = this.scenemeta

            if (!x) {
                return []
            }

            for (i in x) {
                c.push([x[i].name, ''])
            }
            return c;
        },

        'gotoSceneCuesCompleter': function (a) {
            var c = []
            var n = a[1]
            if (n.indexOf('=SCENE') > -1) {
                n = this.scenename
            }
            else {
                for (i in this.scenemeta) {
                    var s = this.scenemeta[i]
                    if (s.name == n) {
                        n = i
                        break
                    }
                }
            }


            var x = this.scenecues[n]

            if (!x) {
                return []
            }

            for (i in x) {
                c.push([i, ''])
            }
            return c;
        },

        'tagPointsCompleter': function (a) {
            var c = [];
            for (i of this.availableTags) {
                c.push([i, ''])
            }
            return c;
        },

        'defaultExpressionCompleter': function (a) {
            var c = [

                ['1', 'Literal 1'],
                ['0', ''],
                ['=1+2+3', 'Spreadsheet-style expression'],
                ['=tv("TagName")', 'Get the value of TagName(0 if nonexistant)'],
                ['=stv("TagName")', 'Get the value of a string tagpoint(empty if nonexistant)'],
                ['=random()', 'Random from 0 to 1'],
                ['=SCENE', 'Name of the scene']
            ];
            for (i of this.availableTags) {
                c.push(['=tv("' + i + '")', ''])
            }
            return c;
        }
    },

    'soundfolders': [],
    'showimportexport': false,
    'evtosend': '',
    'evtypetosend': 'float',
    'evval': '',
    'savedThisSession': false,
    'scenetab': 'cue',
    'showPresets': false,
    'configuredUniverses':
    {
        'blah': { 'type': 'enttec', 'interface': 'xyz' }
    },
    'fixtureClasses': { 'dfjlkdjf': [] },
    //The selected dir and [[folders][files]] in that dir, for the
    //sound file browser
    'soundfilesdir': '',
    'soundfileslisting': [
        [],
        []
    ],
    //Filter which scenes are shown in the list
    'scenefilter': '',
    'cuefilter': '',
    'soundsearch': '',
    'soundsearchresults': [],
    'currentBindingBank': 'default',
    'localStorage': localStorage,
    'keybindmode': 'edit',
    'showAddChannels': false,
    //Keep track of what timers are running in a scene
    'scenetimers': {},
    //Formatted for display
    'cuevals': {},
    'useBlankDescriptions': useBlankDescriptions,

    'formatCueVals': function (c) {
        //Return a simplified version of the data in cuevals
        //Meant for direct display
        op = {}
        for (i in c) {
            op[i] = {}
            for (j in c[i]) {
                op[i][j] = c[i][j].v
            }
        }
        return op
    },

    'del': function (a, b) {
        old_vue_delete(a, b)
    },

    'getValueRange': getValueRange,
    //Returns new value mapped into the range when user clicks to change the range of a custom val
    //Given current val, new range info and old range info
    'mapvaluerange': function (oldv, d, newrange) {
        for (i of d) {
            if (i[2] == newrange) {
                var newd = i
                break;
            }
        }
        var d = this.getValueRange(d, oldv)

        try {
            var asfraction = (oldv - d[0]) / ((d[1] - d[0]) +
                1)
            return Math.round(asfraction * (newd[1] - newd[
                0] + 1) + newd[0])
        }
        catch (e) {
            return newd[0]
        }
    },


    'lookupFixtureType': function (f) {
        for (i in this.fixtureAssignments) {
            if (this.fixtureAssignments[i].name = f) {
                return this.fixtureAssignments[i].type;
            }
        }
        return '';
    },

    'addFixtureAssignment': function (name, t, univ, addr) {
        if (!name) {
            return;
        }
        var d = {
            'name': name,
            'type': t,
            'universe': univ,
            'addr': addr
        }

        api_link.send(['setFixtureAssignment', name, d])

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

    'dictView': function (dict, sorts, filterf) {
        //Given a dict  and a list of sort keys sorts,
        //return a list of [key,value] pairs sorted by the sort
        //keys. Earlier sort keys take precendence.

        // the lowest precedence sort key is the actual dict key.

        //Keys starting with ! are interpreted as meanng to sort in descending order

        var o = []
        Object.keys(dict).forEach(
            function (key, index) {
                if (filterf == undefined || filterf(key, dict[key])) {
                    o.push([key, dict[key]])
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
            for (i of l) {
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
    },

    'cueNamesBySceneName': function () {
        var d = {}
        for (i in this.scenemeta) {
            d[this.scenemeta[i].name] = []

            for (j in this.scenecues[i]) {
                d[this.scenemeta[i].name].push(j)
            }
        }
        return d;
    },


    'toggleTransparent': function (cue, u, c, v) {
        if (v != null) {
            this.setCueValNolock(cue, u, c, null)
        }
        else {
            this.setCueValNolock(cie, u, c, null)
        }
    },
    'promptRename'(s) {
        var x = prompt(
            "Enter new name for scene(May break existing references to scene)"
        )

        if (x != null) {

            api_link.send(['setscenename', s, x])
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
        for (i of search.toLowerCase().split(" ")) {
            if (!s.toLowerCase().includes(i)) {
                return 0;
            }
        }
        return 1;
    },
    'setCueInheritRules': function (c, r) {
        api_link.send(['setCueInheritRules', c, r])
    },


    'setCueRules': function (c, r) {
        api_link.send(['setCueRules', c, r])
    },

    'doSoundSearch': function (s) {
        api_link.send(["searchsounds", s])
    },

    //Current per scene alpha channel
    'alphas': {},
    'scenemeta': {},
    'scenename': null,
    'editingScene': null,
    'universes': {},
    'allScenes': [],
    'cues': {},
    'newcuename': '',
    'cuemeta': {},
    'availableCommands': {},
    'selectedCues': {},
    'showPages': false,
    //go from cue name to cue id
    //scenecues[sceneuuid][cuename]=cueid
    'scenecues': {},
    'formattedCues': [],
    //Indexed by universe then channel number
    'channelNames': {},
    //same info as scenevals, indexed hierarchally, as [universe][channel]
    //Actual objs are shared too so changing one obj change in in the other.

    //We must track faders the user is actively touching so new data doesn't
    //Annoy you jumping them around
    'lockedFaders': {},
    'presets': {},

    //All alarms active on server
    'sys_alerts': {},



    'deletePreset': function (p) {
        if (confirm("Really Delete")) {
            delete this.presets[p];
            api_link.send(['preset', p, None]);

        }
    },


    'renamePreset': function (p) {
        var n = prompt("Preset Name?")

        if (n && n.length) {
            var b = this.presets[p]
            if (b) {
                delete this.presets[p];
                api_link.send(['preset', p, None]);

                this.presets[n] = b;
                api_link.send(['preset', n, b]);
            }
        }
    },

    'savePreset': function (v) {
        /*Prompt saving data from the cuevals dict as a preset*/
        var v2 = {}

        // Just the vals
        for (i in v) {
            v2[i] = v[i].v
        }

        var n = prompt("Preset Name?")

        if (n && n.length) {
            this.presets[n] = v2;
            api_link.send(['preset', n, v2]);

        }
    },

    'updatePreset': function (i, v) {
        /*Update given a name and the modified data as would be found in the presets file*/
        this.presets[i] = v;
        api_link.send(['preset', i, v]);
    },
    'recomputeformattedCues': function () {

    },
    'chnamelookup': function (u, c) {
        if (this.channelNames[u] == undefined) {
            return undefined
        }

        return this.channelNames[u][c]
    },

    'prompt': prompt,
}

function f(v) {
    c = v[0]

    if (c == 'soundfolders') {
        vueapp.$data.soundfolders = v[1]
    }

    if (c == 'scenetimers') {
        vueapp.$data.scenemeta[v[1]].timers = v[2]
    }
    else if (c == 'cuehistory') {
        vueapp.$data.scenemeta[v[1]].history = v[2]
    }
    else if (c == "scenemeta") {
        if (v[2].cue) {
            if (vueapp.$data.cuemeta[v[2].cue] == undefined) {
               appMethods.getcuemeta(v[2].cue)
            }
        }

        if (v[2].alpha != undefined) {
            if (!vueapp.$data.lockedFaders[v[1]]) {
                old_vue_set(vueapp.$data.alphas, v[1], v[2].alpha);
            }
        }

        //Just update existing data if we can
        if (vueapp.$data.scenemeta[v[1]]) {
            Object.assign(vueapp.$data.scenemeta[v[1]], v[2])
        }
        else {
            var meta = v[2];
            set(vueapp.$data.scenemeta, v[1], meta);
        }

        if (vueapp.$data.selectedCues[v[1]] == undefined) {
            old_vue_set(vueapp.$data.selectedCues, v[1], 'default')
        }
        //Make an empty list of cues as a placeholder till the real data arrives
        if (vueapp.$data.scenecues[v[1]] == undefined) {
            old_vue_set(vueapp.$data.scenecues, v[1], {});
        };
    }

    else if (c == "cuemeta") {
        //Make an empty list of cues if it's not there yet
        if (vueapp.$data.scenecues[v[2].scene] == undefined) {
            old_vue_set(vueapp.$data.scenecues, v[2].scene, {});
        };
        old_vue_set(vueapp.$data.scenecues[v[2].scene], v[2].name, v[1]);


        //Make an empty list of cues as a placeholder till the real data arrives
        if (vueapp.$data.cuemeta[v[1]] == undefined) {
            old_vue_set(vueapp.$data.cuemeta, v[1], {});
        };
        set(vueapp.$data.cuemeta, v[1], v[2]);
        vueapp.$data.recomputeformattedCues();

    }

    else if (c == "event") {

        vueapp.$data.evlog.unshift(v[1])
        if (vueapp.$data.evlog.length > 250) {
            vueapp.$data.evlog = vueapp.$data.evlog.slice(0,250)
        }

        if (v[1][0].includes("error")) {
            vueapp.$data.showevents = true;
        }
    }
    else if (c == "serports") {
        vueapp.$data.serports = v[1]
    }

    else if (c == 'alerts') {
        vueapp.$data.sys_alerts = v[1]
    }
    else if (c == 'confuniverses') {
        vueapp.$data.configuredUniverses = v[1]
    }
    else if (c == 'universe_status') {
        vueapp.$data.universes[v[1]].status = v[2]
        vueapp.$data.universes[v[1]].ok = v[3]
        vueapp.$data.universes[v[1]].telemetry = v[4]
    }

    else if (c == "varchange") {
        vueapp.$data.scenemeta[v[1]]['vars'][v[2]] = v[3]
    }
    else if (c == "delcue") {
        c = vueapp.$data.cuemeta[v[1]]
        old_vue_delete(vueapp.$data.cuemeta, v[1]);
        old_vue_delete(vueapp.$data.cuevals, v[1]);
        old_vue_delete(vueapp.$data.scenecues[c.scene], c.name);
        vueapp.$data.recomputeformattedCues();
    }

    else if (c == "cnames") {
        old_vue_set(vueapp.$data.channelNames, v[1], v[2])
    }
    else if (c == "universes") {
        vueapp.$data.universes = v[1]
    }
    else if (c == "soundoutputs") {
        vueapp.$data.soundCards = v[1]
    }

    else if (c == 'soundsearchresults') {
        if (vueapp.$data.soundsearch == v[1]) {
            vueapp.$data.soundsearchresults = v[2]
        }
    }
    else if (c == 'scenecues') {
        //Scenecues only gives us cue number and id info.
        //So if the data isn't in cuemeta, fill in what we can
        d = v[2]
        for (i in v[2]) {
            if (vueapp.$data.cuemeta[d[i][0]] == undefined) {
                old_vue_set(vueapp.$data.cuemeta, d[i][0],
                    {
                        'name': i,
                        'number': d[
                            i][1]
                    })
            }

            //Make the empty list
            if (vueapp.$data.scenecues[v[1]] == undefined) {
                old_vue_set(vueapp.$data.scenecues, v[1], {});
            };


            old_vue_set(vueapp.$data.scenecues[v[1]], i, d[i][0])
        }
        vueapp.$data.recomputeformattedCues();
    }
    else if (c == "cuedata") {
        d = {}
        old_vue_set(vueapp.$data.cuevals, v[1], d)

        for (i in v[2]) {

            if (!(i in vueapp.$data.channelNames)) {
                api_link.send(['getcnames', i])
            }
            old_vue_set(vueapp.$data.cuevals[v[1]], i, {})

            for (j in v[2][i]) {
                y = {
                    "u": i,
                    'ch': j,
                    "v": v[2][i][j]
                }
                old_vue_set(vueapp.$data.cuevals[v[1]][i], j, y)
                //The other 2 don't need to be reactive, v does
                old_vue_set(y, 'v', v[2][i][j])

            }
        }
    }

    else if (c == "commands") {
        vueapp.$data.availableCommands = v[1]
    }

    else if (c == "scv") {
        x = []

        cue = v[1]
        universe = v[2]
        channel = v[3]
        value = v[4]

        if (vueapp.$data.lockedFaders[cue + ":" + universe + ":" + channel] == true) {
            return;
        }


        var needRefresh = false;
        //Empty universe dict
        if (!vueapp.$data.cuevals[cue][universe]) {

            old_vue_set(vueapp.$data.cuevals[cue], universe, {})
            needRefresh = 1;
        }

        if (v[4] !== null) {

            y = {
                "u": universe,
                'ch': channel,
                "v": value
            }
            old_vue_set(y, 'v', value)
            old_vue_set(vueapp.$data.cuevals[cue][universe], channel, y)
        }
        else {
            old_vue_delete(vueapp.$data.cuevals[cue][universe], channel)
            needRefresh = 1;
        }
    }


    else if (c == "go") {

        old_vue_set(vueapp.$data.scenemeta[v[1]], 'active', true)

    }

    else if (c == "refreshPage") {
        window.reload()
    }

    else if (c == "stop") {

        old_vue_set(vueapp.$data.scenemeta[v[1]], 'active', false)

    }
    else if (c == "ferrs") {

        vueapp.$data.ferrs = v[1]

    }
    else if (c == "fixtureclasses") {

        vueapp.$data.fixtureClasses = v[1]
    }
    else if (c == "fixtureclass") {

        old_vue_set(vueapp.$data.fixtureClasses, v[1], v[2])
    }

    else if (c == "fixtureAssignments") {

        vueapp.$data.fixtureAssignments = v[1]
    }

    else if (c == "del") {
        old_vue_delete(vueapp.$data.selectedCues, v[1])
        old_vue_delete(vueapp.$data.scenemeta, v[1])
        old_vue_delete(vueapp.$data.mtimes, v[1])
        vueapp.$data.editingScene = null

    }

    else if (c == "newscene") {
        vueapp.$data.allScenes.push([v[1], v[2]])
    }
    else if (c == 'soundfolderlisting') {
        if (v[1] == vueapp.$data.soundfilesdir) {
            vueapp.$data.soundfileslisting = v[2]
        }
    }

    else if (c == 'presets') {
        vueapp.$data.presets = v[1]
    }
}


init_api_link = function () {
    api_link.upd = f
    api_link.send(['gasd']);
    api_link.send(['getCommands']);

    // Exact sync on half seconds
    function unix_time_upd() {
        vueapp.$data.unixtime = api_link.now() / 1000
        setTimeout(unix_time_upd,
            250-(api_link.now()%250) )
    }

    unix_time_upd()
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
