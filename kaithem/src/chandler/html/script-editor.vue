<style scoped>
.event {
  border-style: solid;
  border-width: 1px;
  border-color: black;
  background-color: white;
  padding: 0.4em;
  font-weight: bold;
  align-self: stretch;
  border-radius: 1.5em;
}

.action {
  padding: 0.4em;
  align-self: stretch;
  max-width: 12em;
}

.action,
.event {
  height: 12em;
  min-width: 8rem;
}

.selected {
  border-width: 4px;
  border-color: var(--highlight-color);
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
        <div
          class="card paper margin col-3 card min-h-24rem w-sm-full"
          popover
          id="blockInspectorEvent"
          ontoggle="globalThis.handleDialogState(event)"
          v-if="selectedCommand == 0 && selectedBinding">
          <header>
            <div class="tool-bar">
              <h4>Event Inspector</h4>
              <button
                class="nogrow"
                type="button"
                popovertarget="blockInspectorEvent"
                popovertargetaction="hide">
                <i class="mdi mdi-close"></i>Close
              </button>
            </div>
          </header>

          <p>Event Trigger. Runs the actions when something happens.</p>

          <h4>Parameters</h4>
          <div class="stacked-form">
            <datalist id="example_events">
              <option
                v-for="(v, _i) in example_events"
                v-bind:value="v[0]"
                v-bind:key="v[0]">{{ v[1] }}</option>
            </datalist>
            <label
              >Run on(type to search)
              <input
                :disabled="disabled"
                v-model="selectedBinding[0]"
                list="example_events"
                v-on:change="$emit('update:modelValue', rules)"
                />
            </label>
          </div>
          <h4>Delete</h4>
          <button
            :disabled="disabled"
            v-on:click="
              deleteBinding(selectedBinding);
            ">
            Remove binding and all actions
          </button>
        </div>

        <div
          class="card paper margin card col-3 min-h-24rem w-sm-full"
          popover
          ontoggle="globalThis.handleDialogState(event)"
          id="blockInspectorCommand"
          v-if="selectedCommand">
          <header>
            <div class="tool-bar">
              <h4>Command Inspector</h4>
              <button
                class="nogrow"
                type="button"
                popovertarget="blockInspectorCommand"
                popovertargetaction="hide">
                <i class="mdi mdi-close"></i>Close
              </button>
            </div>
          </header>

          Type
          <combo-box
            :disabled="disabled"
            v-model="selectedCommand[0]"
            v-bind:options="getPossibleActions()"
            v-bind:pinned="getSpecialActions()"
            @update:modelValue="setCommandDefaults(selectedCommand)"
            v-on:change="
              setCommandDefaults(selectedCommand);
              $emit('update:modelValue', rules);
            "></combo-box>
          <h4>Config</h4>
          <div v-if="selectedCommand[0] == 'set'">
            Set a variable named
            <combo-box
              :disabled="disabled"
              v-model="selectedCommand[1]"
              v-bind:pinned="pinnedvars"
              v-on:change="$emit('update:modelValue', rules)"></combo-box>
            <br />to<br />
            <combo-box
              v-model="selectedCommand[2]"
              v-on:change="$emit('update:modelValue', rules)"></combo-box
            ><br />
            and always return True.
          </div>

          <div v-if="selectedCommand[0] == 'pass'">
            Do nothing and return True.
          </div>

          <div v-if="selectedCommand[0] == 'maybe'">
            Continue action with :<input
              :disabled="disabled"
              v-model="selectedCommand[1]"
              v-on:change="$emit('update:modelValue', rules)" />% chance <br />
            otherwise return None and stop the action.
          </div>

          <div
            v-if="
              !(selectedCommand[0] in specialCommands) &&
              commands[selectedCommand[0]]
            ">
            <div class="stacked-form">
              <label
                v-for="i in commands[selectedCommand[0]].args.keys()"
                v-bind:key="i">
                {{ commands[selectedCommand[0]].args[i][0] }}
                <combo-box
                  :disabled="disabled"
                  :testid="'command-arg-'+commands[selectedCommand[0]].args[i][0] "
                  v-model="selectedCommand[i + 1]"
                  v-on:change="$emit('update:modelValue', rules)"
                  :options="
                    getCompletions(
                      selectedCommand,
                      commands[selectedCommand[0]].args[i][0]
                    )
                  "></combo-box>
              </label>
            </div>
            <h5>Docs</h5>

            <pre style="white-space: pre-wrap">{{
              commands[selectedCommand[0]].doc
            }}</pre>
          </div>
          <button
            v-on:click="
              rules[selectedBindingIndex][1].splice(selectedCommandIndex, 1);
              selectedCommandIndex -= 1;
              $emit('update:modelValue', rules);
            ">
            Delete
          </button>
          <button
            v-if="selectedCommandIndex > 0"
            :disabled="disabled"
            v-on:click="
              swapArrayElements(
                rules[selectedBindingIndex][1],
                selectedCommandIndex,
                selectedCommandIndex - 1
              );
              selectedCommandIndex -= 1;
              $emit('update:modelValue', rules);
            ">
            Move Back
          </button>
          <button
            :disabled="disabled"
            v-if="
              selectedCommandIndex < rules[selectedBindingIndex][1].length - 1
            "
            v-on:click="
              swapArrayElements(
                rules[selectedBindingIndex][1],
                selectedCommandIndex,
                selectedCommandIndex + 1
              );
              selectedCommandIndex += 1;
              $emit('update:modelValue', rules);
            ">
            Move Forward
          </button>
        </div>

        <div class="flex-row gaps col-9"
        data-testid="rules-box"
        >
          <div v-for="(rule, rule_idx) in rules" class="w-sm-double card"
          data-testid="rule-box-row"
          :key="rule_idx"
          >
            <header>
              <div class="tool-bar">
                <button
                  data-testid="rule-trigger"
                  popovertarget="blockInspectorEvent"
                  v-bind:class="{ highlight: selectedBinding == rule }"
                  style="flex-grow: 50"
                  v-on:click="
                    selectedBindingIndex = rules.indexOf(rule);
                    selectedCommandIndex = -1;
                  ">
                  <b>On {{ rule[0] }}</b>
                </button>

                <button :disabled="disabled" v-on:click="moveCueRuleDown(rule_idx)">
                  Move down
                </button>
              </div>
            </header>

            <div class="flex-row gaps w-full padding nogaps">
              <div v-for="(command,command_idx) in rule[1]" 
              data-testid="rule-command"
              :key="command_idx"
              style="display: flex" class="nogrow">
                <button
                  style="align-content: flex-start"
                  popovertarget="blockInspectorCommand"
                  v-bind:class="{
                    'action': 1,
                    'flex-row': 1,
                    'selected': (selectedBinding == rule) & (selectedCommand == command),
                  }"
                  v-on:click="
                    selectedCommandIndex = command_idx;
                    selectedBindingIndex = rules.indexOf(rule);
                  ">
                  <template
                    v-if="commands[command[0]]">
                    <div class="w-full h-min-content">
                      <b>{{ command[0] }}</b>
                    </div>
                    <div
                      class="nogrow h-min-content"
                      style="margin: 2px"
                      v-for="i in commands[command[0]].args.keys()"
                      :key="i"
                      >
                      {{ command[i + 1] }}
                    </div>
                  </template>

                  <template v-if="!(command[0] in commands)">
                    <div
                      class="nogrow h-min-content warning"
                      style="margin: 2px"
                      v-for="k in command"
                      :key="k"
                      >
                      {{ k }}
                    </div>
                  </template>
                </button>
                <i
                  class="mdi mdi-arrow-right"
                  style="align-self: center; text-align: center"></i>
              </div>
              <div style="align-self: stretch">
                <button
                  class="action"
                  style="align-self: stretch; flex-grow: 1"
                  :disabled="disabled"
                  v-on:click="
                    rule[1].push(['pass']);
                    $emit('update:modelValue', rules);
                  ">
                  <b>Add Action</b>
                </button>
              </div>
            </div>
          </div>
          <button
            style="width: 95%; margin-top: 0.5em"
            :disabled="disabled"
            title="Add a rule that the group should do something when an event fires"
            v-on:click="
              rules.push(['cue.enter', [['goto', '=GROUP', '']]]);
              $emit('update:modelValue', rules);
            ">
            <b>Add Rule</b>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  props: [
    "modelValue",
    "commands",
    "disabled",
    "inspector",
    "completers",
    "example_events",
  ],
  components: {
    "combo-box": globalThis.httpVueLoader("/static/vue/ComboBox.vue"),
  },
  watch: {
    modelValue: function (newValue) {
      this.rules = newValue;
    },
    completers: function (newValue) {
      this.argcompleters = newValue || {};
    },
  },

  computed: {
    selectedBinding: function () {
      if (this.selectedBindingIndex == -1) {
        return 0;
      }
      return this.rules[this.selectedBindingIndex];
    },
    selectedCommand: function () {
      if (this.selectedBindingIndex == -1) {
        return 0;
      }
      if (this.selectedCommandIndex == -1) {
        return 0;
      }
      if (this.rules[this.selectedBindingIndex]) {
        return this.rules[this.selectedBindingIndex][1][
          this.selectedCommandIndex
        ];
      }
      return 0;
    },
  },
  data: function () {
    return {
      pinnedvars: [["_", "Output of the previous action"]],
      getCompletions: function (fullCommand, argument) {
        var t = this.commands[fullCommand[0]].completionTags;
        if (t == undefined) {
          try {
            return this.argcompleters["defaultExpressionCompleter"](
              fullCommand
            );
          } catch {
            return [];
          }
        }
        t = t[argument];
        var c = this.argcompleters[t];

        try {
          if (c == undefined) {
            return this.argcompleters["defaultExpressionCompleter"](
              fullCommand
            );
          }

          return c(fullCommand);
        } catch {
          return [];
        }
      },

      moveCueRuleDown: function (index) {
        var rules = [...this.modelValue];

        if (index < rules.length - 1) {
          var t = rules[index + 1];
          rules[index + 1] = rules[index];
          rules[index] = t;
        }
        this.$emit("update:modelValue", rules);
      },

      swapArrayElements: function (array, indexA, indexB) {
        var temporary = array[indexA];
        array[indexA] = array[indexB];
        array[indexB] = temporary;
      },
      rules: this.modelValue,
      argcompleters: this.completers || {},
      getPossibleActions: function () {
        var l = [];
        for (var i in this.commands) {
          if (this.commands[i] == null) {
            console.log("Warning: Null entry for command info for" + i);
          } else {
            //Just use the special version if possible
            if (!(i in this.specialCommands)) {
              l.push([i, this.commands[i].doc || ""]);
            }
          }
        }
        return l;
      },

      getSpecialActions: function () {
        var l = [];
        for (var i in this.specialCommands) {
          //Prefer the special version
          l.push([i, this.specialCommands[i].description]);
        }

        return l;
      },

      selectedCommandIndex: -1,
      selectedBindingIndex: -1,

      //Stuff we have built in HTML templating for
      specialCommands: {
        set: {
          args: [
            ["var", ""],
            ["val", ""],
          ],
          description: "Sets a variable",
        },
        pass: {
          args: [],
          description: "",
        },
        maybe: {
          args: [["chance", "50"]],
          description: "",
        },
      },
      deleteBinding: function (b) {
        if (confirm("really delete binding?")) {
          console.log("jhgf")
          this.removeElement(this.rules, b);
          this.$emit('update:modelValue', this.rules);
        }
      },
      removeElement: function (array, element) {
        var index = array.indexOf(element);
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
          d = this.specialCommands[l[0]]["args"];
        }

        //Get description data for that type
        if (l[0] in this.commands) {
          d = this.commands[l[0]]["args"];
        }
        //Get rid of everything except the command name
        l.splice(1);
        //Not a command we know anything about to set defaults
        if (d == 0) {
          return;
        }

        //Push the default values for the command
        for (var i of d) {
          l.push(i[1] || "");
        }
        return l;
      },
    };
  },
};
</script>
