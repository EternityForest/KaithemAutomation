<style scoped>
.event {
    border-style: solid;
    border-width: 1px;
    border-color: black;
    background-color: white;
    padding: 1em;
    font-weight: bold;
    align-self: stretch;
    border-radius: 1.5em;
}

.action {
    padding: 1em;
    align-self: stretch;
    max-width: 12em;
}

.action,
.event {
    height: 12em;
}

.selected {
    border-width: 4px;
    border-color: darkgrey;
    border-style: dotted;
}

p.small {
    font-size: 80%;
    font-weight: normal;
}

.inspector {
    background-color: rgba(255, 255, 255, 0.5);
    max-width: 40vw;
    width: 28em;
    border-style: solid;
    border-width: 1px;
    border-color: black;
    padding: 0.5em;
    border-radius: 5px;
    overflow: visible;
    margin-right: 4px;
}

.rulesbox {
    background-color: rgba(255, 255, 255, 0.5);
    padding: 0.5em;

}
</style>
<template>
    <div class="w-full">
        <div class="w-full">
            <div class="flex-row gaps">

                <div v-if="selectedCommand == 0 && selectedBinding" class="col-3 card min-h-24rem">
                    <h3>Block Inspector</h3>

                    <p>
                        Event Trigger. Runs the actions when something happens.
                    </p>

                    <h4>Parameters</h4>

                    <label>Run on
                        <combo-box v-model="selectedBinding[0]" v-bind:options="example_events"
                            v-on:change="$emit('input', rules);"></combo-box>
                    </label>
                    <h4>Delete</h4>
                    <button v-on:click="deleteBinding(selectedBinding); $emit('input', rules);">Remove binding and all
                        actions</button>
                </div>

                <div v-if="selectedCommand" class="card col-3 min-h-24rem">
                    <h3>Block Inspector</h3>
                    Type
                    <combo-box v-model="selectedCommand[0]" v-bind:options="getPossibleActions()"
                        v-bind:pinned="getSpecialActions()" v-on:input="setCommandDefaults(selectedCommand);"
                        v-on:change="$emit('input', rules);"></combo-box>
                    <h4>Config</h4>
                    <div v-if="selectedCommand[0] == 'set'">
                        Set a variable named <combo-box v-model="selectedCommand[1]" v-bind:pinned="pinnedvars"
                            v-on:change="$emit('input', rules)"></combo-box> <br>to<br> <combo-box
                            v-model="selectedCommand[2]" v-on:change="$emit('input', rules)"></combo-box><br>
                        and always return True.
                    </div>

                    <div v-if="selectedCommand[0] == 'pass'">
                        Do nothing and return True.
                    </div>

                    <div v-if="selectedCommand[0] == 'maybe'">
                        Continue action with :<input v-model="selectedCommand[1]" v-on:change="$emit('input', rules)">%
                        chance <br> otherwise
                        return None and stop the action.
                    </div>

                    <div v-if="(!(selectedCommand[0] in specialCommands)) && ((commands[selectedCommand[0]]))">
                        <table>
                            <tr v-for="i in commands[selectedCommand[0]].args.keys()">
                                <td>{{ commands[selectedCommand[0]].args[i][0] }}</td>
                                <td><combo-box v-model="selectedCommand[i + 1]" v-on:change="$emit('input', rules)"
                                        :options="getCompletions(selectedCommand, commands[selectedCommand[0]].args[i][0])"></combo-box>
                                </td>
                            </tr>
                        </table>
                        <h5>Docs</h5>

                        <pre style="white-space: pre-wrap;">{{ commands[selectedCommand[0]].doc }}</pre>

                    </div>
                    <button
                        v-on:click="rules[selectedBindingIndex][1].splice(selectedCommandIndex, 1); selectedCommandIndex -= 1; $emit('input', rules);">Delete</button>
                    <button v-if="selectedCommandIndex > 0"
                        v-on:click="swapArrayElements(rules[selectedBindingIndex][1], selectedCommandIndex, selectedCommandIndex - 1); selectedCommandIndex -= 1; $emit('input', rules);">
                        Move Back</button>
                    <button v-if="selectedCommandIndex < (rules[selectedBindingIndex][1].length - 1)"
                        v-on:click="swapArrayElements(rules[selectedBindingIndex][1], selectedCommandIndex, selectedCommandIndex + 1); selectedCommandIndex += 1; $emit('input', rules);">
                        Move Forward</button>

                </div>



                <div class="flex-row gaps col-9">
                    <div v-for="(i, idx) in rules" class="w-sm-double card">
                        <header>
                            <div class="tool-bar">
                                <button v-bind:class="{ highlight: selectedBinding == i }" style="flex-grow: 50;"
                                    v-on:click="selectedBindingIndex = rules.indexOf(i); selectedCommandIndex = -1">

                                    <b>On {{ i[0] }}</b>
                                </button>

                                <button v-on:click="moveCueRuleDown(idx)">Move down</button>
                            </div>

                        </header>

                        <div class="flex-row gaps w-full padding nogaps">

                            <div v-for="j in i[1]" style="align-self:stretch; display:inline-flex;">
                                <button v-bind:class="{'w-12em':1, action: 1, selected: (selectedBinding == i & selectedCommand == j) }"
                                    v-on:click="selectedCommandIndex = i[1].indexOf(j); selectedBindingIndex = rules.indexOf(i)">

                                    <template style="min-width:6em;max-width:12em;overflow:hidden"
                                        v-if="((commands[j[0]]))">

                                        <b>{{ j[0] }}</b><br>
                                            <span class="border" v-for="i in commands[j[0]].args.keys()">
                                                {{ j[i + 1] }}
                                            </span><span> </span>
                                    </template>


                                    <template v-if="(!(j[0] in commands))">
                                        {{ j }}
                                    </template>
                                </button>
                                <i class="icofont-arrow-right" style="align-self:center; text-align:center;"></i>

                            </div>
                            <div style="align-self:stretch;">

                                <button class="action" style="align-self:stretch;"
                                    v-on:click="i[1].push(['pass']); $emit('input', rules)"><b>Add Action</b></button>
                            </div>

                        </div>
                    </div>
                    <button style="width: 95%; margin-top: 0.5em;"
                        title="Add a rule that the scene should do something when an event fires"
                        v-on:click="rules.push(['cue.enter', [['goto', '=SCENE', '']]]); $emit('input', rules);"><b>Add
                        Rule</b></button>

                </div>


            </div>

        </div>
    </div>
