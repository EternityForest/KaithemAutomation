<style scoped>

        .event {
            border-style: solid;
            border-width: 1px;
            border-color: black;
            background-color: white;
            padding: 1em;
            font-weight: bold;
            height: 100%;
            border-radius: 1.5em;
        }
        .action {
            border-style: solid;
            border-width: 1px;
            border-color: black;
            background-color: white;
            padding: 1em;
            font-weight: bold;
            height: 100%;
            border-radius:0px;
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
            background-color: rgba(255,255,255,0.5);
            max-width: 24em;
            border-style: solid;
            border-width: 1px;
            border-color: black;
            padding: 0.5em;
            border-radius: 5px;
            overflow:auto;
            margin-right:4px;
        }
        .rulesbox
        {
            background-color: rgba(255,255,255,0.5);
            padding: 0.5em;
        }
    </style>
    <template>
        <div>
            <div>
                <div style="display:flex;flex-direction:row;">
    
                    <div v-if="selectedCommand==0 && selectedBinding" class="inspector">
                        <h3>Block Inspector</h3>
    
                        <p>
                            Event Trigger. Runs the actions when something happens.
                        </p>
    
                        <h4>Parameters</h4>
    
                        Run when:
                        <combo-box v-model="selectedBinding[0]" v-bind:options="eventsList" v-on:change="$emit('input',rules);"></combo-box> occurs
    
                        <h4>Delete</h4>
                        <button v-on:click="deleteBinding(selectedBinding);$emit('input',rules);">Remove binding and all actions</button>
                    </div>
    
                    <div v-if="selectedCommand" class="inspector">
                        <h3>Block Inspector</h3>
                        Type
                        <combo-box v-model="selectedCommand[0]" v-bind:options="getPossibleActions()"   v-bind:pinned="getSpecialActions()" v-on:input="setCommandDefaults(selectedCommand);"
                            v-on:change="$emit('input',rules);"></combo-box>
                            <h4>Config</h4>
                            <div v-if="selectedCommand[0]=='set'">
                                Set a variable named <combo-box v-model="selectedCommand[1]" v-bind:pinned="pinnedvars" v-on:change="$emit('input',rules)"></combo-box> <br>to<br> <combo-box v-model="selectedCommand[2]"  
                                v-on:change="$emit('input',rules)"></combo-box><br>
                                and always return True.
                            </div>
    
                            <div v-if="selectedCommand[0]=='pass'">
                                Do nothing and return True.
                            </div>
    
                            <div v-if="selectedCommand[0]=='goto'">
                                Trigger scene:<combo-box v-bind:options="sceneNames" v-model="selectedCommand[1]" v-on:change="$emit('input',rules)"></combo-box> <br>to go to cue:<br> 
                                <combo-box v-bind:options="cueNames(selectedCommand[1],parentscene)" v-model="selectedCommand[2]"  v-on:change="$emit('input',rules)"></combo-box><br> and always return True.
                            </div>
    
    
                            <div v-if="selectedCommand[0]=='maybe'">
                                Continue action with :<input v-model="selectedCommand[1]" v-on:change="$emit('input',rules)">% chance <br> otherwise
                                return None and stop the action.
                            </div>
    
                            <div v-if="(!(selectedCommand[0] in specialCommands)) && ((commands[selectedCommand[0]] ))">
                                <table>
                                    <tr v-for="i in commands[selectedCommand[0]].args.keys()">
                                        <td>{{commands[selectedCommand[0]].args[i][0]}}</td>
                                        <td><input v-model="selectedCommand[i+1]" v-on:change="$emit('input',rules)"></td>
                                    </tr>
                                </table>
                                <h5>Docs</h5>
    
                                <pre style="white-space: pre-wrap;">{{commands[selectedCommand[0]].doc}}</pre>
    
                            </div>
                            <button v-on:click="rules[selectedBindingIndex][1].splice(selectedCommandIndex,1); selectedCommandIndex-=1;$emit('input',rules);">Delete</button>
                            <button v-if="selectedCommandIndex>0" v-on:click="swapArrayElements(rules[selectedBindingIndex][1],selectedCommandIndex,selectedCommandIndex-1);selectedCommandIndex-=1;$emit('input',rules);">
                            Move Back</button>
                            <button v-if="selectedCommandIndex<(rules[selectedBindingIndex][1].length-1)" v-on:click="swapArrayElements(rules[selectedBindingIndex][1],selectedCommandIndex,selectedCommandIndex+1);selectedCommandIndex+=1;$emit('input',rules);">
                            Move Forward</button>
    
                    </div>
    
    
    
                    <div style="display:flex;flex-direction:column;align-items: center;">
                        <h3>Event Actions</h3>
                        <div  class="rulesbox" style="overflow:scroll">
                            <div v-for="i in rules" style="display:flex;flex-direction:row; padding:3px;">
                                <button v-bind:class="{event:1,bindingname:1,selected:selectedBinding==i&selectedCommand==0}" v-on:click="selectedBindingIndex=rules.indexOf(i); selectedCommandIndex=-1">
                        <p class="small">When</p>
                        {{i[0]}}
                        <p class="small">Occurs</p>
                    </button>
                                <span style="align-self:center;color:grey; font-size:200%;font-weight:bolder; overflow:hidden;flex-shrink=8">&gt</span>
    
                                <div v-for="j in i[1]" style="align-self:stretch;">
                                    <button v-bind:class="{action:1,selected:(selectedBinding==i&selectedCommand==j)}" v-on:click="selectedCommandIndex=i[1].indexOf(j);selectedBindingIndex=rules.indexOf(i)">
                            
                                        <div v-if="j[0]=='set'">
                                            Set<br><b>{{j[1]}}</b> to<br><b>{{j[2]}}</b>
                                        </div>
                                        
                                        <div v-if="j[0]=='goto'">
                                            Scene {{j[1]}}<br>
                                            goes to {{j[2]}}
                                        </div>
    
                                        <div v-if="j[0]=='pass'">
                                            Do Nothing
                                        </div>
    
                                        <div v-if="j[0]=='maybe'">
                                            Continue {{j[1]}}%<br>
                                            of the time,</br> otherwise
                                            stop.
                                        </div>

                                        <div style="min-width:8em;max-width:30em;overflow:hidden" v-if="(!(j[0] in specialCommands)) && ((commands[j[0]]))">
                                            {{j[0]}}<br>
                                            <table border=1 style="width:100%">
                                                <tr v-for="i in commands[j[0]].args.keys()">
                                                    <td>{{commands[j[0]].args[i][0]}}</td>
                                                    <td>{{j[i+1]}}</td>
                                                </tr>
                                            </table>
                                        </div>
                                    
                                    
                                        <div v-if="!(j[0] in specialCommands) && (!(j[0] in commands))">
                                        {{j}}
                                        </div>
                                </button>
                                    <span style="align-self:center;color:grey; font-size:200%;font-weight:bolder; overflow:hidden;flex-shrink=8">&gt</span>    
                                </div>
    
                                <button class="action" style="align-self:center;" v-on:click="i[1].push(['pass']);$emit('input',rules)">Add Action</button>
                            </div>
                        </div>
                        <button title="Add a rule that the scene should do something when an event fires" v-on:click="rules.push(['change_this',[]]);$emit('input',rules);">Add Rule</button>
    
                    </div>
    
    
                </div>
    
            </div>
        </div>
    </template>
    
    <script>
        module.exports={
    
        props: ['value','commands','scenes','pinnedvars', "inspector","parentscene"],
        components:{
            "combo-box": httpVueLoader("/static/vue/ComboBox.vue")
        },
        watch: {
            value: function(newVal) { 
               this.rules = newVal
            }
          },
        computed:{
            "sceneNames":function()
            {
                var l=[];
                for (i in this.scenes)
                {
                    l.push([i,''])
                }
                return l;
            },
            "selectedBinding":function()
            {
                if (this.selectedBindingIndex==-1)
                {
                    return 0;
                }
                return this.rules[this.selectedBindingIndex];
            },
           "selectedCommand":function()
            {
                if (this.selectedBindingIndex==-1)
                {
                    return 0;
                }
                if (this.selectedCommandIndex==-1)
                {
                    return 0;
                }
                if(this.rules[this.selectedBindingIndex]){
                    return this.rules[this.selectedBindingIndex][1][this.selectedCommandIndex];
                }
                return 0;
                    
                }
        },
        data:function(){
            return({
    
                  "cueNames":function(s, parentscene)
                    {
                        if(s=="=SCENE")
                        {
                            s = parentscene;
                        }
                        if(this.scenes[s]==undefined)
                        {
                            return [];
                        }
                        var l=[];
                        for (i of this.scenes[s])
                        {
                            l.push([i,''])
                        }
                        return l;
                    },
                swapArrayElements:function(arr, indexA, indexB) {
                    var temp = arr[indexA];
                    arr[indexA] = arr[indexB];
                    arr[indexB] = temp;
                },
                rules:this.value,
                eventsList: [['now', "Run when script loads"],['cue.exit','When exiting a cue'],['cue.enter','When entering a cue'], ['keydown.a',"When a lowercase A is pressed in the Send Events mode"]],
                
    
                getPossibleActions: function()
                {
                    var l =[];
                    for (i in this.commands)
                    {
                        if(this.commands[i]==null)
                        {
                            console.log("Warning: Null entry for command info for"+i)
                        }
                        else
                        {
                            //Just use the special version if possible
                            if(!(i in this.specialCommands))
                            {
                                l.push([i,this.commands[i].doc||''])
                            }
                        }
                    }
                    return l
                },
    
    
                getSpecialActions: function()
                {
                    var l =[];
                    for (i in this.specialCommands)
                    {
                        //Prefer the special version
                        l.push([i,this.specialCommands[i].description])
                    }
            
                    return l
                },
    
                selectedCommandIndex:-1,
                selectedBindingIndex: -1,
    
    
                //Stuff we have built in HTML templating for
                specialCommands : {
                        'set': {
                                args:[['var',''],['val','']],
                                description: "Sets a variable"
                            },
                        'goto': {
                                args:[['Scene',''],['Cue','']],
                                description: "Trigger scene to go to cue"
                            },
                        'pass':{
                            args:[],
                            description:""
                        },
                        'maybe':{
                            args:[['chance','50']],
                            description:""
                        }
                    }, 
                deleteBinding: function(b)
                {
                    if(confirm("really delete binding?"))
                    {
                        this.removeElement(this.rules, b)
                    }
    
                },
                removeElement:function(array, e){
                    var index = array.indexOf(e);
                    if (index > -1) {
                        array.splice(index, 1);
                    }
                },
                setCommandDefaults:function(l)
                {
                    //Builtins that don't have to come from the server.
                    //lists of type,default pairs basically.
                   
                    var d = 0;
                    
                    //Get description data for that type
                    if(l[0] in this.specialCommands)
                    {
                        d=this.specialCommands[l[0]]['args']
                    }
    
                    //Get description data for that type
                    if(l[0] in this.commands)
                    {
                        d=this.commands[l[0]]['args']
                    }
                    
                    //Not a command we know anything about to set defaults
                    if (d==0)
                    {
                        return;
                    }
                    
                    //Get rid of everything except the command name
                    l.splice(1);
                    
                    //Push the default values for the command
                    for(i of d)
                    {
                        l.push(i[1] ||'')
                    }
                    return l;
                }
            })
        }
        }
    
    </script>