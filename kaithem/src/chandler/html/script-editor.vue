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
                data-testid="close-event-inspector"
                popovertarget="blockInspectorEvent"
                popovertargetaction="hide">
                <i class="mdi mdi-close"></i>Close
              </button>
            </div>
          </header>

          <p>Event Trigger. Runs the actions when something happens.</p>

          <h4>Parameters</h4>
          <div class="stacked-form">
            <datalist id=" props.example_events">
              <option
                v-for="(v, _i) in props.example_events"
                v-bind:value="v[0]"
                v-bind:key="v[0]">
                {{ v[1] }}
              </option>
            </datalist>
            <label
              >Run on(type to search)
              <input
                :disabled="disabled"
                v-model="selectedBinding.event"
                list=" props.example_events"
                v-on:change="
                  selectedBinding.event = $event.target.value;
                  $nextTick(() => {
                    $emit('update:modelValue', rules);
                  });
                " />
            </label>
          </div>
          <h4>Delete</h4>
          <button
            :disabled="disabled"
            v-on:click="deleteBinding(selectedBinding)">
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
                data-testid="close-command-inspector"
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
            @update:modelValue="setCommandDefaults(selectedCommand)"
            v-on:change="
              selectedCommand.command = $event;
              setCommandDefaults(selectedCommand);
              $nextTick(() => {
                $emit('update:modelValue', rules);
              });
            "></combo-box>
          <div v-if="commands[selectedCommand.command]">
            <div class="stacked-form">
              <label
                v-for="(argMeta, i) in commands[selectedCommand.command].args"
                v-bind:key="i">
                {{ argMeta.name }}
                <combo-box
                  :disabled="disabled"
                  :testid="'command-arg-' + argMeta.name"
                  v-model="selectedCommand[argMeta.name]"
                  v-on:change="
                    rules[selectedBindingIndex].commands[
                      selectedCommandIndex
                    ][argMeta.name] = $event;
                    $emit('update:modelValue', rules);
                  "
                  :options="
                    getCompletions(selectedCommand, argMeta.name)
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
              rules[selectedBindingIndex].commands.splice(
                selectedCommandIndex,
                1
              );
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
                rules[selectedBindingIndex].commands,
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
              selectedCommandIndex <
              rules[selectedBindingIndex].commands.length - 1
            "
            v-on:click="
              swapArrayElements(
                rules[selectedBindingIndex].commands,
                selectedCommandIndex,
                selectedCommandIndex + 1
              );
              selectedCommandIndex += 1;
              $emit('update:modelValue', rules);
            ">
            Move Forward
          </button>
        </div>

        <div class="flex-row gaps col-9" data-testid="rules-box">
          <div
            v-for="(rule, rule_idx) in rules"
            class="w-sm-double card"
            data-testid="rule-box-row"
            :key="rule_idx">
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

                <button
                  :disabled="disabled"
                  v-on:click="moveCueRuleDown(rule_idx)">
                  Move down
                </button>
              </div>
            </header>

            <div class="flex-row gaps w-full padding nogaps">
              <div
                v-for="(action, action_idx) in rule.commands"
                data-testid="rule-command"
                :key="action_idx"
                style="display: flex"
                class="nogrow">
                <button
                  style="align-content: flex-start"
                  popovertarget="blockInspectorCommand"
                  v-bind:class="{
                    'action': 1,
                    'flex-row': 1,
                    'selected':
                      (selectedBinding == rule) & (selectedCommand == action),
                  }"
                  v-on:click="
                    selectedCommandIndex = action_idx;
                    selectedBindingIndex = rules.indexOf(rule);
                  ">
                  <div class="w-full h-min-content">
                    <b>{{ action.command }}</b>
                  </div>

                  <template v-for="(i, argName) of action" :key="i">
                    <template
                      v-if="argName != 'command' && i != '=_' && i != '=GROUP'">
                      <div class="nogrow h-min-content" style="margin: 2px">
                        {{ action[argName] }}
                      </div>
                    </template>
                  </template>

                  <template v-if="!(action.command in commands)">
                    <div
                      class="nogrow h-min-content warning"
                      style="margin: 2px">
                      Command <b>{{ action.command }}</b> not found
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
                    rule.commands.push({ command: 'pass' });
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
                commands: [{ command: 'goto', group: '=GROUP', cue: '' }],
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

