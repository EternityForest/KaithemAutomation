<template>
  <div v-cloak>
    <div
      v-if="iframeDialog"
      class="card paper flex-col"
      style="
        background: var(--alt-control-bg);
        position: fixed;
        width: 90vw;
        max-width: 48rem;
        height: 90vh;
        top: 5vh;
        left: 5vw;
        z-index: 100;
      ">
      <header>
        <button @click="iframeDialog = null" class="w-full nogrow">
          <i class="mdi mdi-close"></i>Close
        </button>
      </header>
      <iframe :src="iframeDialog"></iframe>
    </div>

    <section class="window">
      <header>
        <datalist id="effectTypes">
          <option value="fader">Fader</option>
          <option value="3beq">3-Band EQ</option>
        </datalist>

        <datalist id="inports">
          <option v-for="i in sortedConnectables(inports)" :key="i">
            {{ i }}
          </option>
        </datalist>

        <datalist id="outports">
          <option v-for="i in sortedConnectables(outports)" :key="i">
            {{ i }}
          </option>
          <option>{{ recorderPortName }}</option>
        </datalist>

        <datalist id="presets">
          <option v-for="i in presets" :key="i" :value="i"></option>
          <option value="default"></option>
        </datalist>

        <div class="tool-bar">
          <button
            :class="{ bold: activePane === 'mixer' }"
            @click="activePane = 'mixer'">
            Mixer ({{ boardResource }})
          </button>
          <button
            :class="{ bold: activePane === 'presets' }"
            @click="activePane = 'presets'">
            Presets/Defaults
          </button>
          <button
            :class="{ bold: activePane === 'status' }"
            @click="activePane = 'status'">
            Status
          </button>
          <button @click="showLabels = !showLabels">Labels</button>

          <button @click="showAddEffect = true" data-testid="show-effects-menu">
            Show Effects Menu
          </button>
          <p>Preset:</p>
          <input
            list="presets"
            v-model="loadedPreset"
            placeholder="Preset name" />
          <button @click="confirmSavePreset(loadedPreset)">Save</button>
        </div>
      </header>

      <div v-if="activePane === 'status'">
        <h3>Audio ports</h3>
        <div class="flex-row gaps margin">
          <section class="card w-sm-full">
            <header>
              <h4>Inputs(Sources)</h4>
            </header>
            <table>
              <tr v-for="(v, i) in outports" :key="i">
                <td>{{ i }}</td>
              </tr>
            </table>
          </section>

          <section class="card w-sm-full">
            <header>
              <h4>Outputs(Sinks)</h4>
            </header>
            <table>
              <tr v-for="(v, i) in inports" :key="i">
                <td>{{ i }}</td>
              </tr>
            </table>
          </section>
        </div>

        <h3>MIDI ports</h3>
        <div class="flex-row gaps margin">
          <section class="card">
            <header>
              <h4>Outputs(Sinks)</h4>
            </header>
            <table>
              <tr v-for="(v, i) in midioutports" :key="i">
                <td>{{ i }}</td>
              </tr>
            </table>
          </section>
          <section class="card">
            <header>
              <h4>Inputs(Sources)</h4>
            </header>
            <table>
              <tr v-for="(v, i) in midiinports" :key="i">
                <td>{{ i }}</td>
              </tr>
            </table>
          </section>
        </div>
      </div>

      <div v-if="activePane === 'presets'">
        <h2>Presets</h2>
        <details class="help">
          <summary><i class="mdi mdi-help-circle-outline"></i></summary>
          Presets let you load and save the entire state of the mixing board.
          When kaithem boots, the preset named "default" will be loaded if it
          exists. Presets are saved immediately to vardir/system.mixer/presets
        </details>

        <table border="1">
          <tr>
            <th>Name</th>
            <th>Actions</th>
          </tr>
          <tr v-for="i in presets" :key="i">
            <td>{{ i }}</td>
            <td>
              <button @click="confirmLoadPreset(i)">Load</button>
            </td>
            <td>
              <button @click="confirmDeletePreset(i)">Delete</button>
            </td>
          </tr>

          <tr>
            <td>
              <input
                list="presets"
                v-model="newpresetname"
                placeholder="New Preset" />
            </td>
            <td>
              <button @click="createPreset(newpresetname)">Save</button>
            </td>
            <td></td>
          </tr>
        </table>
      </div>

      <div v-if="!ui_ready">
        <h3>Loading Mixer Channels</h3>
        <p>This may take a while if kaithem has just booted up.</p>
      </div>

      <div class="flex" v-if="activePane === 'mixer' && ui_ready">
        <article
          v-for="(channel, channelname) in channels"
          :key="channelname"
          class="channel window flex-col margin w-sm-full"
          :data-testid="'channel-box-' + channelname">
          <header>
            <div v-if="channel.type === 'audio' || !channel.type">
              <div></div>
              <div class="menubar tool-bar">
                <h3 style="display: inline-block">
                  {{ channelname }}({{ channel.channels }})
                </h3>
                <p
                  :class="{
                    error: channelStatus[channelname] !== 'running',
                    success: channelStatus[channelname] === 'running',
                  }">
                  <small data-testid="channel-status">{{
                    channelStatus[channelname]
                  }}</small>
                </p>
                <button data-testid="ding-button" @click="ding(channelname)">
                  <i class="mdi mdi-bell"></i>
                </button>
                <button @click="api.send(['refreshChannel', channelname])">
                  <i class="mdi mdi-refresh"></i>
                </button>
                <button
                  data-testid="delete-button"
                  @click="confirmDelete(channelname)">
                  <i class="mdi mdi-trash-can"></i>
                </button>
              </div>
            </div>
          </header>

          <div v-if="showLabels">
            <label>
              Image file(Relative to media/ in this module
              <input
                @change="
                  api.send([
                    'set_label_image',
                    channelname,
                    ($event.target as HTMLInputElement).value,
                  ])
                "
                v-model="channel.label_image"
                placeholder="Label" />
              <button @click="iframeDialog = getExcalidrawLink(channelname)">
                <i class="mdi mdi-pencil"></i>Draw
              </button>
            </label>
          </div>

          <details>
            <summary>Setup</summary>

            <div class="tool-bar">
              <label>
                In:<input
                  v-model="channel.input"
                  list="outports"
                  data-testid="channel-input"
                  @change="
                    setInput(
                      channelname,
                      ($event.target as HTMLInputElement).value
                    )
                  " />
              </label>
            </div>

            <div
              class="chain scroll h-24rem noselect"
              data-testid="effect-chain">
              <div
                v-for="(effect, index) in channel.effects"
                :key="effect.id || index"
                class="effect"
                :data-testid="'effect-box-' + effect.type">
                <details class="undecorated">
                  <summary data-testid="effect-title-id">
                    <div class="menubar tool-bar inline" style="width: 85%">
                      <p :title="effect.id">
                        <b>{{ effect.displayType }}</b>
                      </p>
                      <button
                        data-testid="move-effect-up-button"
                        @click="moveEffectUp(channelname, index)">
                        <span class="mdi mdi-arrow-up"></span>
                      </button>
                      <button @click="moveEffectDown(channelname, index)">
                        <span class="mdi mdi-arrow-down"></span>
                      </button>
                      <button
                        data-testid="delete-effect-button"
                        v-if="effect.type !== 'fader'"
                        @click="deleteEffect(channelname, index)">
                        <span class="mdi mdi-trash-can"></span>
                      </button>
                    </div>
                  </summary>

                  <table class="col-12 h-center" border="1">
                    <tr
                      v-for="param in sortedParameters(effect.params)"
                      :key="param.name"
                      class="param"
                      :data-testid="'param-row-' + param.name">
                      <template v-if="param.type === 'float'">
                        <td>{{ param.displayName }}</td>
                        <td>
                          <SmoothRange
                            style="width: 95%"
                            v-model.number="param.value"
                            :min="param.min"
                            :max="param.max"
                            :step="param.step"
                            @input="
                              setParameter(
                                channelname,
                                effect.id,
                                param.name,
                                parseFloat(
                                  ($event.target as HTMLInputElement).value
                                )
                              )
                            " />
                        </td>

                        <td data-testid="param-value" class="num-param-value">
                          {{ param.value }}
                        </td>
                      </template>

                      <template v-if="param.type === 'int'">
                        <td>{{ param.displayName }}</td>
                        <td>
                          <SmoothRange
                            style="width: 95%"
                            v-model.number="param.value"
                            :min="param.min"
                            :max="param.max"
                            :step="param.step"
                            @input="
                              setParameter(
                                channelname,
                                effect.id,
                                param.name,
                                parseInt(
                                  ($event.target as HTMLInputElement).value
                                )
                              )
                            " />
                        </td>

                        <td class="num-param-value">{{ param.value }}</td>
                      </template>

                      <template v-if="param.type === 'string.int'">
                        <td>{{ param.displayName }}</td>
                        <td>
                          <input
                            type="number"
                            style="width: 95%"
                            v-model.number="param.value"
                            :min="param.min"
                            :max="param.max"
                            :step="param.step"
                            @change="
                              setParameter(
                                channelname,
                                effect.id,
                                param.name,
                                parseInt(
                                  ($event.target as HTMLInputElement).value
                                )
                              )
                            " />
                        </td>

                        <td class="num-param-value">{{ param.value }}</td>
                      </template>

                      <template v-if="param.type === 'bool'">
                        <td>{{ param.displayName }}</td>
                        <td>
                          <input
                            type="checkbox"
                            v-model="param.value"
                            @input="
                              setParameter(
                                channelname,
                                effect.id,
                                param.name,
                                ($event.target as HTMLInputElement).checked
                              )
                            " />
                        </td>
                        <td>{{ param.value }}</td>
                      </template>

                      <template v-if="param.type === 'JackInput'">
                        <td>{{ param.displayName }}</td>
                        <td>
                          <input
                            list="inports"
                            v-model="param.value"
                            @change="
                              setParameter(
                                channelname,
                                effect.id,
                                param.name,
                                ($event.target as HTMLInputElement).value
                              )
                            " />
                        </td>
                        <td>{{ param.value }}</td>
                      </template>

                      <template v-if="param.type === 'string'">
                        <td>{{ param.displayName }}</td>
                        <td>
                          <input
                            v-model="param.value"
                            @change="
                              setParameter(
                                channelname,
                                effect.id,
                                param.name,
                                ($event.target as HTMLInputElement).value
                              )
                            " />
                        </td>
                        <td></td>
                      </template>

                      <template v-if="param.type === 'enum'">
                        <td>{{ param.displayName }}</td>
                        <td>
                          <select
                            v-model="param.value"
                            @input="
                              setParameter(
                                channelname,
                                effect.id,
                                param.name,
                                ($event.target as HTMLSelectElement).value
                              )
                            ">
                            <option
                              v-for="i of param.options"
                              :key="i[1]"
                              :value="i[1]">
                              {{ i[0] }}
                            </option>
                          </select>
                        </td>
                        <td></td>
                      </template>
                    </tr>
                  </table>
                </details>
              </div>

              <div
                v-if="showAddEffect"
                class="effect"
                data-testid="effects-menu">
                <h3>
                  Add Effect<button @click="showAddEffect = false">Hide</button>
                </h3>
                <div class="tool-bar">
                  <input v-model="fxSearch" placeholder="Search" />
                  <button @click="fxSearch = ''">
                    <i class="mdi mdi-backspace"></i>
                  </button>
                </div>
                <div style="height: 12em; overflow: scroll">
                  <template v-for="i in effectTypes" :key="i.type">
                    <div
                      v-if="
                        canUseEffect(i, channel.channels) &&
                        (i.displayType + i.help)
                          .toLowerCase()
                          .includes(fxSearch)
                      ">
                      <h4>{{ i.displayType }}</h4>
                      <p>{{ i.help }}</p>
                      <button
                        :data-testid="'add-effect-' + i.type"
                        @click="api.send(['addEffect', channelname, i.type])">
                        Add
                      </button>
                    </div>
                  </template>
                </div>
              </div>
            </div>
            <div class="tool-bar">
              <p>Connect output:</p>
              <input
                v-model="channel.output"
                list="inports"
                @change="
                  setOutput(
                    channelname,
                    ($event.target as HTMLInputElement).value
                  )
                "
                data-testid="channel-output"
                title="The output of this channel will be automatically connected to this port" />
            </div>

            <div class="tool-bar">
              <p>FBX Threshold:</p>
              <input
                class="w-4rem"
                type="number"
                v-model="channel.soundFuse"
                title="Steady or increasing values above this will result in the volume being automatically lowered."
                @change="
                  setFuse(
                    channelname,
                    ($event.target as HTMLInputElement).value
                  )
                " />
              <p>dB</p>
            </div>
          </details>

          <img
            v-if="channel.label_image"
            class="w-full"
            :src="`/settings/mixer/${boardname}/${channelname}/image?ts=${channel.labelImageTimestamp}`" />

          <footer class="padding noselect">
            <p>{{ channelname }} Level:</p>
            <div class="tool-bar">
              <SmoothRange
                v-model="channel.fader"
                data-testid="channel-fader"
                @input="
                  setFader(
                    channelname,
                    parseFloat(($event.target as HTMLInputElement).value)
                  )
                "
                :step="0.5"
                :min="-60"
                :max="20"
                :title="channel.fader" />

              <button
                @click="setMute(channelname, !channel.mute)"
                title="Mute channel">
                <i
                  v-if="channel.mute"
                  class="mdi mdi-volume-mute"
                  style="color: red; background-color: black"></i>
                <i v-if="!channel.mute" class="mdi mdi-volume-mute"></i>
              </button>
            </div>

            <div class="tool-bar">
              <meter
                min="-70"
                max="10"
                high="-5"
                data-testid="channel-level-meter"
                :value="channel.level"></meter>
              <p style="width: 5em" data-testid="channel-level-value">
                {{ channel.level }}db
              </p>
            </div>
          </footer>
        </article>

        <div class="flex-col gaps inline w-sm-full">
          <article class="channel window h-12rem flex-col margin w-sm-full">
            <header>
              <div
                class="decorative-image-h-bar decorative-image"
                style="min-height: 3em; margin: auto"></div>
              <h3>Mixer Controls</h3>
            </header>
            <div class="grow"></div>
            <h4>New Channel</h4>
            <div class="tool-bar">
              <input
                v-model="newchannelname"
                style="max-width: 8em"
                data-testid="new-channel-name" />
              <button
                data-testid="add-mono-channel"
                @click="api.send(['addChannel', newchannelname, 1])">
                Add Mono
              </button>
              <button
                data-testid="add-stereo-channel"
                @click="api.send(['addChannel', newchannelname, 2])">
                Add Stereo
              </button>
            </div>
            <footer></footer>
          </article>

          <article class="channel window margin w-sm-full">
            <header>
              <h3>Recorder ({{ recordStatus }})</h3>
            </header>
            <details class="help">
              <summary><i class="mdi mdi-help-circle-outline"></i></summary>
              Route your audio to the input(Named {{ recorderPortName }}) to use
              this.

              <br />
              Files in
              <a
                href="/settings/files/${os.path.join(directories.vardir,'recordings','mixer')|u}">
                VARDIR/recordings/mixer
              </a>
            </details>
            <div class="tool-bar margin">
              <p>Channels:</p>
              <input
                aria-label="Channels"
                type="number"
                v-model="recordChannels"
                style="max-width: 3em" />
              <p>File Prefix:</p>
              <input v-model="recordName" size="1" />
            </div>
            <div class="tool-bar margin">
              <button @click="api.send(['record', recordName, recordChannels])">
                Start
              </button>
              <button @click="api.send(['stopRecord'])">Stop</button>
            </div>
            <footer></footer>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import SmoothRange from "./components/smooth-range.vue";

// Props from parent (passed from index.ts)
const properties = defineProps<{
  boardname: string;
  boardApiUuid: string;
  globalApiUuid: string;
  boardResource: string;
  boardModule: string;
}>();

// Global API widget reference
let api: any;
let gapi: any;

// Reactive state
const fxSearch = ref("");
const ui_ready = ref(false);
const inports = ref<Record<string, Record<string, boolean | string | number>>>(
  {}
);
const outports = ref<Record<string, Record<string, boolean | string | number>>>(
  {}
);
const channels = ref<Record<string, Record<string, any>>>({});
const newchannelname = ref("");
const newpresetname = ref("");
const activePane = ref("mixer");
const effectTypes = ref<Record<string, any>>({});
const presets = ref<string[]>([]);
const showAddEffect = ref(false);
const loadedPreset = ref("");
const midiinports = ref<Record<string, string>>({});
const midioutports = ref<Record<string, string>>({});
const recorderPortName = ref(
  properties.boardname.replace(":", "_").replace("/", "_")
);
const recordName = ref(
  properties.boardname.replace(":", "_").replace("/", "_") + "_"
);
const recordChannels = ref(2);
const recordStatus = ref("");
const channelStatus = ref<Record<string, string>>({});
const showLabels = ref(false);
const iframeDialog = ref<string | null>(null);

// Helper function to compare parameters for sorting
function compareParameters(
  a: Record<string, number | string>,
  b: Record<string, number | string>
) {
  if (a.sort > b.sort) return 1;
  if (b.sort < a.sort) return -1;
  if (a.displayName > b.displayName) return 1;
  if (b.displayName < a.displayName) return -1;
  return 0;
}

// Sort parameters by sort key and display name
function sortedParameters(pl: Record<string, any>) {
  const l = [];
  for (const i in pl) {
    pl[i].name = i;
    l.push(pl[i]);
  }
  l.sort(compareParameters);
  return l;
}

// Get Excalidraw edit link
function getExcalidrawLink(channel: string) {
  return (
    "/excalidraw-plugin/edit?module=" +
    encodeURIComponent(properties.boardname.split(":")[0]) +
    "&resource=" +
    encodeURIComponent(
      "media/mixers/sketches/channel_" +
        properties.boardname.split(":")[1] +
        ".excalidraw.png"
    ) +
    "&callback=" +
    encodeURIComponent(
      `/settings/mixer/${properties.boardname}/${channel}/set_channel_img`
    ) +
    "&ratio_guide=16_9"
  );
}

// Test audio output
function ding(c: string) {
  api.send(["test", c + "_in"]);
}

// Confirm and delete channel
function confirmDelete(c: string) {
  if (globalThis.confirm("Do you really want to delete this channel?")) {
    api.send(["rmChannel", c]);
  }
}

// Confirm and delete preset
function confirmDeletePreset(c: string) {
  if (globalThis.confirm("Do you really want to delete this preset?")) {
    api.send(["deletePreset", c]);
  }
}

// Confirm and load preset
function confirmLoadPreset(c: string) {
  if (globalThis.confirm("Do you really want to load this preset?")) {
    api.send(["loadPreset", c]);
  }
}

// Confirm and save preset
function confirmSavePreset(c: string) {
  if (
    globalThis.confirm(
      "Do you really want to save this preset? Anything named 'default' will be loaded at startup."
    )
  ) {
    api.send(["savePreset", c]);
  }
}

// Create preset
function createPreset(name: string) {
  api.send(["savePreset", name]);
}

// Move effect up in chain
function moveEffectUp(channel: string, effectIndex: number) {
  if (effectIndex > 0) {
    const x = channels.value[channel].effects[effectIndex];
    const y = channels.value[channel].effects[effectIndex - 1];
    channels.value[channel].effects[effectIndex] = y;
    channels.value[channel].effects[effectIndex - 1] = x;
    api.send(["setEffects", channel, channels.value[channel].effects]);
  }
}

// Move effect down in chain
function moveEffectDown(channel: string, effectIndex: number) {
  if (effectIndex < channels.value[channel].effects.length - 1) {
    const x = channels.value[channel].effects[effectIndex];
    const y = channels.value[channel].effects[effectIndex + 1];
    channels.value[channel].effects[effectIndex] = y;
    channels.value[channel].effects[effectIndex + 1] = x;
    api.send(["setEffects", channel, channels.value[channel].effects]);
  }
}

// Delete effect from chain
function deleteEffect(channel: string, effectIndex: number) {
  channels.value[channel].effects.splice(effectIndex, 1);
  api.send(["setEffects", channel, channels.value[channel].effects]);
}

// Set channel fader level
function setFader(channel: string, value: number) {
  api.send(["setFader", channel, value]);
}

// Set channel mute state
function setMute(channel: string, value: boolean) {
  api.send(["setMute", channel, value]);
}

// Set channel output
function setOutput(channel: string, value: string) {
  api.send(["setOutput", channel, value]);
}

// Set channel feedback cutoff threshold
function setFuse(channel: string, value: string) {
  api.send(["setFuse", channel, value]);
}

// Set effect parameter
function setParameter(
  channel: string,
  effect: string,
  parameter: string,
  value: any
) {
  api.send(["setParam", channel, effect, parameter, value]);
}

// Set channel input
function setInput(channel: string, value: string) {
  api.send(["setInput", channel, value]);
}

// Check if effect can be used with channel count
function canUseEffect(fx: any, channels: number) {
  if (fx.gstElement) {
    return 1;
  }
  if (channels === 2 && fx.stereoGstElement) {
    return 1;
  }
  if (channels === 1 && fx.monoGstElement) {
    return 1;
  }
  return 0;
}

// Sort connectables (ports) for display
function sortedConnectables(pl: Record<string, any>) {
  const l: string[] = [];
  const clients: Record<string, number> = {};

  for (const i in pl) {
    l.push(i);
    const client = i.split(":")[0];
    if (!(client in clients)) {
      l.push(client);
      clients[client] = 1;
    }
  }
  l.sort();
  return l;
}

// Lifecycle hook - initialize API widget and set up message handler
onMounted(async () => {
  try {
    // Dynamic import of APIWidget to avoid bundling issues
    const widgetModule = await import("/static/js/widget.mjs");
    const APIWidgetClass = widgetModule.APIWidget;

    // Initialize API widgets
    api = new APIWidgetClass(properties.boardApiUuid);
    gapi = new APIWidgetClass(properties.globalApiUuid);

    // Set up message handler for real-time updates
    api.upd = (message_: any[]) => {
      if (message_[0] === "recordingStatus") {
        recordStatus.value = message_[1];
      }

      if (message_[0] === "newport") {
        if (message_[3]) {
          inports.value[message_[1]] = message_[2];
        } else {
          outports.value[message_[1]] = message_[2];
        }
      }

      if (message_[0] === "rmport") {
        delete inports.value[message_[1]];
        delete outports.value[message_[1]];
      }

      if (message_[0] === "ui_ready") {
        ui_ready.value = true;
      }

      if (message_[0] === "inports") {
        inports.value = message_[1];
      }

      if (message_[0] === "presets") {
        presets.value = message_[1];
      }

      if (message_[0] === "effectTypes") {
        effectTypes.value = message_[1];
      }

      if (message_[0] === "outports") {
        outports.value = message_[1];
      }

      if (message_[0] === "channels") {
        channels.value = message_[1];
      }

      if (message_[0] === "loadedPreset") {
        loadedPreset.value = message_[1];
      }

      if (message_[0] === "midiinports") {
        midiinports.value = message_[1];
      }

      if (message_[0] === "midioutports") {
        midioutports.value = message_[1];
      }

      if (message_[0] === "lv" && channels.value[message_[1]]) {
        channels.value[message_[1]].level = message_[2];
      }

      if (message_[0] === "status" && channels.value[message_[1]]) {
        channelStatus.value[message_[1]] = message_[2];
      }

      if (message_[0] === "fader") {
        channels.value[message_[1]].fader = message_[2];
      }

      if (message_[0] === "mute") {
        channels.value[message_[1]].mute = message_[2];
      }
    };

    gapi.upd = api.upd;
  } catch (error) {
    console.error("Failed to initialize API widget:", error);
  }
});
</script>

<style scoped>
.channel {
  height: 95%;
  display: inline-flex;
  flex-direction: column;
  vertical-align: top;
  flex-grow: 0.1;
}

.chain {
  border-style: none;
  max-height: 30em;
  overflow: auto;
}

.num-param-value {
  min-width: 3.5em;
}

details {
  padding: 0px;
  margin: 0px;
}

button.bold {
  font-weight: bolder;
  text-shadow: 5px;
}
</style>