</template>

<script>
module.exports = {

    props: ['modelValue', 'commands', 'pinnedvars', "inspector", "completers", "example_events"],
    components: {
        "combo-box": httpVueLoader("/static/vue/ComboBox.vue"),
    },
    watch: {
        modelValue: function (newVal) {
            this.rules = newVal
        },
        completers: function (newVal) {
            this.argcompleters = newVal || {}
        }
    },

    computed: {
        "sceneNames": function () {
            var l = [];
            for (i in this.scenes) {
                l.push([i, ''])
            }
            return l;
        },
        "selectedBinding": function () {
            if (this.selectedBindingIndex == -1) {
                return 0;
            }
            return this.rules[this.selectedBindingIndex];
        },
        "selectedCommand": function () {
            if (this.selectedBindingIndex == -1) {
                return 0;
            }
            if (this.selectedCommandIndex == -1) {
                return 0;
            }
            if (this.rules[this.selectedBindingIndex]) {
                return this.rules[this.selectedBindingIndex][1][this.selectedCommandIndex];
            }
            return 0;

        }
    },
    data: function () {
        return ({
            "getCompletions": function (fullCommand, arg) {
                var t = this.commands[fullCommand[0]].completionTags
                if (t == undefined) {

                    try {
                        return this.argcompleters['defaultExpressionCompleter'](fullCommand)
                        return c(fullCommand)
                    }
                    catch (e) {
                        return [];
                    }
                }
                t = t[arg]
                var c = this.argcompleters[t]

                try {
                    if (c == undefined) {
                        return this.argcompleters['defaultExpressionCompleter'](fullCommand)
                    }

                    return c(fullCommand)
                }
                catch (e) {
                    return [];
                }
            },


            'moveCueRuleDown': function (idx) {
                var rules = [...this.modelValue];

                if (idx < rules.length - 1) {
                    var t = rules[idx + 1]
                    rules[idx + 1] = rules[idx]
                    rules[idx] = t
                }
                this.$emit('input', rules)
            },


            swapArrayElements: function (arr, indexA, indexB) {
                var temp = arr[indexA];
                arr[indexA] = arr[indexB];
                arr[indexB] = temp;
            },
            rules: this.modelValue,
            argcompleters: (this.completers || {}),
            getPossibleActions: function () {
                var l = [];
                for (i in this.commands) {
                    if (this.commands[i] == null) {
                        console.log("Warning: Null entry for command info for" + i)
                    }
                    else {
                        //Just use the special version if possible
                        if (!(i in this.specialCommands)) {
                            l.push([i, this.commands[i].doc || ''])
                        }
                    }
                }
                return l
            },


            getSpecialActions: function () {
                var l = [];
                for (i in this.specialCommands) {
                    //Prefer the special version
                    l.push([i, this.specialCommands[i].description])
                }

                return l
            },

            selectedCommandIndex: -1,
            selectedBindingIndex: -1,


            //Stuff we have built in HTML templating for
            specialCommands: {
                'set': {
                    args: [['var', ''], ['val', '']],
                    description: "Sets a variable"
                },
                'pass': {
                    args: [],
                    description: ""
                },
                'maybe': {
                    args: [['chance', '50']],
                    description: ""
                }
            },
            deleteBinding: function (b) {
                if (confirm("really delete binding?")) {
                    this.removeElement(this.rules, b)
                }

            },
            removeElement: function (array, e) {
                var index = array.indexOf(e);
                if (index > -1) {
                    array.splice(index, 1);
                }
            },
            setCommandDefaults: function (l) {
                //Builtins that don't have to come from the server.
                //lists of type,default pairs basically.

                var d = 0;

                //Get description data for that type
                if (l[0] in this.specialCommands) {
                    d = this.specialCommands[l[0]]['args']
                }

                //Get description data for that type
                if (l[0] in this.commands) {
                    d = this.commands[l[0]]['args']
                }

                //Not a command we know anything about to set defaults
                if (d == 0) {
                    return;
                }

                //Get rid of everything except the command name
                l.splice(1);

                //Push the default values for the command
                for (i of d) {
                    l.push(i[1] || '')
                }
                return l;
            }
        })
    }
}

</script>