<script setup>
import { computed, watchEffect, ref } from "vue";

import ComboBox from "../../vue/combo-box.vue";
const props = defineProps({
  modelValue: Object,
  commands: Object,
  disabled: Boolean,
  completers: Object,
  example_events: Array,
});

const emit = defineEmits(["update:modelValue"]);

let rules = props.modelValue;
let disabled = props.disabled;

watchEffect(() => {
  // `foo` transformed to `props.foo` by the compiler
  rules = props.modelValue;
  disabled = props.disabled;
});

let argcompleters = props.completers || {};

let selectedCommandIndex = ref(-1);
let selectedBindingIndex = ref(-1);

const selectedBinding = computed(() => {
  if (selectedBindingIndex.value == -1) {
    return 0;
  }
  return rules[selectedBindingIndex.value];
});

const selectedCommand = computed(() => {
  if (selectedBindingIndex.value == -1) {
    return 0;
  }
  if (selectedCommandIndex.value == -1) {
    return 0;
  }
  if (rules[selectedBindingIndex.value]) {
    const rule = rules[selectedBindingIndex.value];
    const actions = rule.commands || [];
    if (actions[selectedCommandIndex.value]) {
      return actions[selectedCommandIndex.value];
    }
  }
  return 0;
});

function getArgMetadata(commandName, argumentName) {
  if (commandName in props.commands) {
    return props.commands[commandName].args[argumentName];
  }
  return {};
}

function getCompletions(actionObject, argumentName) {
  const cmdName = actionObject.command;
  const cmdMeta = props.commands[cmdName];

  const argumentMetadata = getArgMetadata(cmdName, argumentName);

  if (!argumentMetadata) {
    return argcompleters["defaultExpressionCompleter"](actionObject);
  }

  if (argcompleters[cmdMeta.type]) {
    try {
      return argcompleters[cmdMeta.type](actionObject, argumentName);
    } catch (error) {
      console.log(error);
      return [];
    }
  }
  return argcompleters["defaultExpressionCompleter"](actionObject);
}

function moveCueRuleDown(index) {
  var rules = [...props.modelValue];

  if (index < rules.length - 1) {
    var t = rules[index + 1];
    rules[index + 1] = rules[index];
    rules[index] = t;
  }
  emit("update:modelValue", rules);
}

function swapArrayElements(array, indexA, indexB) {
  var temporary = array[indexA];
  array[indexA] = array[indexB];
  array[indexB] = temporary;
}

function getPossibleActions() {
  var l = [];
  for (var i in props.commands) {
    if (props.commands[i] == null) {
      console.log("Warning: Null entry for command info for" + i);
    } else {
      l.push([i, props.commands[i].doc || ""]);
    }
  }
  return l;
}

function deleteBinding(b) {
  if (confirm("Really delete binding?")) {
    removeElement(rules, b);
    emit("update:modelValue", rules);
  }
}
function removeElement(array, element) {
  var index = array.indexOf(element);
  if (index > -1) {
    array.splice(index, 1);
  } else {
    console.log("Element not found in array");
    alert("Element not found in array");
  }
}
function setCommandDefaults(action) {
  // For dict format actions, set defaults from command metadata
  const cmdName = action.command;
  let metadata = null;

  // Get description data
  if (cmdName in props.commands) {
    metadata = props.commands[cmdName];
  }

  // If we don't know this command, nothing to do
  if (!metadata) {
    return;
  }

  // Set default values for all args
  const arguments_ = metadata.args || [];
  for (const argumentMeta of arguments_) {
    if (!(argumentMeta.name in action)) {
      action[argumentMeta.name] = argumentMeta.default || "";
    }
  }
}
</script>
