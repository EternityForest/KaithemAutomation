${vars}
function set(o, k, v) {

    if (o[k] == undefined) {
        Vue.set(o, k, v)
    }
    for (var key in v) {
        // If values of same property are not equal,
        // objects are not equivalent
        if (o[k][key] !== v[key]) {
            Vue.set(o[k], key, v[key])
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


hfaderdata =
{
    'promptExactVal': function (cue, u, v) {
        var x = prompt("Enter new value for scene")

        if (x != null) {

            this.setCueValNolock(cue, u, v, x);
        }
    },
    'setCueVal': function (sc, u, ch, val) {
        appData.lockedFaders[sc + ":" + u + ":" + ch] = true;
        api_link.send(['scv', sc, u, ch, val]);
    },
    'setCueValNolock': function (sc, u, ch, val) {
        api_link.send(['scv', sc, u, ch, val]);
    },
    'unlockCueValFader': function (sc, u, ch) {
        delete appData.lockedFaders[sc + ":" + u + ":" + ch];
    },
    'getValueRange': getValueRange,

    'rmValFromCue': function (universe, ch) {
        api_link.send(['scv', appData.scenecues[appData.scenename]
        [appData.selectedCues[appData.scenename]],
            universe,
            ch,
            null
        ])
        Vue.delete(appData.cuevals[appData.selectedCues[appData
            .scenename]][appData.newcueu],
            ch)
        Vue.delete(appData.cuevals[appData.selectedCues[appData
            .scenename]][appData.newcueu],
            ch)
    },
}




//# sourceURL=appcode.js 
appData = {
    //Ace code editor
    htmloptions: {
        mode: 'html',
        theme: 'tomorrow',
        fontSize: 11,
        fontFamily: 'monospace',
        highlightActiveLine: false,
        highlightGutterLine: false
    },
    cssoptions: {
        mode: 'css',
        theme: 'tomorrow',
        fontSize: 11,
        fontFamily: 'monospace',
        highlightActiveLine: false,
        highlightGutterLine: false
    },
    jsoptions: {
        mode: 'javascript',
        theme: 'tomorrow',
        fontSize: 11,
        fontFamily: 'monospace',
        highlightActiveLine: false,
        highlightGutterLine: false
    },
    mdooptions: {
        mode: 'markdown',
        theme: 'tomorrow',
        fontSize: 11,
        fontFamily: 'monospace',
        highlightActiveLine: false,
        highlightGutterLine: false
    },


    'eventlogautoscroll': true,
    //https://stackoverflow.com/questions/6312993/javascript-seconds-to-time-string-with-format-hhmmss
    'formatInterval': formatInterval,
    'console': console,
    'sc_code': "",
    'unixtime': 0,
    'serports': [],
    'bindingsListTest': [],
    'keyboardJS': keyboardJS,
    //Code view for the fixture assignments
    'fixturescode': '',
    //Index by name
    'fixtureAssignments': {},
    'newfixname': '',
    'newfixtype': '',
    'newfixaddr': '',
    'newfixuniverse': '',
    //Fixture error info str
    'ferrs': '',
    'fixtures': '',
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

    'showfixtureassg': false,
    'fixtureassg': '',
    'showsoundoptions': false,
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


            var x = appData.scenemeta

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
                n = appData.scenename
            }
            else {
                for (i in appData.scenemeta) {
                    var s = appData.scenemeta[i]
                    if (s.name == n) {
                        n = i
                        break
                    }
                }
            }


            var x = appData.scenecues[n]

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
            for (i of appData.availableTags) {
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
            for (i of appData.availableTags) {
                c.push(['=tv("' + i + '")', ''])
            }
            return c;
        }
    },

    'showimportexport': false,
    'evtosend': '',
    'evtypetosend': 'float',
    'evval': '',
    'savedThisSession': false,
    'useBlankDescriptions': useBlankDescriptions,
    'saveToDisk': function () {
        if (this.savedThisSession == false) {
            var x = confirm("This saves directly to disk, overwriting the previous default. This message only shows the first save.")
            if (!x) {
                return
            }
            this.savedThisSession = true;
        }
        api_link.send(['saveScenes'])
    },

    'saveSetup': function () {

        api_link.send(['saveSetup'])
    },
    'saveLibrary': function () {

        api_link.send(['saveLibrary'])
    },
    'sendev': function (where) {
        api_link.send(['event', appData.evtosend, appData.evval, appData.evtypetosend, where])
    },

    'sceneev': function (evt, where) {
        api_link.send(['event', evt, '', 'str', where])
    },
    //For the raw cue data edit thing
    'cuedatafield': "",
    'refreshcuedata': function () {
        try {
            scene = this.scenename
            cueid = this.scenecues[scene][this.selectedCues[scene]]

            this.cuedatafield = jsyaml.safeDump(this
                .formatCueVals(
                    this.cuevals[cueid]));
        }
        catch
        {

        }
    },

    'del': Vue.delete,
    'refreshPorts': function () {
        api_link.send(['getserports'])
    },
    'pushSettings': function () {
        api_link.send(['setconfuniverses', appData.configuredUniverses])
    },

    'showDMXSetup': false,
    'showPresets': false,
    'showsceneoptions': false,
    'scenetab': 'cue',
    'configuredUniverses':
    {
        'blah': { 'type': 'enttec', 'interface': 'xyz' }
    },
    'gamepad': false,
    'newuniversename': "",
    'fixtureClasses': { 'dfjlkdjf': [] },
    'selectedFixtureClass': '',
    'showFixtureSetup': false,
    //The selected dir and [[folders][files]] in that dir, for the
    //sound file browser
    'soundfilesdir': '',
    'soundfileslisting': [
        [],
        []
    ],
    'setSoundfileDir': function (i) {

        if (!((i == '') | (i[0] == '/'))) {
            appData.soundfilesdir += i;
        }
        else {
            appData.soundfilesdir = i;
        }
        appData.soundfileslisting = [
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

    'setSceneSlideOverlay': function (cueid, i) {

        api_link.send(['setsceneslideoverlay', cueid, i])
    },


    'newCueFromSound': function (sc, i) {

        api_link.send(['newFromSound', sc, i])
    },
    'chTypeChanged': function (i) {
        if (appData.fixtureClasses[appData.selectedFixtureClass]
        [i][1] == 'fine') {
            Vue.set(appData.fixtureClasses[appData.selectedFixtureClass]
            [i], 2, i - 1)
            Vue.set(appData.fixtureClasses[appData.selectedFixtureClass]
            [i], 3, undefined)
        }

        else if (appData.fixtureClasses[appData.selectedFixtureClass]
        [i][1] == 'fixed') {
            var v = appData.fixtureClasses[appData.selectedFixtureClass][i]
            Vue.set(appData.fixtureClasses[appData.selectedFixtureClass]
            , i, [v[0],v[1],0,{}])
        }
        else {
            Vue.set(appData.fixtureClasses[appData.selectedFixtureClass]
            [i], 2, 0)
            Vue.set(appData.fixtureClasses[appData.selectedFixtureClass]
            [i], 3, undefined)

        }
        appData.pushfixture(i)
    },

    'setEventButtons': function (sc, i) {

        api_link.send(['seteventbuttons', sc, i])
    },


    'setDisplayTags': function (sc, i) {

        api_link.send(['setdisplaytags', sc, i])
    },

    'setSceneNotes': function (sc, i) {

        api_link.send(['setNotes', sc, i])
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
        var d = appData.getValueRange(d, oldv)

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


    'pushfixture': function (i) {
        api_link.send(['setfixtureclass', i, appData.fixtureClasses[
            i]])
    },


    'pushfixtureopz': function (i) {
        api_link.send(['setfixtureclassopz', i, appData.fixtureClasses[
            i]])
    },
    'pushfixturescode': function () {
        api_link.send(['setfixturesfromcode', appData.fixturescode])
    },

    'setFixtureAssignment': function (i, v) {
        api_link.send(['setFixtureAssignment', i, v])
    },

    'rmFixtureAssignment': function (i) {
        api_link.send(['rmFixtureAssignment', i])
    },


    'lookupFixtureType': function (f)
    {
        for (i in appData.fixtureAssignments) {
            if (appData.fixtureAssignments[i].name = f)
            {
                return appData.fixtureAssignments[i].type;    
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
        var x = appData.configuredUniverses[u];
        if (x) {
            return useBlankDescriptions(x.channelConfig);
        }
    },
    'showhidefixtures': function () {
        appData.showFixtureSetup = !appData.showFixtureSetup
        appData.getfixtureclasses()
        appData.selectedFixtureClass = ''
    },
    'showhidefixtureassignments': function () {
        appData.getfixtureclasses()
        appData.showfixtureassg = !appData.showfixtureassg;
        api_link.send(['getfixtureassg']);
    },
    'getfixtureclasses': function () {
        api_link.send(['getfixtureclasses'])
    },
    'getfixtureclass': function (i) {
        if (i == '') {
            return;
        }
        api_link.send(['getfixtureclass', i])
    },

    'addfixturetype': function () {
        x = prompt("New Fixture Type Name:", appData.selectedFixtureType)
        if (x) {
            Vue.set(appData.fixtureClasses, x, [])
            appData.selectedFixtureType = x
            api_link.send(['setfixtureclass', x, appData.fixtureClasses[x]])
            api_link.send(['getfixtureclass', x])
        }
    },
    'delfixturetype': function () {
        x = confirm("Really delete?")
        if (x) {
            Vue.delete(appData.fixtureClasses, appData.selectedFixtureType)
            api_link.send(['rmfixtureclass', appData.selectedFixtureType])
            appData.selectedFixtureType = '';
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
            if (a[0] != b[0])
            {
                return (a[0] > b[0])? 1 : -1
            }
            return 0
        });
        return (o)
    },


    'formatScenes': function () {
        return appData.dictView(appData.scenemeta, [
            '!priority', '!started', 'name'
        ]).filter(
            function (x) {
                return (x[1].name && x[1].name.includes(
                    appData.scenefilter))
            });

    },
    'cueNamesBySceneName': function () {
        var d = {}
        for (i in appData.scenemeta) {
            d[appData.scenemeta[i].name] = []

            for (j in appData.scenecues[i]) {
                d[appData.scenemeta[i].name].push(j)
            }
        }
        return d;
    },
    'formatCues': function (filt) {
        z = {}
        //list cue objects
        for (i in appData.scenecues[appData.scenename]) {
            m = appData.cuemeta[appData.scenecues[appData.scenename]
            [i]]
            if (m !== undefined) {
                if ((!filt) | i.includes(this.cuefilter)) {
                    z[i] = m
                }
            }
        }
        if (!filt) {
            appData.formattedCues = appData.dictView(z, ['number'])
            return appData.formattedCues
        }
        else {
            return appData.dictView(z, ['number'])
        }
    },

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



    'toggleTransparent': function (cue, u, c, v) {
        if (v != null) {
            appData.setCueValNolock(cue, u, c, null)
        }
        else {
            appData.setCueValNolock(cie, u, c, null)
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
    'deleteUniverse': function (u) {
        console.log(u)
        Vue.delete(appData.configuredUniverses, u)
    },
    //Filter which scenes are shown in the list
    'scenefilter': '',
    'cuefilter': '',
    'soundsearch': '',
    'soundsearchresults': [],
    'currentBindingBank': 'default',
    'localStorage': localStorage,
    'keybindscript': localStorage.getItem("keybind-script"),
    'keybindmode': 'edit',
    'showAddChannels': false,
    'showLightingControls': true,
    'showAdvancedControls': true,
    'showSoundControls': true,
    //Keep track of what timers are running in a scene
    'scenetimers': {},
    //Formatted for display
    'cuevals': {},

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
    //Used only for autocompletion, it's a list of all known tracks that we've seen so far.
    'knownTracks': {},
    'scenemeta': {},
    'scenename': null,
    'editingScene': null,
    'running_scenes': {},
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



    'deletePreset': function (p) {
        if (confirm("Really Delete"))
        {
            delete appData.presets[p];    
            api_link.send(['preset', p, None]);

        }
    },


    'renamePreset': function (p) {
        var n = prompt("Preset Name?")

        if (n && n.length)
        {
            var b = appData.presets[p]
            if (b) {
                delete appData.presets[p];
                api_link.send(['preset', p, None]);

                appData.presets[n] = b;
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

        if (n && n.length)
        {
            appData.presets[n] = v2;
            api_link.send(['preset', n, v2]);

        }
    },

    'updatePreset': function (i,v) {
        /*Update given a name and the modified data as would be found in the presets file*/
        appData.presets[i] = v;
        api_link.send(['preset', i, v]);    
    },
    'recomputeformattedCues': function () {
        appData.formatCues(0)

    },
    'chnamelookup': function (u, c) {
        if (appData.channelNames[u] == undefined) {
            return undefined
        }

        return appData.channelNames[u][c]
    },
    "getcueid": function (sceneid, cuename) {
        return (this.scenecues[sceneid][cuename])
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
        for (i in appData.cuevals[sc][fix])
        {
            if ((!(preset[i] == undefined)) && preset[i].toString().length)
                {
                api_link.send(['scv', sc, fix, i, preset[i]]);
                appData.cuevals[sc][fix][i].v = preset[i]
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
        appData.refreshcuedata()

    },
    'getallcuemeta': function (sn) {
        api_link.send(['getallcuemeta', sn]);

    },
    'cond_getcuemeta': function (b) {
        if (b) {
            api_link.send(['getallcuemeta', this.scenename]);
        }
    },
    'selectscene': function (sc, sn) {
        this.getcuedata(this.scenecues[sn][this.selectedCues[
            sc] || 'default'])
        this.editingScene = sc;
        this.scenename = sn;
        api_link.send(['gsd', sn]);
        api_link.send(['getallcuemeta', sn]);
        appData.refreshcuedata()
        appData.recomputeformattedCues();


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

    'toggleByName': function (sn) {

        api_link.send(['togglebyname', sn]);
    },

    'stopByName': function (sn) {

        api_link.send(['stopbyname', sn]);
    },

    'shortcut': function (sc) {
        api_link.send(['shortcut', appData.sc_code]);
        appData.sc_code = ''

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
        appData.lockedFaders[sc] = true;
        api_link.send(['setalpha', sc, v]);
        appData.alphas[sc] = v
    },
    'unlockAlpha': function (sc) {
        delete appData.lockedFaders[sc];
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

    'addcue': function (sc, v) {
        api_link.send(['addcue', sc, v]);
        //There's a difference between "not there" undefined and actually set to undefined....
        if (appData.scenecues[sc][v] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            Vue.set(appData.scenecues[sc], v, undefined);
            appData.recomputeformattedCues();
        };
        setTimeout(function () {
            Vue.set(appData.selectedCues,
                sc, v)
        }, 70)
    },

    'clonecue': function (sc, cue, v) {
        api_link.send(['clonecue', cue, v]);
        //There's a difference between "not there" undefined and actually set to undefined....
        if (appData.scenecues[sc][v] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            Vue.set(appData.scenecues[sc], v, undefined);
            appData.recomputeformattedCues();
        };
        setTimeout(function () {
            Vue.set(appData.selectedCues,
                sc, v)
        }, 70)

    },
    'gotonext': function (currentcueid) {
        nextcue = appData.cuemeta[currentcueid].next

        cue = nextcue || (appData.cuemeta[currentcueid].defaultnext)
        if (!cue) {
            return
        }
        api_link.send(['addcue', appData.scenename, nextcue]);
        api_link.send(['getcuedata', cue]);

        //There's a difference between "not there" undefined and actually set to undefined....
        if (appData.scenecues[cue] == undefined) {
            //Placeholder so we can at least show a no cue found message till it arrives
            set(appData.scenecues[appData.scenename], cue,
                undefined);
        }
        setTimeout(function () {
            Vue.set(appData.selectedCues,
                appData.scenename, cue)
        },
            30)
    },
    'rmcue': function (cue) {
        appData.selectedCues[appData.scenename] = 'default'
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
    'setcuevaldata': function (cue, v) {
        api_link.send(['setcuevaldata', cue, jsyaml.safeLoad(v)]);
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
        var  t = ['.mp3','.ogg','.wav','.oga','.opus','.aac','.flac']
        for(let i of t)
        {
            if(s.endsWith(i))
            {
                document.getElementById("soundpreview").src = "WebMediaServer?file="+encodeURIComponent(s);
                document.getElementById("soundpreview").currentTime = 0;
                document.getElementById("soundpreview").play();
                document.getElementById("textpreview").src = "";
                document.getElementById("textpreview").style.display='none'
                document.getElementById("soundpreview").style.display='block'
                return
            }
        }
        document.getElementById("textpreview").src = "WebMediaServer?file="+encodeURIComponent(s);
        document.getElementById("soundpreview").src = ""
        document.getElementById("textpreview").style.display='block'
        document.getElementById("soundpreview").style.display='none'

    },

    'closePreview': function(s)
    {
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

        appData.scenemeta[sc].alpha = v;
        api_link.send(['setdalpha', sc, v]);
    },


    'setcrossfade': function (sc, v) {

        appData.scenemeta[sc].crossfade = v;
        api_link.send(['setcrossfade', sc, v]);
    },
    'setmqtt': function (sc, v) {

        appData.scenemeta[sc].mqttServer = v;
        api_link.send(['setMqttServer', sc, v]);
    },

    "setmqttfeature": function (sc, feature, v) {
        api_link.send(['setmqttfeature', sc, feature, v]);
    },
    'setmidi': function (sc, v) {

        appData.scenemeta[sc].midiSource = v;
        api_link.send(['setMidiSource', sc, v]);
    },
    'setvisualization': function (sc, v) {

        appData.scenemeta[sc].musicVisualizations = v;
        api_link.send(['setMusicVisualizations', sc, v]);
    },

    'setcommandtag': function (sc, v) {

        appData.scenemeta[sc].commandTag = v;
        api_link.send(['setscenecommandtag', sc, v]);
    },

    'setdefaultnext': function (sc, v) {

        appData.scenemeta[sc].defaultNext = v;
        api_link.send(['setDefaultNext', sc, v]);
    },
    'setinfodisplay': function (sc, v) {

        appData.scenemeta[sc].infoDisplay = v;
        api_link.send(['setinfodisplay', sc, v]);
    },
    'setutility': function (sc, v) {

        appData.scenemeta[sc].utility = v;
        api_link.send(['setutility', sc, v]);
    },
    'setpriority': function (sc, v) {
        api_link.send(['setpriority', sc, v]);
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
        api_link.send(['addscene', appData.newscenename]);
    },
    'prompt': prompt,

    'addMonitorScene': function () {
        api_link.send(['addmonitor', appData.newscenename]);
    },


    'addRangeEffect': function (fix) {
        appData.addThisFixToCurrentCue(fix,
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

        api_link.send(['addcuef', appData.scenecues[
            appData.scenename]
        [appData.selectedCues[appData.scenename]],
            fix, idx, len, spacing
        ]);

    },
    'rmFixCue': function (cue, fix) {
        api_link.send(['rmcuef', cue, fix]);

    },

    'addValToCue': function () {
        if (!appData.newcueu) {
            return
        }
        api_link.send(['addcueval', appData.scenecues[
            appData.scenename]
        [appData.selectedCues[appData.scenename]],
            appData.newcueu, appData.newcuevnumber
        ]);
        if (parseInt(appData.newcuevnumber) != NaN) {
            appData.newcuevnumber = parseInt(appData.newcuevnumber) + 1
        }

    },

    'sortscenes': function () {

        appData.allScenes.sort(function (a, b) {
            return a[3] - b[3]
        })
    },
    'editMode': function () {
        keyboardJS.reset();
        appData.keybindmode = "edit";
    },
    'runMode': function () {
        rebind(appData.keybindscript);
        appData.keybindmode = "run";
    },
    //https://stackoverflow.com/questions/18082/validate-decimal-numbers-in-javascript-isnumeric
    'isNumeric': function (input) {
        var RE = /^-{0,1}\d*\.{0,1}\d+$/;
        return (RE.test(input));
    }

}

function f(v) {
    c = v[0]

    if (c == 'scenetimers') {
        appData.scenemeta[v[1]].timers = v[2]
    }
    if (c == 'cuehistory') {
        appData.scenemeta[v[1]].history = v[2]
    }
    if (c == "scenemeta") {
        if (v[2].cue) {
            if (appData.cuemeta[v[2].cue] == undefined) {
                appData.getcuemeta(v[2].cue)
            }
        }

        if (v[2].alpha != undefined) {
            if (!appData.lockedFaders[v[1]]) {
                Vue.set(appData.alphas, v[1], v[2].alpha);
            }
        }

        //Just update existing data if we can
        if (appData.scenemeta[v[1]]) {
            Object.assign(appData.scenemeta[v[1]], v[2])
        }
        else {
            var meta = v[2];
            set(appData.scenemeta, v[1], meta);
        }

        if (appData.selectedCues[v[1]] == undefined) {
            Vue.set(appData.selectedCues, v[1], 'default')
        }
        //Make an empty list of cues as a placeholder till the real data arrives
        if (appData.scenecues[v[1]] == undefined) {
            Vue.set(appData.scenecues, v[1], {});
        };
    }

    if (c == "cuemeta") {
        //Make an empty list of cues if it's not there yet
        if (appData.scenecues[v[2].scene] == undefined) {
            Vue.set(appData.scenecues, v[2].scene, {});
        };
        Vue.set(appData.scenecues[v[2].scene], v[2].name, v[1]);


        //Make an empty list of cues as a placeholder till the real data arrives
        if (appData.cuemeta[v[1]] == undefined) {
            Vue.set(appData.cuemeta, v[1], {});
        };
        set(appData.cuemeta, v[1], v[2]);
        appData.recomputeformattedCues();

    }

    if (c == "event") {

        appData.evlog.push(v[1])
        if (appData.evlog.length > 250) {
            appData.evlog = appData.evlog.slice(-250)
        }

        if (v[1][0].includes("error")) {
            appData.showevents = true;
        }

        if (appData.showevents) {
            if (appData.eventlogautoscroll) {
                var d = document.getElementById('eventlogbox');
                var isscrolled = d.scrollTop + d.clientHeight + 35 >= d.scrollHeight;

                if (isscrolled) {
                    setTimeout(function () {
                        if (d) {

                            d.scrollTop = d.scrollHeight;

                        }
                    }, 150)
                }

            }

        }
        var element = document.getElementById('eventlogbox_scene');

        if (element) {
            setTimeout(function () {
                if (element) {
                    element.scrollTop = element.scrollHeight - element.clientHeight;
                }
            }, 150)
        }
    }
    if (c == "serports") {
        appData.serports = v[1]
    }
    if (c == 'confuniverses') {
        appData.configuredUniverses = v[1]
    }
    if (c == 'universe_status') {
        appData.universes[v[1]].status = v[2]
        appData.universes[v[1]].ok = v[3]
        appData.universes[v[1]].telemetry = v[4]
    }

    if (c == "varchange") {
        appData.scenemeta[v[1]]['vars'][v[2]] = v[3]
    }
    if (c == "delcue") {
        c = appData.cuemeta[v[1]]
        Vue.delete(appData.cuemeta, v[1]);
        Vue.delete(appData.cuevals, v[1]);
        Vue.delete(appData.scenecues[c.scene], c.name);
        appData.recomputeformattedCues();
    }

    if (c == "cnames") {
        Vue.set(appData.channelNames, v[1], v[2])
    }
    if (c == "universes") {
        appData.universes = v[1]
    }
    if (c == "soundoutputs") {
        appData.soundCards = v[1]
    }

    if (c == 'soundsearchresults') {
        if (appData.soundsearch == v[1]) {
            appData.soundsearchresults = v[2]
        }
    }
    if (c == 'scenecues') {
        //Scenecues only gives us cue number and id info.
        //So if the data isn't in cuemeta, fill in what we can
        d = v[2]
        for (i in v[2]) {
            if (appData.cuemeta[d[i][0]] == undefined) {
                Vue.set(appData.cuemeta, d[i][0],
                    {
                        'name': i,
                        'number': d[
                            i][1]
                    })
            }

            //Make the empty list
            if (appData.scenecues[v[1]] == undefined) {
                Vue.set(appData.scenecues, v[1], {});
            };


            Vue.set(appData.scenecues[v[1]], i, d[i][0])
        }
        appData.recomputeformattedCues();
    }
    if (c == "cuedata") {
        d = {}
        Vue.set(appData.cuevals, v[1], d)

        for (i in v[2]) {

            if (!(i in appData.channelNames)) {
                api_link.send(['getcnames', i])
            }
            Vue.set(appData.cuevals[v[1]], i, {})

            for (j in v[2][i]) {
                y = {
                    "u": i,
                    'ch': j,
                    "v": v[2][i][j]
                }
                Vue.set(appData.cuevals[v[1]][i], j, y)
                //The other 2 don't need to be reactive, v does
                Vue.set(y, 'v', v[2][i][j])

            }
        }
        appData.refreshcuedata()

    }

    else if (c == "commands") {
        appData.availableCommands = v[1]
    }

    if (c == "scv") {
        x = []

        cue = v[1]
        universe = v[2]
        channel = v[3]
        value = v[4]

        if (appData.lockedFaders[cue + ":" + universe + ":" + channel] == true) {
            return;
        }


        var needRefresh = false;
        //Empty universe dict
        if (!appData.cuevals[cue][universe]) {

            Vue.set(appData.cuevals[cue], universe, {})
            needRefresh = 1;
        }

        if (v[4] !== null) {

            y = {
                "u": universe,
                'ch': channel,
                "v": value
            }
            Vue.set(y, 'v', value)
            Vue.set(appData.cuevals[cue][universe], channel, y)
        }
        else {
            Vue.delete(appData.cuevals[cue][universe], channel)
            needRefresh = 1;
        }
        if (needRefresh) {
            appData.refreshcuedata()
        }

    }


    if (c == "go") {

        Vue.set(appData.scenemeta[v[1]], 'active', true)

    }

    if(c == "refreshPage")
    {
        window.reload()
    }
    
    if (c == "stop") {

        Vue.set(appData.scenemeta[v[1]], 'active', false)

    }
    if (c == "ferrs") {

        appData.ferrs = v[1]

    }
    if (c == "fixtures") {

        appData.fixtures = v[1]

    }
    if (c == "fixtureclasses") {

        appData.fixtureClasses = v[1]
    }
    if (c == "fixtureclass") {

        Vue.set(appData.fixtureClasses, v[1], v[2])
    }

    else if (c == "fixtureascode") {

        appData.fixturescode = v[1]
    }

    if (c == "fixtureAssignments") {

        appData.fixtureAssignments = v[1]
    }

    if (c == "del") {
        Vue.delete(appData.selectedCues, v[1])
        Vue.delete(appData.scenemeta, v[1])
        Vue.delete(appData.running_scenes, v[1])
        Vue.delete(appData.mtimes, v[1])
        appData.editingScene = null

    }

    if (c == "newscene") {
        appData.allScenes.push([v[1], v[2]])
    }
    if (c == 'soundfolderlisting') {
        if (v[1] == appData.soundfilesdir) {
            appData.soundfileslisting = v[2]
        }
    }

    if (c == 'presets') {
        appData.presets = v[1]
    }
}


boardapi_msghandler = f
api_link.upd = f
api_link.send(['gasd']);
api_link.send(['getCommands']);

setInterval(function () {
    appData.unixtime = api_link.now() / 1000
}, 1000 / 8)
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


keysdown = {}
keyHandle = function (e) {
    if (keysdown[e.key] != undefined) {
        if (keysdown[e.key]) {
            return;
        }

    }
    keysdown[e.key] = true;
    e.preventRepeat();
    api_link.send(['event', "keydown." + e.key, 1, 'int', "__global__"])
}
keyUpHandle = function (e) {
    if (keysdown[e.key] != undefined) {
        if (!keysdown[e.key]) {
            return;
        }

    }
    keysdown[e.key] = false;
    api_link.send(['event', "keyup." + e.key, 1, 'int', "__global__"])
}
rebind = function (data) {
    keyboardJS.reset()
    keyboardJS.bind(keyHandle)
    keyboardJS.bind(null, keyUpHandle)

}
