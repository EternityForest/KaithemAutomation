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
                v-model="selectedBinding.event"
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
            v-model="selectedCommand.command"
            v-bind:options="getPossibleActions()"
            v-bind:pinned="getSpecialActions()"
            @update:modelValue="setCommandDefaults(selectedCommand)"
            v-on:change="
              setCommandDefaults(selectedCommand);
              $emit('update:modelValue', rules);
            "></combo-box>
          <h4>Config</h4>
          <div v-if="selectedCommand.command == 'set'">
            Set a variable named
            <combo-box
              :disabled="disabled"
              v-model="selectedCommand.variable"
              v-bind:pinned="pinnedvars"
              v-on:change="$emit('update:modelValue', rules)"></combo-box>
            <br />to<br />
            <combo-box
              v-model="selectedCommand.value"
              v-on:change="$emit('update:modelValue', rules)"></combo-box
            ><br />
            and always return True.
          </div>

          <div v-if="selectedCommand.command == 'pass'">
            Do nothing and return True.
          </div>

          <div v-if="selectedCommand.command == 'maybe'">
            Continue action with :<input
              :disabled="disabled"
              v-model="selectedCommand.chance"
              v-on:change="$emit('update:modelValue', rules)" />% chance <br />
            otherwise return None and stop the action.
          </div>

          <div
            v-if="
              !(selectedCommand.command in specialCommands) &&
              commands[selectedCommand.command]
            ">
            <div class="stacked-form">
              <label
                v-for="(argMeta, i) in commands[selectedCommand.command].args"
                v-bind:key="i">
                {{ argMeta.name }}
                <combo-box
                  :disabled="disabled"
                  :testid="'command-arg-' + argMeta.name"
                  v-model="selectedCommand[argMeta.name]"
                  v-on:change="$emit('update:modelValue', rules)"
                  :options="
                    getCompletions(
                      selectedCommand,
                      argMeta.name
                    )
                  "></combo-box>
              </label>
            </div>
            <h5>Docs</h5>

            <pre style="white-space: pre-wrap">{{
              commands[selectedCommand.command].doc
            }}</pre>
          </div>
          <button
            v-on:click="
              rules[selectedBindingIndex].actions.splice(selectedCommandIndex, 1);
              selectedCommandIndex -= 1;
              $emit('update:modelValue', rules);
            ">
            Delete Command
          </button>
          <button
            v-if="selectedCommandIndex > 0"
            :disabled="disabled"
            v-on:click="
              swapArrayElements(
                rules[selectedBindingIndex].actions,
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
              selectedCommandIndex < rules[selectedBindingIndex].actions.length - 1
            "
            v-on:click="
              swapArrayElements(
                rules[selectedBindingIndex].actions,
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
                  <b>On {{ rule.event }}</b>
                </button>

                <button :disabled="disabled" v-on:click="moveCueRuleDown(rule_idx)">
                  Move down
                </button>
              </div>
            </header>

            <div class="flex-row gaps w-full padding nogaps">
              <div v-for="(action,action_idx) in rule.actions"
              data-testid="rule-command"
              :key="action_idx"
              style="display: flex" class="nogrow">
                <button
                  style="align-content: flex-start"
                  popovertarget="blockInspectorCommand"
                  v-bind:class="{
                    'action': 1,
                    'flex-row': 1,
                    'selected': (selectedBinding == rule) & (selectedCommand == action),
                  }"
                  v-on:click="
                    selectedCommandIndex = action_idx;
                    selectedBindingIndex = rules.indexOf(rule);
                  ">
                  <template
                    v-if="commands[action.command]">
                    <div class="w-full h-min-content">
                      <b>{{ action.command }}</b>
                    </div>
                    <div
                      class="nogrow h-min-content"
                      style="margin: 2px"
                      v-for="(argMeta, i) in commands[action.command]"
                      :key="i"
                      >
                      {{ action[argMeta.name] }}
                    </div>
                  </template>

                  <template v-if="!(action.command in commands)">
                    <div
                      class="nogrow h-min-content warning"
                      style="margin: 2px"
                      >
                      {{ action.command }}
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
                    rule.actions.push({command: 'pass'});
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
              rules.push({
                event: 'cue.enter',
                actions: [{command: 'goto', group: '=GROUP', cue: ''}]
              });
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
        const rule = this.rules[this.selectedBindingIndex];
        const actions = rule.actions || [];
        if (actions[this.selectedCommandIndex]) {
          return actions[this.selectedCommandIndex];
        }
      }
      return 0;
    },
  },
  data: function () {
    return {
      pinnedvars: [["_", "Output of the previous action"]],
      getCompletions: function (actionObj, argumentName) {
        const cmdName = actionObj.command;
        const cmdMeta = this.commands[cmdName];
        if (!cmdMeta || !cmdMeta.completionTags) {
          try {
            return this.argcompleters["defaultExpressionCompleter"](actionObj);
          } catch {
            return [];
          }
        }

        const completionTag = cmdMeta.completionTags[argumentName];
        const completer = this.argcompleters[completionTag];

        try {
          if (!completer) {
            return this.argcompleters["defaultExpressionCompleter"](actionObj);
          }
          return completer(actionObj);
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
            { name: "variable", type: "str", default: "" },
            { name: "value", type: "str", default: "" },
          ],
          description: "Sets a variable",
        },
        pass: {
          args: [],
          description: "Do nothing and return True",
        },
        maybe: {
          args: [{ name: "chance", type: "float", default: "50" }],
          description: "Continue action with chance % probability",
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
      setCommandDefaults: function (action) {
        // For dict format actions, set defaults from command metadata
        const cmdName = action.command;
        let metadata = null;

        // Get description data
        if (cmdName in this.specialCommands) {
          metadata = this.specialCommands[cmdName];
        } else if (cmdName in this.commands) {
          metadata = this.commands[cmdName];
        }

        // If we don't know this command, nothing to do
        if (!metadata) {
          return;
        }

        // Set default values for all args
        const args = metadata.args || [];
        for (const argMeta of args) {
          if (!(argMeta.name in action)) {
            action[argMeta.name] = argMeta.default || "";
          }
        }
      }
    };
  },
};
</script>
