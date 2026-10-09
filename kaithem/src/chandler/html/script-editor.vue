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
  height: 7rem;
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
          class="card paper margin col-3 card min-h-24rem w-full"
          style="width: 98%"
          popover
          id="blockInspectorEvent"
          ontoggle="globalThis.handleDialogState(event)"
          v-if="selectedCommandIndex == -1 && rules?.[selectedBindingIndex]"
        >
          <header>
            <div class="tool-bar">
              <h4>Event Inspector</h4>
              <button
                class="nogrow"
                type="button"
                data-testid="close-event-inspector"
                popovertarget="blockInspectorEvent"
                popovertargetaction="hide"
              >
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
                v-bind:key="v[0]"
              >
                {{ v[1] }}
              </option>
            </datalist>
            <label
              >Run on(type to search)
              <input
                :disabled="disabled"
                v-model="rules[selectedBindingIndex].event"
                list=" props.example_events"
                v-on:change="
                  rules[selectedBindingIndex].event = $event.target.value;
                  $emit('update:modelValue', rules);
                "
              />
            </label>
          </div>
          <h4>Delete</h4>
          <button
            :disabled="disabled"
            v-on:click="deleteBinding(rules[selectedBindingIndex])"
          >
            Remove binding and all actions
          </button>
        </div>

        <div
          class="card paper margin card col-3 min-h-24rem w-sm-full"
          popover
          ontoggle="globalThis.handleDialogState(event)"
          id="blockInspectorCommand"
          v-if="rules?.[selectedBindingIndex]?.commands?.[selectedCommandIndex]"
        >
          <header>
            <div class="tool-bar">
              <h4>Command Inspector</h4>
              <button
                class="nogrow"
                data-testid="close-command-inspector"
                type="button"
                popovertarget="blockInspectorCommand"
                popovertargetaction="hide"
              >
                <i class="mdi mdi-close"></i>Close
              </button>
            </div>
          </header>

          <label>Type
          <combo-box
            :disabled="disabled"
            v-model="rules[selectedBindingIndex].commands[selectedCommandIndex].command"
            v-bind:options="getPossibleActions()"
            :testid="'command-type'"
            v-on:change="
              rules[selectedBindingIndex].commands[
                selectedCommandIndex
              ].command = $event;
              setCommandDefaults(
                rules[selectedBindingIndex].commands[selectedCommandIndex]
              );
              $emit('update:modelValue', rules);
            "
          ></combo-box></label>
          <div v-if="commands?.[rules?.[selectedBindingIndex]?.commands?.[selectedCommandIndex]?.command]">
            <div class="stacked-form">
              <label
                v-for="(argMeta, i) in commands[rules[selectedBindingIndex].commands[selectedCommandIndex].command].args"
                v-bind:key="i"
              >
                {{ argMeta.name }}
                <combo-box
                  :disabled="disabled"
                  :testid="'command-arg-' + argMeta.name"
                  v-model="rules[selectedBindingIndex].commands[selectedCommandIndex][argMeta.name]"
                  v-on:change="
                    rules[selectedBindingIndex].commands[selectedCommandIndex][
                      argMeta.name
                    ] = $event;
                    $emit('update:modelValue', rules);
                  "
                  :options="getCompletions(rules[selectedBindingIndex].commands[selectedCommandIndex], argMeta.name)"
                ></combo-box>
              </label>
            </div>
            <h5>Docs</h5>

            <pre style="white-space: pre-wrap">{{
              commands[rules[selectedBindingIndex].commands[selectedCommandIndex].command].doc
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
            "
          >
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
            "
          >
            Move Back
          </button>
          <button
            :disabled="disabled"
            v-if="
              selectedCommandIndex <
              rules?.[selectedBindingIndex]?.commands?.length - 1
            "
            v-on:click="
              swapArrayElements(
                rules[selectedBindingIndex].commands,
                selectedCommandIndex,
                selectedCommandIndex + 1
              );
              selectedCommandIndex += 1;
              $emit('update:modelValue', rules);
            "
          >
            Move Forward
          </button>
        </div>

        <div class="flex-row gaps col-9" data-testid="rules-box">
          <div
            v-for="(rule, rule_idx) in rules"
            class="w-sm-double card"
            data-testid="rule-box-row"
            :key="rule_idx"
          >
            <header>
              <div class="tool-bar">
                <button
                  data-testid="rule-trigger"
                  popovertarget="blockInspectorEvent"
                  v-bind:class="{ highlight: rules?.[selectedBindingIndex] == rule }"
                  style="flex-grow: 50"
                  v-on:click="
                    selectedBindingIndex = parseInt(rule_idx);
                    selectedCommandIndex = -1;
                  "
                >
                  <b>On {{ rule.event }}</b>
                </button>

                <button
                  :disabled="disabled"
                  v-on:click="moveCueRuleDown(rule_idx)"
                >
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
                class="nogrow"
              >
                <button
                  style="align-content: flex-start"
                  popovertarget="blockInspectorCommand"
                  v-bind:class="{
                    action: 1,
                    'flex-row': 1,
                    selected:
                      (rules?.[selectedBindingIndex] == rule) && (rules?.[selectedBindingIndex]?.commands?.[selectedCommandIndex] == action),
                  }"
                  v-on:click="
                    selectedCommandIndex = parseInt(action_idx);
                    selectedBindingIndex = parseInt(rule_idx);
                  "
                >
                  <div class="w-full h-min-content">
                    <b>{{ action.command }}</b>
                  </div>

                  <template v-for="(i, argName) of action" :key="i">
                    <template
                      v-if="argName != 'command' && i != '=_' && i != '=GROUP'"
                    >
                      <div class="nogrow h-min-content" style="margin: 2px">
                        {{ action[argName] }}
                      </div>
                    </template>
                  </template>

                  <template v-if="!(action.command in commands)">
                    <div
                      class="nogrow h-min-content warning"
                      style="margin: 2px"
                    >
                      Command <b>{{ action.command }}</b> not found
                    </div>
                  </template>
                </button>
                <i
                  class="mdi mdi-arrow-right"
                  style="align-self: center; text-align: center"
                ></i>
              </div>
              <div style="align-self: stretch">
                <button
                  class="action"
                  style="align-self: stretch; flex-grow: 1"
                  :disabled="disabled"
                  v-on:click="
                    rule.commands.push({ command: 'pass' });
                    $emit('update:modelValue', rules);
                  "
                >
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
              rules?.push({
                event: 'cue.enter',
                commands: [{ command: 'continue_if', v: '=_' }],
              });
              $emit('update:modelValue', rules);
            "
          >
            <b>Add Rule</b>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {watchEffect, ref } from 'vue';

import ComboBox from '../../vue/combo-box.vue';
const props = defineProps({
  modelValue: Object,
  commands: Object,
  disabled: Boolean,
  completers: Object,
  example_events: Array,
});

const emit = defineEmits(['update:modelValue']);

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



function getArgMetadata(commandName, argumentName) {
  if (commandName in props.commands) {
    for (var i in props.commands[commandName].args) {
      if (props.commands[commandName].args[i].name == argumentName) {
        return props.commands[commandName].args[i];
      }
    }
  }
  return {};
}

function getCompletions(actionObject, argumentName) {
  const cmdName = actionObject.command;

  const argumentMetadata = getArgMetadata(cmdName, argumentName);

  if (!argumentMetadata) {
    return argcompleters['defaultExpressionCompleter'](actionObject);
  }

  if (argcompleters[argumentMetadata.type]) {
    try {
      return argcompleters[argumentMetadata.type](actionObject, argumentName);
    } catch (error) {
      console.log(error);
      return [];
    }
  }
  return argcompleters['defaultExpressionCompleter'](actionObject);
}

function moveCueRuleDown(index) {
  var rules = [...props.modelValue];

  if (index < rules.length - 1) {
    var t = rules[index + 1];
    rules[index + 1] = rules[index];
    rules[index] = t;
  }
  emit('update:modelValue', rules);
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
      console.log('Warning: Null entry for command info for' + i);
    } else {
      l.push([i, props.commands[i].doc || '']);
    }
  }
  return l;
}

function deleteBinding(b) {
  if (confirm('Really delete binding?')) {
    removeElement(rules, b);
    emit('update:modelValue', rules);
    selectedBindingIndex.value = -1;
  }
}
function removeElement(array, element) {
  var index = array.indexOf(element);
  if (index > -1) {
    array.splice(index, 1);
  } else {
    console.log('Element not found in array');
    alert('Element not found in array');
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
  // but still need cleanup old args
  if (!metadata) {
    metadata = { args: [] };
  }

  // Set default values for all args
  const arguments_ = metadata.args || [];
  for (const argumentMeta of arguments_) {
    if (!(argumentMeta.name in action)) {
      action[argumentMeta.name] = argumentMeta.default || '';
    }
  }

  // Remove any args that are not in the metadata
  for (const argName in action) {
    if (argName == 'command') {
      continue;
    }

    let found = false;
    for (const argumentMeta of arguments_) {
      if (argumentMeta.name == argName) {
        found = true;
        break;
      }
    }
    if (!found) {
      delete action[argName];
    }
  }
}
</script>
