<template id="template">
  <div id="app" v-cloak class="flex-row gaps">
    <datalist id="tagslisting">
      <option
        v-for="(v, i) of availableTags"
        v-bind:value="i"
        v-bind:key="i"></option>
    </datalist>

    <datalist id="midiinputs">
      <option
        v-for="(v, _i) of midiInputs"
        v-bind:value="v"
        v-bind:key="v"></option>
    </datalist>

    <section id="optionsblock" class="multibar undecorated w-full">
      <div class="menubar tool-bar noselect">
        <p id="toolbar-clock"></p>
        <p>
          <b>{{ boardname }}</b>
        </p>
        <a
          class="button"
          data-testid="commander-link"
          :href="
            '/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/commander/' +
            boardname
          "
          ><i class="mdi mdi-dance-ballroom"></i
        ></a>

        <button
          type="button"
          v-on:click="saveToDisk()"
          :disabled="no_edit"
          title="Save the current state now.  If not manually saved, autosave happens every 10min">
          <i class="mdi mdi-content-save"></i>Save
        </button>
      </div>

      <div class="menubar tool-bar noselect">
        <button type="button" popovertarget="presetsDialog">
          <i class="mdi mdi-playlist-edit"></i>Presets
        </button>
        <button type="button" v-on:click="showevents = !showevents">
          <i class="mdi mdi-flag"></i>Events
        </button>

        <button
          type="button"
          v-on:click="showslideshowtelemetry = !showslideshowtelemetry">
          <i class="mdi mdi-monitor"></i>Displays
        </button>
        <a
          aria-label="Settings"
          class="button"
          :href="
            '/chandler/config/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/' + boardname
          "
          ><i class="mdi mdi-cog-outline"></i></a
        ><label>
          <i class="mdi mdi-volume-medium"></i
          ><input type="checkbox" class="toggle" v-model="uiAlertSounds" />
        </label>
        <button
          aria-label="Fullscreen"
          type="button"
          onclick="document.documentElement.requestFullscreen()">
          <i class="mdi mdi-arrow-expand-all"></i>
        </button>
      </div>

      <div class="menubar tool-bar noselect">
        <p><b>Keys:</b></p>
        <button
          type="button"
          v-on:click="editMode"
          v-bind:class="{ highlight: keybindmode == 'edit' }">
          <i class="mdi mdi-pencil"></i>Edit Mode
        </button>
        <button
          type="button"
          v-on:click="runMode"
          v-bind:class="{ highlight: keybindmode == 'run' }">
          <i class="mdi mdi-flag"></i>Send Events
        </button>
      </div>
    </section>

    <main class="w-full flex-row">
      <section
        class="window w-full max-h-12rem"
        v-if="Object.keys(sys_alerts).length > 0">
        <div class="flex-row scroll gaps padding">
          <div
            class="card w-sm-full"
            v-bind:key="v.id"
            v-for="(v, i) of sys_alerts">
            <header :class="v['barrel-class']" class="padding break-word">
              <i class="mdi mdi-alert"></i>{{ i }}
            </header>
            <p :class="v['barrel-class']">
              {{ v.message || "no trip message" }}
            </p>
          </div>
        </div>
      </section>
      <section
        class="window margin w-sm-full flex-col gaps h-48rem"
        style="resize: both; padding-bottom: 1px">
        <header>
          <div
            class="decorative-image-h-bar decorative-image"
            style="min-height: 3em; margin: auto"></div>

          <div class="tool-bar noselect">
            <input
              size="8"
              type="text"
              title="Enter a cue's shortcut code here to activate it. Keybindings are suspended while this is selected."
              aria-label="Shortcut code"
              placeholder="Shortcut"
              v-model="sc_code"
              v-on:keydown.enter="shortcut()"
              v-on:focus="keyboardJS.pause()"
              v-on:blur="keyboardJS.resume()" />
            <button type="button" v-on:click="shortcut()">Go!</button>
          </div>
          <div class="tool-bar noselect">
            <input
              type="text"
              v-model="groupfilter"
              placeholder="Search"
              list="tracks" />
            <button
              type="button"
              aria-label="Clear search"
              v-on:click="groupfilter = ''">
              <i class="mdi mdi-backspace"></i>
            </button>
            <button type="button" v-on:click="showPages = !showPages">
              Compact
            </button>
          </div>
        </header>

        <div class="h-24rem scroll">
          <div class="flex-col gaps">
            <article
              v-for="i in formatAllGroups"
              v-bind:key="i[1].id"
              class="card group relative border noselect"
              v-bind:class="{
                grey: i[1].doingHandoff,
                run: i[1].active & !i[1].doingHandoff,
              }">
              <header>
                <div>
                  <h4>
                    <button
                      type="button"
                      class="w-full noselect"
                      popovertarget="selectedGroupWindow"
                      v-on:click="selectgroup(i[1], i[0])">
                      <span style="font-size: 150%">{{ i[1].name }}</span
                      ><span v-if="i[1].ext" class="grey"> (external)</span>

                      <i
                        class="mdi mdi-wifi"
                        v-if="i[1].mqttServer"
                        title="This group uses MQTT"></i>
                    </button>
                  </h4>
                </div>
              </header>
              <p v-if="cuemeta[i[1].cue]">
                <span v-if="i[1].active && cuemeta[i[1].cue]"
                  data-testid="sidebar-active-cue-name"
                  >{{ cuemeta[i[1].cue].name }}
                  <small>{{ formatTime(i[1].enteredCue) }}</small></span
                >
                <span v-if="cuemeta[i[1].cue].sound"
                  ><i class="mdi mdi-music"></i
                ></span>

                <span
                  v-if="cuemeta[i[1].cue].inheritRules"
                  title="This cue has rules inherited"
                  v-on:click="selectcue(groupname, cuemeta[i[1].cue].name)"
                  ><i class="mdi mdi-script-text-outline"></i
                ></span>
                <span
                  v-if="
                    cuemeta[i[1].cue].rules &&
                    cuemeta[i[1].cue].rules.length > 0
                  "
                  title="This cue has rules attached"
                  v-on:click="selectcue(groupname, cuemeta[i[1].cue].name)"
                  ><i class="mdi mdi-script-text-outline"></i
                ></span>
              </p>
              <p class="warning" v-if="i[1].status">
                STATUS: {{ i[1].status }}
              </p>

              <div class="tool-bar noselect" v-if="!i[1].utility">
                <button
                  type="button"
                  :class="{ success: i[1].active, warning: i[1].status }"
                  v-on:click="go(i[0])">
                  <i class="mdi mdi-play"></i>Go!
                </button>
                <button type="button" v-on:click="gotoPreviousCue(i[0])">
                  <i class="mdi mdi-skip-previous"></i>Prev
                </button>
                <button type="button" v-on:click="gotoNextCue(i[0])">
                  Next<i class="mdi mdi-skip-next"></i>
                </button>
                <button
                  type="button"
                  class="stopbutton"
                  v-on:click="stop(i[0])">
                  <i class="mdi mdi-stop-circle-outline"></i>Stop
                </button>
              </div>
              <iframe
                v-if="showPages && i[1].infoDisplay.length > 0"
                :src="i[1].infoDisplay"></iframe>

              <div
                class="tool-bar noselect"
                v-if="i[1].eventButtons.length > 0">
                <button
                  type="button"
                  v-for="v of i[1].eventButtons"
                  v-bind:key="v[1] + '_' + v[0]"
                  v-on:click="sendGroupEventWithConfirm(v[1], v[1])">
                  {{ v[0] }}
                </button>
              </div>

              <smooth-range
                style="margin-left: 0.4rem"
                v-if="!i[1].utility"
                max="1"
                step="0.01"
                min="0"
                v-on:input="setalpha(i[0], parseFloat($event.target.value))"
                v-model="alphas[i[0]]"></smooth-range>

              <group-ui
                :unixtime="unixtime"
                v-bind:group-data="i[1]"
                :cue="cuemeta[i[1].cue]"></group-ui>

              <div class="w-full flex">
                <cue-countdown
                  :group="i[1]"
                  :cue="cuemeta[i[1].cue]"></cue-countdown>
                <small>
                  <span
                    v-if="
                      i[1].active &&
                      ('' + cuemeta[i[1].cue].length).indexOf('@') > -1
                    ">
                    <i class="mdi mdi-clock-end"></i>
                    {{ cuemeta[i[1].cue].length.substring(1) }}
                  </span>
                </small>
              </div>

              <div
                class="w-full flex"
                v-if="i[1].active && i[1].nextScheduledCue">
                <span
                  ><i class="mdi mdi-calendar-clock"></i>
                  {{ formatTime(i[1].nextScheduledCue[1])
                  }}<i class="mdi mdi-arrow-right"></i>
                  {{ i[1].nextScheduledCue[0] }}
                </span>
              </div>

              <footer>
                <span
                  v-if="
                    cuemeta[i[1].cue] &&
                    (cuemeta[i[1].cue].next || cuemeta[i[1].cue].defaultnext)
                  "
                  >Next Cue:
                  {{
                    cuemeta[i[1].cue].next || cuemeta[i[1].cue].defaultnext
                  }}</span
                >

                <small v-if="i[1].blend !== 'normal'"
                  >Blend:<b>{{ i[1].blend }}</b></small
                >
                <small v-if="cuemeta[i[1].cue] && cuemeta[i[1].cue].sound"
                  ><br />Sound:<b>{{
                    cuemeta[i[1].cue].sound.match(/([^\/]+)$/)[1]
                  }}</b></small
                >
              </footer>
            </article>
          </div>
        </div>

        <footer class="padding">
          <div class="tool-bar noselect">
            <input
              type="text"
              :disabled="no_edit"
              v-model="newgroupname"
              placeholder="New group name"
              size="4" />
            <button
              type="button"
              data-testid="add-group-button"
              v-on:click="addGroup()">
              <i class="mdi mdi-plus"></i>Add
            </button>
          </div>
        </footer>
      </section>

      <section
        class="window margin flex-item"
        v-if="showevents"
        style="position: fixed; z-index: 99; bottom: 0px; width: 97%">
        <header>
          <div class="tool-bar noselect">
            <h2>Event Log</h2>
            <input
              type="text"
              v-model="eventsFilterString"
              placeholder="Filter events" /><br />
            <button type="button" v-on:click="showevents = 0">
              <i class="mdi mdi-close"></i>Close
            </button>
          </div>
        </header>

        <div class="max-h-18rem scroll border">
          <div
            v-bind:class="{
              error: i[0].includes('error'),
            }"
            v-bind:key="i[2] + '@' + i[1]"
            v-for="i in recentEventsLog.filter(
              (d) =>
                d[1].search(eventsFilterString) > -1 ||
                d[0].search(eventsFilterString) > -1
            )">
            {{ i[2] }}:
            <b>{{ i[0] }}</b>
            at
            {{ i[1] }}:

            <span v-if="!(typeof i[3] == 'string' && i[3].length > 32)">{{
              i[3]
            }}</span>
            <pre v-if="typeof i[3] == 'string' && i[3].length > 32">{{
              i[3]
            }}</pre>
            <pre v-if="i[4]">{{ i[4] }}</pre>
          </div>
        </div>

        <label
          >Send Global Event:
          <input
            type="text"
            :disabled="no_edit"
            v-model="eventToSendBox"
            v-on:keydown.enter="sendEvent"
            placeholder="Event Name"
            title="Event Name" />
        </label>

        <input
          :disabled="no_edit"
          v-model="eventValueToSendBox"
          v-on:keydown.enter="sendEvent"
          title="Event Value"
          placeholder="value" />

        <select v-model="eventTypeToSendSelection">
          <option value="int">Integer</option>
          <option value="float">Real Number</option>
          <option value="str">Text</option>
        </select>

        <button type="button" v-on:click="sendEvent('__global__')">Send</button>
      </section>

      <section
        v-if="showslideshowtelemetry"
        class="flex-item window paper h-24rem margin">
        <header>
          <div class="tool-bar noselect">
            <h3>Slideshow Players</h3>
            <button
              type="button"
              v-on:click="showslideshowtelemetry = !showslideshowtelemetry">
              <i class="mdi mdi-close"></i>Close
            </button>
          </div>
        </header>

        <slideshow-telemetry
          :telemetry="slideshow_telemetry"></slideshow-telemetry>
      </section>

      <fixture-presets-dialog
        :fixture="selectingPresetFor"
        :fordestination="selectingPresetForDestination"
        :fixtureclasses="fixtureClasses"
        :fixturetype="lookupFixtureType(selectingPresetFor)"
        :currentvals="(cuevals[currentcueid] || {})[selectingPresetFor]"
        :currentcueid="currentcueid"
        :getpresetimage="getPresetImage"
        :no_edit="no_edit"></fixture-presets-dialog>

      <preset-editing-dialog
        :presets="presets"
        :no_edit="no_edit"
        :updatepreset="updatePreset"
        :getpresetimage="getPresetImage"
        :deletepreset="deletePreset"
        :copypreset="copyPreset"
        :renamepreset="renamePreset"></preset-editing-dialog>

      <dialog id="soundpreviewdialog">
        <header>
          <div class="tool-bar noselect">
            <button type="button" v-on:click="closePreview">OK</button>
          </div>
        </header>
        <iframe id="textpreview" style="height: 24em; width: 24em"></iframe>
        <audio controls id="soundpreview"></audio>
      </dialog>

      <div
        popover
        class="card modal paper flex-col"
        id="iframeDialog"
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
          <button
            @click="iframeDialog = null"
            popovertarget="iframeDialog"
            popovertargetaction="hide"
            class="w-full nogrow">
            <i class="mdi mdi-close"></i>Close
          </button>
        </header>
        <iframe title="excalidraw" :src="iframeDialog"></iframe>
      </div>

      <cue-logic-dialog
        :groupname="groupname"
        :currentcue="currentcue"
        :groupmeta="groupmeta"
        :groupcues="groupcues"
        :editinggroup="editingGroup"
        :availablecommands="availableCommands"
        :availabletags="availableTags"
        :no_edit="no_edit"
        :setcueproperty="setCueProperty"
        :unixtime="unixtime">
      </cue-logic-dialog>

      <section
        popover
        ontoggle="globalThis.handleDialogState(event)"
        id="selectedGroupWindow"
        style="min-height: 90vh"
        class="modal window paper margin w-full"
        v-if="editingGroup && cuemeta[editingGroup.cue]">
        <header>
          <p class="warning" v-if="editingGroup.status">
            STATUS: {{ editingGroup.status }}
          </p>
          <div class="tool-bar noselect">
            <h3>
              <span
                v-on:dblclick="promptRename(groupname)"
                title="Double click to set group name">
                {{ editingGroup.name }}</span
              >
              <small class="success" v-if="editingGroup.active">
                (running)</small
              >
            </h3>
            <button
              type="button"
              class="nogrow"
              v-if="editingGroup.cuelen"
              v-on:click="addTimeToGroup(editingGroup.id)">
              <i class="mdi mdi-clock"></i><i class="mdi mdi-plus"></i>
            </button>

            <button
              aria-label="Group Notes"
              class="nogrow"
              type="button"
              popovertarget="groupNotesDialog">
              <i class="mdi mdi-text"></i>
            </button>

            <button
              aria-label="Group Settings"
              data-testid="group-properties-button"
              class="nogrow"
              type="button"
              popovertarget="groupPropsDialog">
              <i class="mdi mdi-cog"></i>
            </button>

            <button
              aria-label="Delete Group"
              type="button"
              class="nogrow"
              v-on:click="delgroup(groupname)">
              <i class="mdi mdi-delete"></i>
            </button>

            <button
              data-testid="close-group"
              aria-label="Close Group"
              type="button"
              class="nogrow"
              @click="selectingPresetFor = null"
              popovertarget="selectedGroupWindow"
              popovertargetaction="hide">
              <i class="mdi mdi-close"></i>
            </button>
          </div>
        </header>

        <div id="cuesbox">
          <cue-table
            :cuemeta="cuemeta"
            :groupname="groupname"
            :groupcues="groupcues">
            <template v-slot:header>
              <tr>
                <th title="Click the cue name to edit that cue">Name</th>
                <th class="desktop-only">Shortcut</th>
                <th class="desktop-only">Fadein</th>
                <th
                  class="desktop-only"
                  title="Length, 0 indicates until stopped">
                  Length
                </th>
                <th title="The next cue, after this one ends">Next</th>
                <th class="desktop-only">Track</th>
                <th>Jump to</th>
              </tr>
            </template>

            <template v-slot:row="slotProps">
              <tr
                v-bind:class="{
                  highlight: selectedCues[groupname] == slotProps.i[1].name,
                  error: slotProps.i[1].errorLockout,
                  success:
                    cuemeta[editingGroup.cue].name == slotProps.i[1].name,
                }">
                <td
                  class="rowname"
                  data-label="Cue: "
                  style="user-select: none"
                  title="Click the cue name to edit that cue"
                  v-on:click="selectcue(groupname, slotProps.i[1].name)">
                  <span
                    title="Cue number, double click to change."
                    style="width: 6em; margin: 6px"
                    v-on:dblclick="promptsetnumber(slotProps.i[1].id)"
                    >{{ slotProps.i[1].number }}</span
                  >

                  <span
                    v-if="slotProps.i[1].provider"
                    class="mdi mdi-import"></span>

                  <div style="display: inline-block">
                    <span>{{ slotProps.i[1].name.slice(0, 64) }}</span>

                    <img
                      v-if="slotProps.i[1].labelImage.length > 0"
                      :src="
                        '/chandler/WebMediaServer?labelImg=' +
                        encodeURIComponent(slotProps.i[1].id) +
                        '&timestamp=' +
                        encodeURIComponent(slotProps.i[1].labelImageTimestamp)
                      "
                      class="h-center"
                      style="max-height: 1em" />
                  </div>
                  <span v-if="slotProps.i[1].scheduledFor">
                    <i class="mdi mdi-calendar-clock"></i>
                    {{ formatTime(slotProps.i[1].scheduledFor) }}
                  </span>

                  <span
                    title="Checkpoint Cue"
                    v-if="slotProps.i[1].checkpoint"
                    class="mdi mdi-star-four-points-outline"></span>

                  <span v-if="selectedCues[groupname] == slotProps.i[1].name"
                    ><i class="mdi mdi-pencil nomargin"></i
                  ></span>

                  <i
                    class="mdi mdi-light-bulb nomargin"
                    v-if="slotProps.i[1].hasLightingData"
                    title="This cue has lighting commands"></i>

                  <i
                    class="mdi mdi-audio nomargin"
                    v-if="slotProps.i[1].sound"></i>
                  <i
                    class="mdi mdi-monitor nomargin"
                    v-if="slotProps.i[1].slide"></i>

                  <span
                    v-if="slotProps.i[1].inheritRules"
                    title="This cue has rules inherited"
                    ><i class="mdi mdi-script-text-outline nomargin"></i
                  ></span>

                  <span
                    v-if="
                      slotProps.i[1].rules && slotProps.i[1].rules.length > 0
                    "
                    title="This cue has rules attatched"
                    ><i class="mdi mdi-script-text-outline nomargin"></i
                  ></span>
                </td>

                <td class="desktop-only" data-label="Shortcut:">
                  <div class="tool-bar noselect" style="width: 8em">
                    <input
                      :disabled="no_edit"
                      title="Shortcut code"
                      style="max-width: 4.5em"
                      v-on:change="
                        setCueProperty(
                          slotProps.i[1].id,
                          'shortcut',
                          $event.target.value
                        )
                      "
                      min="0"
                      step="0.1"
                      v-model="slotProps.i[1].shortcut" />
                    <button
                      type="button"
                      style="opacity: 0.3"
                      title="Generate a shortcut code from the cue's number"
                      v-on:click="
                        setCueProperty(
                          slotProps.i[1].id,
                          'shortcut',
                          '__generate__from__number__'
                        )
                      ">
                      GEN
                    </button>
                  </div>
                </td>

                <td class="desktop-only" data-label="Fade In:">
                  <input
                    :disabled="no_edit"
                    type="number"
                    v-on:change="
                      setCueProperty(
                        slotProps.i[1].id,
                        'fadeIn',
                        $event.target.value
                      )
                    "
                    style="width: 5em"
                    min="0"
                    step="0.01"
                    title="Fade In"
                    v-model="slotProps.i[1].fadeIn" />
                </td>

                <td class="desktop-only" data-label="Length:">
                  <input
                    :disabled="no_edit"
                    v-on:change="
                      setCueProperty(
                        slotProps.i[1].id,
                        'length',
                        $event.target.value
                      );
                      notifyPopupComputedCueLength($event.target.value);
                    "
                    class="w-12rem"
                    list="lenoptions"
                    title="Cue Length"
                    v-model="slotProps.i[1].length" />
                </td>

                <td data-label="Next Cue:">
                  <select
                    style="width: 98%; max-width: 24rem"
                    v-model="slotProps.i[1].next"
                    :disabled="no_edit"
                    v-if="Object.keys(groupcues[groupname]).length < 40"
                    autocomplete="off"
                    title="Select a cue to activate when this one ends"
                    v-on:change="
                      setnext(slotProps.i[1].id, $event.target.value)
                    ">
                    <option value="">
                      &gt;&gt;&gt; {{ editingGroup.defaultnext }}
                    </option>
                    <option
                      v-for="j in formatCues"
                      v-bind:value="j[1].name"
                      v-bind:key="j[1].id">
                      {{ j[1].number }}: {{ j[1].name.slice(0, 16) }}
                    </option>
                    <option v-bind:value="slotProps.i[1].next">
                      {{ slotProps.i[1].next }}
                    </option>

                    <option value="__random__">RANDOM</option>
                    <option value="__shuffle__">SHUFFLE</option>
                    <option value="__schedule__">Skip to Schedule</option>
                  </select>

                  <input
                    :disabled="no_edit"
                    name="nextcue"
                    class="w-12rem"
                    v-if="Object.keys(groupcues[groupname]).length > 40"
                    autocomplete="off"
                    list="cues_in_group"
                    title="Select a cue to activate when this one ends"
                    v-on:change="
                      setnext(slotProps.i[1].id, $event.target.value)
                    "
                    v-model="slotProps.i[1].next"
                    v-bind:placeholder="editingGroup.defaultnext" />
                </td>

                <td class="desktop-only" data-label="Track vals from prev: ">
                  <input
                    :disabled="no_edit"
                    type="checkbox"
                    v-on:change="
                      setCueProperty(
                        slotProps.i[1].id,
                        'track',
                        slotProps.i[1].track
                      )
                    "
                    v-model="slotProps.i[1].track"
                    title="Track values from previous cue? If false, values not present are always transparent" />
                </td>
                <td data-label="Goto:">
                  <button
                    type="button"
                    style="min-width: 90%"
                    v-on:click="jumpToCueWithConfirmationIfNeeded(slotProps.i[1].id, editingGroup.id)">
                    Go
                  </button>
                </td>
              </tr>
            </template>
          </cue-table>

          <div class="tool-bar noselect">
            <input
              :disabled="no_edit"
              v-model="newcuename"
              placeholder="New cue name"
              list="specialcues" />
            <button
              type="button"
              v-on:click="add_cue(groupname, newcuename, currentcue)">
              <i class="mdi mdi-plus"></i>Add Cue
            </button>
            <button
              type="button"
              v-on:click="clonecue(groupname, currentcueid, newcuename)">
              <i class="mdi mdi-content-copy"></i>Clone Cue
            </button>
            <button type="button" v-on:click="rmcue(currentcueid)">
              <i class="mdi mdi-delete"></i>Delete Current
            </button>
          </div>
        </div>

        <hr />

        <div v-if="currentcue">
          <div class="tool-bar noselect">
            <h3>
              <i class="mdi mdi-pencil nomargin nogrow"></i>Editing Cue:
              {{ currentcue.name }}
            </h3>

            <button
              type="button"
              popovertarget="cueTextDialog"
              data-testid="cue-text-dialog-button">
              <i class="mdi mdi-text"></i>
              Text
            </button>

            <button
              type="button"
              popovertarget="cueMediaDialog"
              data-testid="cue-media-dialog-button">
              <i class="mdi mdi-music"></i>
              Media
            </button>

            <button type="button" popovertarget="cuePropsDialog">
              <i class="mdi mdi-cog"></i>
              Properties
            </button>

            <button
              type="button"
              popovertarget="cueLogicDialog"
              data-testid="cue-logic-button">
              <i class="mdi mdi-code-braces"></i>
              Logic({{ currentcue.rules.length }})
            </button>
          </div>
          <div class="tool-bar noselect w-full">
            <label class="grow" for="cuenotes"
              ><span><i class="mdi mdi-text"></i>Notes</span>
            </label>

            <input
              :disabled="no_edit"
              type="text"
              id="cuenotes"
              v-on:change="
                setCueProperty(currentcueid, 'notes', $event.target.value)
              "
              v-model="cuemeta[currentcueid].notes" />
          </div>

          <div class="tool-bar noselect">
            <p v-if="currentcue.sound">Sound: {{ currentcue.sound }}</p>
            <p v-if="currentcue.slide">Slide: {{ currentcue.slide }}</p>
          </div>

          <div class="tool-bar noselect error" v-if="currentcue.errorLockout">
            <p>
              <i class="mdi mdi-alert"></i>
              ERROR: Data may be corrupt, check all settings
            </p>

            <button
              type="button"
              v-on:click="setCueProperty(currentcueid, 'errorLockout', false)">
              <i class="mdi mdi-lock-open"></i>Re-enable
            </button>
          </div>

          <p v-if="currentcue.name.startsWith('__')" class="highlight">
            Cues starting with __ are special cues. They are never chosen in
            random selections or as the default next cue and may have predefined
            system functions attatched.
          </p>

          <span class="help" v-if="editingGroup.ext"
            >This is an external group that is defined somewhere in code. Any
            changes made here may be overwritten by the code at any time.</span
          >

          <div class="undecorated">
            <div class="tool-bar noselect noselect">
              <button
                type="button"
                v-bind:class="{ highlight: groupChannelsViewMode == 'cue' }"
                v-on:click="groupChannelsViewMode = 'cue'">
                <i class="mdi mdi-cog-outline"></i>Normal View
              </button>
              <button
                type="button"
                v-bind:class="{
                  highlight: groupChannelsViewMode == 'channels',
                }"
                data-testid="add-rm-fixtures-button"
                v-on:click="groupChannelsViewMode = 'channels'">
                <i class="mdi mdi-list-box-outline"></i>Add/Remove Fixtures
              </button>
            </div>

            <div
              class="fadersbox flex-row nopadding"
              style="max-width: 100%; align-items: baseline">
              <template
                v-for="(h, uname) in cuevals[currentcueid]"
                v-bind:key="uname">
                <article
                  class="universe card flex-col gaps"
                  v-if="uname[0] != '@'">
                  <header>
                    <h3 class="noselect">{{ uname }}</h3>
                  </header>
                  <details class="undecorated nopadding nomargin">
                    <summary data-testid="details-fixture-channels-summary">
                      Channels
                    </summary>
                    <div class="scroll nomargin flex-row fader-box-inner">
                      <h-fader
                        :i="i[1]"
                        :groupid="groupname"
                        :chinfo="channelInfoForUniverseChannel(i[1].u, i[1].ch)"
                        :currentcueid="currentcueid"
                        :showdelete="groupChannelsViewMode == 'channels'"
                        :fixcmd="h"
                        v-bind:key="i[1].ch"
                        v-for="i in dictView(h, [])">
                      </h-fader>
                    </div>
                  </details>
                </article>
              </template>

              <template v-for="(h, fname) in cuevals[currentcueid]">
                <article
                  v-bind:key="fname"
                  class="fixture card flex-col gaps noselect"
                  v-if="fname[0] == '@'">
                  <header>
                    <h4 :title="lookupFixtureType(fname)">
                      {{ fname }}
                    </h4>

                    <div class="tool-bar noselect">
                      <button
                        type="button"
                        @click="showPresetDialog(fname, false)"
                        popovertarget="presetForFixture"
                        title="Select a preset for this fixture"
                        data-testid="select-preset-for-fixture">
                        <i class="mdi mdi-playlist-play"></i>
                      </button>

                      <button
                        type="button"
                        v-if="h.__length__"
                        @click="showPresetDialog(fname, true)"
                        title="Select a preset for the end of the range effect"
                        popovertarget="presetForFixture">
                        <i class="mdi mdi-playlist-play"></i>
                        <i class="mdi mdi-arrow-right"></i>
                      </button>

                      <select
                        :disabled="no_edit"
                        class="w-4rem nogrow"
                        style="flex-basis: 2rem"
                        data-testid="save-preset-options"
                        v-on:change="
                          savePreset(h, $event.target.value);
                          $event.target.value = '__dummy__';
                        ">
                        <option value="__dummy__">Save</option>
                        <option value="">For Any</option>
                        <option
                          :value="'name' + fname"
                          title="Save for use with this fixture">
                          For This
                        </option>
                        <option
                          :value="
                            'name@h-fa' + lookupFixtureColorProfile(fname)
                          "
                          title="Save for use with fixtures of this type">
                          For Type
                        </option>
                      </select>
                    </div>
                    <button
                      type="button"
                      v-if="groupChannelsViewMode == 'channels'"
                      v-on:click="rmFixCue(currentcueid, fname)">
                      <i class="mdi mdi-delete"></i>
                    </button>
                  </header>

                  <details
                    class="undecorated nopadding nomargin"
                    data-testid="details-fixture-channels-summary">
                    <summary class="nomargin nopadding">
                      <img
                        v-if="fixtureAssignments[fname.slice(1)]?.label_image"
                        style="max-height: 4em"
                        :src="
                          '/chandler/WebMediaServer?file=' +
                          encodeURIComponent(
                            fixtureAssignments[fname.slice(1)]?.label_image
                          ) +
                          '&ts=' +
                          fixtureAssignments[fname.slice(1)]
                            ?.labelImageTimestamp
                        " />

                      <div
                        class="preset-icon"
                        v-if="
                          h['__preset__'] &&
                          h['__preset__'].v &&
                          presets[h['__preset__'].v]
                        ">
                        <img
                          style="max-height: 4em; object-fit: cover"
                          :src="
                            '/chandler/WebMediaServer?file=' +
                            encodeURIComponent(
                              getPresetImage(h['__preset__'].v)
                            )
                          " />

                        <div
                          class="label"
                          :style="{
                            'background-color':
                              presets[h['__preset__'].v]?.html_color ||
                              'transparent',
                          }">
                          {{ h["__preset__"].v.split("@")[0] }}
                        </div>
                      </div>
                    </summary>

                    <div
                      class="scroll nomargin padding-bottom flex-row fader-box-inner">
                      <h-fader
                        :i="i[1]"
                        :groupid="groupname"
                        :chinfo="channelInfoForUniverseChannel(i[1].u, i[1].ch)"
                        :currentcueid="currentcueid"
                        :showdelete="groupChannelsViewMode == 'channels'"
                        :fixcmd="h"
                        v-bind:key="i[1].ch"
                        v-for="i in dictView(h, [])">
                      </h-fader>
                    </div>
                  </details>
                </article>
              </template>
              <div
                v-if="groupChannelsViewMode == 'channels'"
                class="flex-row gaps">
                <div class="card margin">
                  <header>
                    <h4>Add Raw Channel</h4>
                  </header>

                  <div class="stacked-form w-20rem">
                    <label
                      >Universe
                      <combo-box
                        v-bind:options="useBlankDescriptions(universes)"
                        v-model="newcueu"></combo-box>
                    </label>

                    <label>
                      Channel
                      <combo-box
                        v-bind:options="getChannelCompletions(newcueu)"
                        v-model="newcuevnumber">
                      </combo-box>
                    </label>

                    <button
                      type="button"
                      :disabled="no_edit"
                      data-testid="add-channel-to-cue-button"
                      v-on:click="addValueToCue()">
                      <i class="mdi mdi-plus"></i>Add Channel to Cue
                    </button>
                  </div>
                </div>

                <div class="card margin">
                  <header>
                    <h4>Add Tag Point</h4>
                  </header>

                  <div class="stacked-form w-20rem">
                    <label
                      >Tag
                      <input v-model="newcuetag" list="tagslisting" />
                    </label>

                    <button
                      type="button"
                      :disabled="no_edit"
                      v-on:click="addTagToCue()"
                      data-testid="add-tag-to-cue-button">
                      <i class="mdi mdi-plus"></i>Add Tag to Cue
                    </button>
                  </div>
                </div>

                <div class="card margin w-24rem">
                  <header>
                    <h4>Add Fixture</h4>
                  </header>
                  <div class="scroll">
                    <table>
                      <tr
                        v-for="(v, i) in fixtureAssignments"
                        v-bind:key="v.universe + '_' + v.channel">
                        <td>{{ v.universe }}:{{ i }} at {{ v.channel }}</td>
                        <td>
                          <button
                            type="button"
                            v-on:click="addfixToCurrentCue(i, 1, 1, 0)">
                            <i class="mdi mdi-plus"></i>Add
                          </button>
                        </td>
                        <td>
                          <button type="button" v-on:click="addRangeEffect(i)">
                            <i class="mdi mdi-plus"></i>Range Effect
                          </button>
                        </td>
                      </tr>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div>
            <cue-media-dialog
              :currentcue="currentcue"
              :groupname="groupname"
              :setcueproperty="setCueProperty"
              :testsoundcard="testSoundCard"
              :editinggroup="editingGroup"
              :soundcards="soundCards"
              :setgroupproperty="setGroupProperty"></cue-media-dialog>

            <div
              class="window w-full modal"
              popover
              id="cueTextDialog"
              ontoggle="globalThis.handleDialogState(event)">
              <header>
                <div class="tool-bar noselect">
                  <h4>{{ currentcue.name }} Text</h4>
                  <button
                    class="nogrow"
                    type="button"
                    popovertarget="cueTextDialog"
                    popovertargetaction="hide">
                    <i class="mdi mdi-close" data-testid="close-cue-text"></i
                    >Close
                  </button>
                </div>
              </header>

              <textarea
                v-model="currentcue.markdown"
                class="w-full h-16rem"
                data-testid="cuetext"
                @input="
                  setCuePropertyDeferred(
                    currentcue.id,
                    'markdown',
                    $event.target.value
                  )
                "
                @change="
                  setCueProperty(currentcue.id, 'markdown', $event.target.value)
                ">
              </textarea>
            </div>

            <div
              class="window w-full modal"
              popover
              id="cuePropsDialog"
              ontoggle="globalThis.handleDialogState(event)">
              <header>
                <div class="tool-bar noselect">
                  <h4>{{ currentcue.name }}</h4>
                  <button
                    class="nogrow"
                    type="button"
                    popovertarget="cuePropsDialog"
                    popovertargetaction="hide"
                    data-testid="close-cue-props">
                    <i class="mdi mdi-close"></i>Close
                  </button>
                </div>
              </header>

              <div>
                <div class="flex-row gaps">
                  <fieldset class="stacked-form w-sm-full">
                    <legend>Basic</legend>
                    <label>Action</label>
                    <div class="tool-bar noselect">
                      <button
                        type="button"
                        v-on:click="
                          promptRenameCue(groupname, currentcue.name)
                        ">
                        <i class="mdi mdi-rename-box-outline"></i>Rename Cue
                      </button>
                    </div>

                    <label
                      ><span
                        ><i class="mdi mdi-pound-box-outline"></i> Number</span
                      >
                      <input
                        :disabled="no_edit"
                        type="number"
                        title="Cue number"
                        v-on:change="
                          setnumber(currentcueid, $event.target.value)
                        "
                        min="0"
                        step="0.1"
                        v-model="currentcue.number" />
                    </label>

                    <label
                      ><i class="mdi mdi-star-four-points-outline"></i
                      >Checkpoint
                      <input
                        :disabled="no_edit"
                        type="checkbox"
                        v-model="currentcue.checkpoint"
                        title="At startup, jump to the last checkpoint cue you were in."
                        v-on:change="
                          setCueProperty(
                            currentcueid,
                            'checkpoint',
                            currentcue.checkpoint
                          )
                        " />
                    </label>

                    <p>
                      <label>
                        <input
                          :disabled="no_edit"
                          type="checkbox"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'track',
                              currentcue.track
                            )
                          "
                          v-model="currentcue.track"
                          title="Track values from previous cue? If false, values not present are always transparent" />
                        <span
                          ><i class="mdi mdi-arrow-expand-right"></i>Track</span
                        >
                      </label>

                      <label
                        ><input
                          :disabled="no_edit"
                          title="If false, dissallow entering cue if it's already running"
                          type="checkbox"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'reentrant',
                              currentcue.reentrant
                            )
                          "
                          v-model="currentcue.reentrant" /><span
                          ><i class="mdi mdi-replay"></i>Reentrant</span
                        ></label
                      >
                    </p>

                    <p>
                      <datalist id="shortcuts">
                        <option
                          v-bind:key="i"
                          v-for="i of shortcuts"
                          v-bind:value="i"></option>
                      </datalist>

                      <label
                        ><span
                          ><i class="mdi mdi-arrow-down-circle-outline"></i
                          >Shortcut
                        </span>
                        <input
                          :disabled="no_edit"
                          title="Shortcut code used to quickly activate a cue"
                          size="8"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'shortcut',
                              $event.target.value
                            )
                          "
                          v-model="currentcue.shortcut" />
                      </label>

                      <label
                        ><span
                          ><i class="mdi mdi-arrow-right-circle-outline"></i>
                          Trigger Shortcut</span
                        >
                        <input
                          :disabled="no_edit"
                          type="text"
                          list="shortcuts"
                          title="When entering this cue, trigger the shortcut in other groups"
                          size="8"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'triggerShortcut',
                              $event.target.value
                            )
                          "
                          v-model="currentcue.triggerShortcut" />
                      </label>
                    </p>
                    <p>
                      <label
                        ><span
                          ><i class="mdi mdi-calendar-clock"></i> Schedule
                          At</span
                        >
                        <input
                          :disabled="no_edit"
                          type="text"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'scheduleAt',
                              $event.target.value
                            )
                          "
                          v-model="currentcue.scheduleAt" />
                      </label>
                    </p>
                    <p>
                      <label>
                        <span
                          ><i class="mdi mdi-clock-outline"></i> Fadein</span
                        >
                        <input
                          :disabled="no_edit"
                          type="number"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'fadeIn',
                              $event.target.value
                            )
                          "
                          min="0"
                          step="0.1"
                          v-model="currentcue.fadeIn" />
                      </label>
                      <label
                        ><span><i class="mdi mdi-clock-end"></i> Length</span>
                        <input
                          :disabled="no_edit"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'length',
                              $event.target.value
                            );
                            notifyPopupComputedCueLength($event.target.value);
                          "
                          v-model="cuemeta[currentcueid].length"
                          min="0" />
                      </label>
                    </p>

                    <p>
                      <label
                        ><span
                          ><i class="mdi mdi-dice-multiple-outline"></i> Vary
                          Length</span
                        >
                        <input
                          :disabled="no_edit"
                          type="number"
                          v-on:change="
                            setCueProperty(
                              currentcueid,
                              'lengthRandomize',
                              $event.target.value
                            )
                          "
                          step="0.1"
                          title="Randomize the cue length +- this amount"
                          v-model="cuemeta[currentcueid].lengthRandomize"
                          min="0" />
                      </label>
                      <label
                        ><span
                          ><i class="mdi mdi-dice-multiple-outline"></i
                          >Probability</span
                        >
                        <input
                          title="Probability this cue is selected in random selections. =expressions allowed"
                          v-on:change="
                            setprobability(currentcueid, $event.target.value)
                          "
                          v-model="currentcue.probability"
                          placeholder="1" />
                      </label>
                    </p>

                    <datalist :id="'providers' + groupname">
                      <option
                        v-bind:key="p"
                        v-for="p in editingGroup.cueProviders"
                        :value="p"></option>
                      <option value="">Internal</option>
                    </datalist>

                    <label
                      ><span><i class="mdi mdi-folder"></i>Provider</span>
                      <input
                        :disabled="no_edit"
                        :list="'providers' + groupname"
                        v-on:change="
                          setCueProperty(
                            currentcueid,
                            'provider',
                            $event.target.value
                          )
                        "
                        v-model="cuemeta[currentcueid].provider" />
                    </label>
                  </fieldset>

                  <fieldset class="stacked-form w-sm-full">
                    <legend>Cue Advance</legend>
                    <label
                      >Next Cue
                      <div>
                        <combo-box
                          v-model="cuemeta[currentcueid].next"
                          :disabled="no_edit"
                          v-on:change="
                            setnext(currentcueid, cuemeta[currentcueid].next)
                          "
                          :options="
                            useBlankDescriptions(groupcues[groupname], {
                              '__random__': '',
                              '__shuffle__': 'Avoid Recent',
                              '*': 'Wildcard match',
                            })
                          "></combo-box>
                      </div>
                    </label>
                    <p>
                      <button
                        type="button"
                        v-on:click="gotonext(currentcueid, groupname)">
                        <i class="mdi mdi-arrow-right"></i>Edit Next
                      </button>
                      <button
                        title="If this cue's next does not exist, clone the current cue to be the next, and edit that cue"
                        v-on:click="
                          clonecue(groupname, currentcueid, currentcue.next)
                        ">
                        <i class="mdi mdi-content-copy"></i>Clone to Next
                      </button>
                    </p>

                    <datalist id="cues_in_group" name="cues_in_group">
                      <option
                        v-bind:key="i"
                        v-for="i in Object.keys(groupcues[groupname]).sort()"
                        v-bind:value="i">
                        {{ i }}
                      </option>
                    </datalist>
                  </fieldset>
                </div>
              </div>
            </div>
          </div>

          <div
            class="window w-full modal"
            popover
            id="groupNotesDialog"
            ontoggle="globalThis.handleDialogState(event)">
            <header>
              <div class="tool-bar noselect">
                <h4>{{ editingGroup.name }} Notes</h4>
                <button
                  class="nogrow"
                  type="button"
                  data-testid="close-group-notes"
                  popovertarget="groupNotesDialog"
                  popovertargetaction="hide">
                  <i class="mdi mdi-close"></i>Close
                </button>
              </div>
            </header>

            <div style="overflow: auto; max-height: 30em">
              <textarea
                v-model="editingGroup.notes"
                @change="
                  setGroupProperty(
                    editingGroup.id,
                    'notes',
                    $event.target.value
                  )
                "
                @input="
                  setGroupPropertyDeferred(
                    editingGroup.id,
                    'notes',
                    $event.target.value
                  )
                "></textarea>
            </div>
          </div>

          <div
            class="window w-full modal"
            popover
            id="groupPropsDialog"
            ontoggle="globalThis.handleDialogState(event)">
            <header>
              <div class="tool-bar noselect">
                <h4>Group Settings</h4>
                <button
                  class="nogrow"
                  type="button"
                  data-testid="close-group-settings"
                  popovertarget="groupPropsDialog"
                  popovertargetaction="hide">
                  <i class="mdi mdi-close"></i>Close
                </button>
              </div>
            </header>
            <!-- <details>
                    <summary>Music Visualization Presets</summary>
                    <textarea v-on:change="setvisualization(groupname,$event.target.value);"
                        v-model="editingGroup.musicVisualizations"></textarea>
                </details> -->
            <div class="flex-row gaps">
              <fieldset class="stacked-form w-sm-full">
                <legend>Basic</legend>
                <p>
                  <label
                    ><span
                      ><i class="mdi mdi-circle-opacity"></i>

                      Alpha</span
                    ><input
                      type="number"
                      max="1"
                      step="0.01"
                      min="0"
                      v-on:change="
                        setalpha(groupname, parseFloat($event.target.value))
                      "
                      v-model="alphas[groupname]" />
                  </label>

                  <label
                    ><span
                      ><i class="mdi mdi-circle-opacity"></i> Default
                      Alpha</span
                    >
                    <input
                      :disabled="no_edit"
                      type="number"
                      max="1"
                      step="0.01"
                      min="0"
                      v-on:change="
                        setGroupProperty(
                          groupname,
                          'defaultAlpha',
                          parseFloat($event.target.value)
                        )
                      "
                      v-model="editingGroup.defaultAlpha" />
                  </label>
                </p>

                <label
                  ><span><i class="mdi mdi-layers-triple"></i> Blend Mode</span>
                  <select
                    :disabled="no_edit"
                    title="This setting controls blending multiple groups together"
                    v-on:input="
                      setGroupProperty(groupname, 'blend', $event.target.value)
                    "
                    v-model="editingGroup.blend"
                    data-testid="group_blend_mode">
                    <option title="Alpha blend with groups below">
                      normal
                    </option>
                    <option
                      title="Highest Takes Priority, only affect lights if the value is higher than the others">
                      HTP
                    </option>
                    <option title="Limit maximum level">inhibit</option>

                    <option v-bind:key="i" v-for="i in blendModes">
                      {{ i }}
                    </option>
                  </select>
                </label>

                <label
                  ><span
                    ><i class="mdi mdi-lock-alert"></i> Require Confirmation for
                    Cue Jumps</span
                  >
                  <input
                    :disabled="no_edit"
                    type="checkbox"
                    v-model="editingGroup.requireConfirm"
                    v-on:change="
                      setGroupProperty(
                        groupname,
                        'requireConfirm',
                        editingGroup.requireConfirm
                      )
                    " />
                </label>

                <p>
                  <label
                    ><span><i class="mdi mdi-numeric"></i> Priority</span>
                    <input
                      :disabled="no_edit"
                      type="number"
                      min="0"
                      max="100"
                      v-on:change="
                        setGroupProperty(
                          groupname,
                          'priority',
                          parseFloat($event.target.value)
                        )
                      "
                      v-model="editingGroup.priority" />
                  </label>
                </p>
                <p>
                  <label
                    ><span><i class="mdi mdi-metronome"></i> BPM</span>
                    <input
                      :disabled="no_edit"
                      type="number"
                      min="0"
                      max="300"
                      v-on:change="
                        setbpm(groupname, parseFloat($event.target.value))
                      "
                      v-model="editingGroup.bpm" />
                  </label>
                  <button
                    type="button"
                    v-on:click="tap(groupname)"
                    class="grow">
                    <i class="mdi mdi-gesture-tap"></i>Tap
                  </button>
                </p>

                <p>
                  <label
                    title="Check this box to make the group active at startup">
                    <span
                      ><i class="mdi mdi-refresh-auto"></i> Active By
                      Default</span
                    >
                    <input
                      :disabled="no_edit"
                      type="checkbox"
                      v-on:change="
                        setGroupProperty(
                          groupname,
                          'defaultActive',
                          $event.target.checked
                        )
                      "
                      v-model="editingGroup.defaultActive" />
                  </label>

                  <label
                    title="Groups inherit from previous groups even if you jump directly to them">
                    <span
                      ><i class="mdi mdi-skip-forward-outline"></i>
                      Backtrack</span
                    >
                    <input
                      :disabled="no_edit"
                      type="checkbox"
                      v-on:change="
                        setGroupProperty(
                          groupname,
                          'backtrack',
                          $event.target.checked
                        )
                      "
                      v-model="editingGroup.backtrack" />
                  </label>
                </p>

                <label
                  ><span
                    ><i class="mdi mdi-layers-outline"></i> Slideshow
                    Overlay</span
                  >
                  <input
                    :disabled="no_edit"
                    v-on:change="
                      setGroupProperty(
                        groupname,
                        'slideOverlayUrl',
                        $event.target.value
                      )
                    "
                    v-model="editingGroup.slideOverlayUrl" />
                </label>

                <label title="Receive note events from a MIDI input device">
                  <span><i class="mdi mdi-midi-port"></i> MIDI Source:</span>
                  <input
                    :disabled="no_edit"
                    list="midiinputs"
                    v-on:change="
                      setGroupProperty(
                        groupname,
                        'midiSource',
                        $event.target.value
                      )
                    "
                    v-model="editingGroup.midiSource" />
                </label>

                <label title="Receive shortcut codes from a command-type tag">
                  Command Tag:<input
                    :disabled="no_edit"
                    placeholder="Tagpoint"
                    v-on:change="setcommandtag(groupname, $event.target.value)"
                    v-model="editingGroup.commandTag"
                    list="commandtagslisting" />
                </label>

                <label
                  title="You can use this with __random__ to create a shuffle effect."
                  >Default cue advance:
                  <input
                    :disabled="no_edit"
                    list="nextcueoptions"
                    v-on:change="
                      setGroupProperty(
                        groupname,
                        'defaultNext',
                        $event.target.value
                      )
                    "
                    v-model="editingGroup.defaultNext"
                    placeholder="Next cue in list" />
                </label>
              </fieldset>

              <div class="card w-sm-full">
                <header>
                  <h4>Sound</h4>
                </header>
                <div class="stacked-form">
                  <label>
                    Sound Output<input
                      title="If not set by a cue, the global setting for the group is used"
                      v-on:change="
                        setGroupProperty(
                          groupname,
                          'soundOutput',
                          $event.target.value
                        )
                      "
                      v-model="editingGroup.soundOutput"
                      placeholder="default"
                  /></label>

                  <label>
                    Crossfade Media
                    <input
                      :disabled="no_edit"
                      type="number"
                      max="60"
                      step="0.01"
                      min="0"
                      v-on:change="
                        setcrossfade(groupname, parseFloat($event.target.value))
                      "
                      v-model="editingGroup.crossfade" />
                  </label>
                </div>
                <h5>Outputs</h5>
                <div class="scroll max-h-24rem">
                  <dl>
                    <dt>Web Player</dt>
                    <dd>
                      <div class="tool-bar noselect">
                        <button
                          type="button"
                          v-on:click="
                            setGroupProperty(
                              groupname,
                              'soundOutput',
                              'groupwebplayer'
                            )
                          ">
                          Set as Group Default
                        </button>
                      </div>
                    </dd>

                    <template v-for="i of soundCards" v-bind:key="i">
                      <dt>{{ i || "UNSET" }}</dt>
                      <dd>
                        <div class="tool-bar noselect">
                          <button
                            type="button"
                            v-on:click="
                              setGroupProperty(groupname, 'soundOutput', i)
                            ">
                            Set as Group Default
                          </button>
                          <button
                            type="button"
                            v-on:click="testSoundCard(i, 0, 48000)">
                            Test
                          </button>
                        </div>
                      </dd>
                    </template>
                  </dl>
                </div>
              </div>

              <div class="card w-sm-full">
                <header>
                  <h4>MQTT Features</h4>
                </header>
                <div class="stacked-form">
                  <label
                    >MQTT Server:
                    <input
                      :disabled="no_edit"
                      v-on:change="setmqtt(groupname, $event.target.value)"
                      v-model="editingGroup.mqttServer" />
                  </label>

                  <label
                    title="Cue transitions on the same MQTT server sharing a group name will sync if cue names match."
                    >Sync Group Name
                    <input
                      :disabled="no_edit"
                      v-on:change="
                        setmqttfeature(
                          groupname,
                          'syncGroup',
                          $event.target.value
                        )
                      "
                      v-model="editingGroup.mqttSyncFeatures.syncGroup" />
                  </label>
                </div>
              </div>

              <div class="card w-sm-double">
                <header>
                  <h4>UI</h4>
                </header>

                <div class="stacked-form">
                  <p>
                    <label
                      >Utility Group(No controls)
                      <input
                        :disabled="no_edit"
                        type="checkbox"
                        v-on:change="
                          setGroupProperty(
                            groupname,
                            'utility',
                            editingGroup.utility
                          )
                        "
                        v-model="editingGroup.utility"
                        title="If checked, the group is a utility group without sidebar controls. Use for embedding CCTV, or basic state machines." />
                    </label>

                    <label
                      >Hide in Runtime Mode
                      <input
                        :disabled="no_edit"
                        type="checkbox"
                        v-on:change="
                          setGroupProperty(groupname, 'hide', editingGroup.hide)
                        "
                        v-model="editingGroup.hide"
                        title="If checked, the group is a utility group without sidebar controls. Use for embedding CCTV, or basic state machines." />
                    </label>
                  </p>

                  <label
                    title="This URL is shown in a mini window in the sidebar"
                    >Sidebar info URL
                    <input
                      :disabled="no_edit"
                      v-on:change="
                        setinfodisplay(groupname, $event.target.value)
                      "
                      v-model="editingGroup.infoDisplay" />
                  </label>
                </div>
                <h5>Event Buttons</h5>
                <table border="1" class="w-full">
                  <tr>
                    <th>Label</th>
                    <th>Event</th>
                    <th>Action</th>
                  </tr>
                  <tr
                    v-for="(v, i) in editingGroup.eventButtons"
                    v-bind:key="v[1] + '_' + v[0]">
                    <td>
                      <input
                        :disabled="no_edit"
                        v-model="v[0]"
                        class="w-6rem"
                        data-testid="event_button_label"
                        v-on:change="
                          setEventButtons(groupname, editingGroup.eventButtons)
                        " />
                    </td>
                    <td>
                      <input
                        :disabled="no_edit"
                        v-model="v[1]"
                        class="w-6rem"
                        data-testid="event_button_event"
                        v-on:change="
                          setEventButtons(groupname, editingGroup.eventButtons)
                        " />
                    </td>
                    <td>
                      <button
                        data-testid="event_button_delete"
                        v-on:click="
                          editingGroup.eventButtons.splice(i, 1);
                          setEventButtons(groupname, editingGroup.eventButtons);
                        ">
                        Delete
                      </button>
                    </td>
                  </tr>

                  <tr>
                    <td></td>
                    <td></td>
                    <td>
                      <button
                        v-on:click="
                          editingGroup.eventButtons.push(['', '']);
                          setEventButtons(groupname, editingGroup.eventButtons);
                        ">
                        Add Button
                      </button>
                    </td>
                  </tr>
                </table>

                <h5>Display and Input Tags</h5>

                <details class="help">
                  <summary><i class="mdi mdi-help-circle-outline"></i></summary>
                  <p>Lets you display some tag points in the group overview.</p>

                  <p>
                    Tags will be created if they do not exist. Use the tag
                    settings page to configure defaults an limits
                  </p>

                  <p>
                    Expression tags are allowed, =tv('tag1') + 6 will display 6
                    plus the tag 'tv'
                  </p>

                  <p>
                    You can also add inputs to the group overview. You can then
                    respond to these inputs in the cue logic.
                  </p>
                </details>

                <table border="1" class="w-full">
                  <tr class="">
                    <th>Label</th>
                    <th>Width</th>
                    <th>Tag</th>
                    <th>Type</th>
                    <th>Action</th>
                  </tr>
                  <tr
                    v-for="(v, i) in editingGroup.displayTags"
                    v-bind:key="v[0] + '_' + v[1] + v[2]">
                    <td>
                      <input
                        :disabled="no_edit"
                        v-model="v[0]"
                        class="w-6rem"
                        data-testid="display_tag_label"
                        v-on:change="
                          setGroupProperty(
                            groupname,
                            'displayTags',
                            editingGroup.displayTags
                          )
                        " />
                    </td>

                    <td>
                      <input
                        type="number"
                        step="0.1"
                        :disabled="no_edit"
                        v-model="v[2].width"
                        class="w-4rem"
                        data-testid="display_tag_width"
                        v-on:change="
                          setGroupProperty(
                            groupname,
                            'displayTags',
                            editingGroup.displayTags
                          )
                        " />
                    </td>

                    <td>
                      <input
                        :disabled="no_edit"
                        type="text"
                        list="tagslisting"
                        v-model="v[1]"
                        data-testid="display_tag_tag"
                        v-on:change="
                          setGroupProperty(
                            groupname,
                            'displayTags',
                            editingGroup.displayTags
                          )
                        " />
                    </td>

                    <td>
                      <select
                        v-model="v[2].type"
                        class="w-6rem"
                        data-testid="display_tag_type"
                        v-on:change="
                          setGroupProperty(
                            groupname,
                            'displayTags',
                            editingGroup.displayTags
                          )
                        ">
                        <option value="meter">Meter</option>
                        <option value="text">Text</option>
                        <option value="led">LED</option>
                        <option value="string_input">Text Input</option>
                        <option value="numeric_input">Numeric Input</option>
                        <option value="switch_input">Switch Input</option>
                        <option value="null">Don't Show</option>
                      </select>

                      <template v-if="v[2].type == 'led'">
                        <select
                          :disabled="no_edit"
                          v-model="v[2].color"
                          data-testid="display_tag_led_color"
                          v-on:change="
                            setGroupProperty(
                              groupname,
                              'displayTags',
                              editingGroup.displayTags
                            )
                          ">
                          <option value="red">Red</option>
                          <option value="yellow">Yel</option>
                          <option value="green">Grn</option>
                          <option value="blue">Blu</option>
                          <option value="purple">Purple</option>
                        </select>
                      </template>
                    </td>

                    <td>
                      <button
                        data-testid="display_tag_delete"
                        v-on:click="
                          editingGroup.displayTags.splice(i, 1);
                          setGroupProperty(
                            groupname,
                            'displayTags',
                            editingGroup.displayTags
                          );
                        ">
                        Delete
                      </button>

                      <a v-bind:href="'/tagpoints/' + encodeURIComponent(v[1])"
                        ><i class="mdi mdi-gear"></i
                      ></a>
                    </td>
                  </tr>

                  <tr>
                    <td></td>
                    <td></td>
                    <td></td>
                    <td></td>

                    <td>
                      <button
                        v-on:click="
                          editingGroup.displayTags.push([
                            'Label',
                            '=1',
                            { type: 'null' },
                          ]);
                          setGroupProperty(
                            groupname,
                            'displayTags',
                            editingGroup.displayTags
                          );
                        ">
                        Add Tag
                      </button>
                    </td>
                  </tr>
                </table>
              </div>

              <div class="card w-sm-full">
                <header>
                  <h4>Import/Export</h4>
                </header>
                <div class="stacked-form">
                  <label
                    >Download just this group
                    <a
                      class="button"
                      v-bind:href="
                        'downloadOneGroup?id=' +
                        groupname +
                        '&name=' +
                        editingGroup.name
                      "
                      title="Download your group as a file"
                      ><i class="mdi mdi-download"></i>Download Group</a
                    >
                  </label>

                  <label
                    >Download audio playlist as m3u
                    <a
                      class="button"
                      v-bind:href="
                        'downloadm3u?id=' +
                        groupname +
                        '&rel=&name=' +
                        editingGroup.name
                      "
                      title="Download your group as a file"
                      ><i class="mdi mdi-download"></i>Download Playlist</a
                    >
                  </label>

                  <p>
                    This playlist should work in other apps such as VLC on other
                    computers, as long as the same media folders are in the same
                    place relative to your home folder.
                  </p>

                  <label
                    >Add new cues from playlist
                    <a
                      class="button"
                      v-bind:href="'uploadm3u?id=' + groupname"
                      title="Upload a playlist"
                      ><i class="mdi mdi-folder-open"></i>Upload M3U Playlist</a
                    >
                  </label>

                  <p>
                    Uploads use fuzzy search and should work as long as media
                    files exist somewhere in a media folder, you can use
                    playlists from other devices.
                  </p>
                </div>
              </div>

              <div class="card w-sm-full" v-if="editingGroup.blend != 'normal'">
                <header>
                  <h4>Send event</h4>
                </header>
                <div class="stacked-form">
                  <label
                    >Event name:
                    <input
                      :disabled="no_edit"
                      v-model="eventToSendBox"
                      v-on:keydown.enter="sendEvent"
                      placeholder="Event Name"
                      title="Event Name" />
                  </label>

                  <label
                    >Value
                    <input
                      :disabled="no_edit"
                      v-model="eventValueToSendBox"
                      v-on:keydown.enter="sendEvent"
                      title="Event Value"
                      placeholder="value" />
                  </label>
                  <label
                    >Type
                    <select v-model="eventTypeToSendSelection">
                      <option value="int">Integer</option>
                      <option value="float">Real Number</option>
                      <option value="str">Text</option>
                    </select>
                  </label>

                  <button type="button" v-on:click="sendEvent(groupname)">
                    Send
                  </button>
                </div>
              </div>

              <div class="card w-sm-full" v-if="editingGroup.blend != 'normal'">
                <header>
                  <h4>Blend Mode</h4>
                </header>
                <div class="stacked-form">
                  <p>{{ editingGroup.blendDesc }}</p>
                  <p>
                    <label
                      v-bind:key="arg[0]"
                      v-for="arg of dictView(editingGroup.blendArgs, [])"
                      >{{ arg[0] }}:
                      <input
                        :disabled="no_edit"
                        type="number"
                        style="width: 5em"
                        step="0.01"
                        v-bind:title="arg[0]"
                        v-on:change="
                          setGroupProperty(
                            groupname,
                            'blendArgs',
                            editingGroup.blendArgs
                          )
                        "
                        v-model="editingGroup.blendArgs[arg[0]]" />
                    </label>
                  </p>
                </div>
              </div>

              <div class="card w-sm-double">
                <header>
                  <h4>Slideshow Layout</h4>
                </header>
                <p class="help">
                  You have to refresh the player for this to take effect.
                </p>

                <details>
                  <summary>Special Vars</summary>
                  <dl>
                    <dt v-pre>{{ clock }}</dt>
                    <dd>Browser's local formatted time</dd>

                    <dt v-pre>{{ date }}</dt>
                    <dd>Browser's local formatted date</dd>

                    <dt v-pre>{{ countdown }}</dt>
                    <dd>
                      Empty if cue has no length, otherwise, 00:00:00 formatted
                      countdown to end of current cue.
                    </dd>

                    <dt v-pre>{{ var_XXX }}</dt>
                    <dd>User defined variables set in cue logic.</dd>
                  </dl>
                </details>
                <details>
                  <summary>Custom layout for slideshow</summary>
                  <div class="stacked-form">
                    <textarea
                      v-model="editingGroup.slideshowLayout"
                      class="w-full h-16rem"
                      data-testid="slideshow_layout"
                      @change="
                        setGroupProperty(
                          editingGroup.id,
                          'slideshowLayout',
                          $event.target.value
                        )
                      "
                      @input="
                        setGroupPropertyDeferred(
                          editingGroup.id,
                          'slideshowLayout',
                          $event.target.value
                        )
                      "></textarea>
                  </div>
                </details>
              </div>

              <div class="card w-sm-full">
                <header>Slideshow Transform</header>
                <div class="stacked-form">
                  <label
                    >Perspective Distance
                    <span
                      ><input
                        type="range"
                        min="0"
                        max="500"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.perspective"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />
                      {{ editingGroup.slideshowTransform.perspective }}cm</span
                    >
                  </label>

                  <label
                    >Scale X
                    <span
                      ><input
                        type="range"
                        min="0"
                        max="100"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.scale_x"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />
                      {{ editingGroup.slideshowTransform.scale_x }}</span
                    >

                    %
                  </label>

                  <label
                    >Scale Y
                    <span
                      ><input
                        type="range"
                        min="0"
                        max="100"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.scale_y"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />
                      {{ editingGroup.slideshowTransform.scale_y }}%</span
                    >
                  </label>

                  <label
                    >Translate X
                    <span
                      ><input
                        type="range"
                        min="-100"
                        max="100"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.translate_x"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />

                      {{ editingGroup.slideshowTransform.translate_x }}%</span
                    >
                  </label>

                  <label
                    >Translate Y
                    <span
                      ><input
                        type="range"
                        min="-100"
                        max="100"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.translate_y"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />

                      {{ editingGroup.slideshowTransform.translate_y }}%</span
                    >
                  </label>

                  <label
                    >Keystone X
                    <span
                      ><input
                        type="range"
                        min="-180"
                        max="180"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.rotate_x"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />

                      {{ editingGroup.slideshowTransform.rotate_x }}deg</span
                    >
                  </label>

                  <label
                    >Keystone Y
                    <span
                      ><input
                        type="range"
                        min="-180"
                        max="180"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.rotate_y"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />
                      {{ editingGroup.slideshowTransform.rotate_y }}deg</span
                    >
                  </label>

                  <label
                    >Rotate
                    <span
                      ><input
                        type="range"
                        min="-180"
                        max="180"
                        :disabled="no_edit"
                        v-model.number="editingGroup.slideshowTransform.rotate_z"
                        @change="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        "
                        @input="
                          setGroupProperty(
                            editingGroup.id,
                            'slideshowTransform',
                            editingGroup.slideshowTransform
                          )
                        " />
                      {{ editingGroup.slideshowTransform.rotate_z }}deg</span
                    >
                  </label>
                </div>
              </div>

              <div class="card w-sm-full">
                <header>
                  <h4>Cue Providers</h4>
                </header>
                <p>
                  Cue providers let you automatically import cues from a folder
                  of media files.
                </p>

                <div>
                  <ul>
                    <dt
                      v-for="cueprovider of editingGroup.cueProviders"
                      v-bind:key="cueprovider">
                      {{ cueprovider }}
                      <button
                        type="button"
                        v-on:click="
                          editingGroup.cueProviders.splice(
                            editingGroup.cueProviders.indexOf(cueprovider),
                            1
                          );
                          setGroupProperty(
                            editingGroup.id,
                            'cueProviders',
                            editingGroup.cueProviders
                          );
                        ">
                        Delete
                      </button>
                    </dt>
                  </ul>
                </div>

                <media-browser :no_edit="no_edit" :selectfolders="true">
                  <template v-slot="slotProps">
                    <button
                      v-if="slotProps.filename.endsWith('/')"
                      @click="
                        editingGroup.cueProviders.push(
                          'file://' + slotProps.filename + '?import_media=sound'
                        );
                        setGroupProperty(
                          editingGroup.id,
                          'cueProviders',
                          editingGroup.cueProviders
                        );
                      ">
                      Import Sounds
                    </button>

                    <button
                      v-if="slotProps.filename.endsWith('/')"
                      @click="
                        editingGroup.cueProviders.push(
                          'file://' + slotProps.filename + '?import_media=slide'
                        );
                        setGroupProperty(
                          editingGroup.id,
                          'cueProviders',
                          editingGroup.cueProviders
                        );
                      ">
                      Import Slides
                    </button>
                  </template>
                </media-browser>
              </div>
            </div>

            <details class="undecorated">
              <summary>Cue History</summary>
              <div>
                <button type="button" v-on:click="refreshhistory(groupname)">
                  Refresh
                </button>
                <h3>Cue History</h3>
                <table border="1" v-if="groupmeta[groupname].history">
                  <tr>
                    <th>Cue</th>
                    <th>Time</th>
                  </tr>
                  <tr
                    v-for="v of groupmeta[groupname].history"
                    v-bind:key="v[1]">
                    <td>{{ v[0] }}</td>
                    <td>{{ new Date(v[1] * 1000).toLocaleString() }}</td>
                  </tr>
                </table>
              </div>
            </details>

            <div
              v-if="
                groupcues[groupname][selectedCues[groupname]] == undefined ||
                cuemeta[groupcues[groupname][selectedCues[groupname]]] ==
                  undefined
              ">
              Cue data not found...
            </div>

            <div v-if="showevents" style="height: 25em"></div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import {
  formatAllGroups,
  formatCues,
  currentcue,
  currentcueid,
  sys_alerts,
  unixtime,
  boardname,
  shortcuts,
  fixtureAssignments,
  no_edit,
  recentEventsLog,
  soundCards,
  availableTags,
  midiInputs,
  blendModes,
  groupChannelsViewMode,
  fixtureClasses,
  groupfilter,
  keybindmode,
  cuevals,
  useBlankDescriptions,
  slideshow_telemetry,
  showslideshowtelemetry,
  dictView,
  alphas,
  groupmeta,
  groupname,
  editingGroup,
  universes,
  newcuename,
  cuemeta,
  availableCommands,
  selectedCues,
  showPages,
  uiAlertSounds,
  groupcues,
  presets,
  //
  setGroupProperty,
  setCueProperty,
  setCuePropertyDeferred,
  setGroupPropertyDeferred,
  saveToDisk,
  sendGroupEventWithConfirm,
  refreshhistory,
  selectcue,
  selectgroup,
  delgroup,
  go,
  stop,
  setalpha,
  gotoNextCue,
  gotoPreviousCue,
  add_cue,
  clonecue,
  gotonext,
  rmcue,
  jumpToCueWithConfirmationIfNeeded,
  setnext,
  setprobability,
  promptsetnumber,
  setnumber,
  setcrossfade,
  setmqtt,
  setmqttfeature,
  setcommandtag,
  setinfodisplay,
  setbpm,
  tap,
  testSoundCard,
  addRangeEffect,
  addfixToCurrentCue,
  rmFixCue,
  editMode,
  runMode,
  setEventButtons,
  addTimeToGroup,
  lookupFixtureType,
  lookupFixtureColorProfile,
  getChannelCompletions,
  promptRename,
  promptRenameCue,
  deletePreset,
  renamePreset,
  copyPreset,
  savePreset,
  getPresetImage,
  updatePreset,
  channelInfoForUniverseChannel,
  notifyPopupComputedCueLength,
} from "./boardapi.mjs";

import {
  showPresetDialog,
  selectingPresetForDestination,
  selectingPresetFor,
  sc_code,
  shortcut,
  closePreview,
  iframeDialog,
  eventsFilterString,
  newcueu,
  newcuetag,
  newcuevnumber,
  newgroupname,
  addValueToCue,
  addTagToCue,
  addGroup,
} from "./editor.mjs";
import { ref } from "/static/js/thirdparty/vue.esm-browser.js";

import { formatTime } from "./utils.mjs";

let showevents = ref(false);

globalThis.addEventListener(
  "servererrorevent",
  (e) => {
    showevents.value = true;
  },
  false
);

let eventToSendBox = ref("");
let eventTypeToSendSelection = ref("float");
let eventValueToSendBox = ref("");

function sendEvent(where) {
  globalThis.api_link.send([
    "event",
    eventToSendBox.value,
    eventValueToSendBox.value,
    eventTypeToSendSelection.value,
    where,
  ]);
}
</script>

<script type="module">
export default {
  name: "console-app",
  template: "#template",
  components: {
    "combo-box": globalThis.httpVueLoader("/static/vue/ComboBox.vue"),
    "h-fader": globalThis.httpVueLoader("./hfader.vue"),
    "cue-countdown": globalThis.httpVueLoader("./cue-countdown.vue"),
    "cue-table": globalThis.httpVueLoader("./cue-table.vue"),

    // // Currently contains the timers and the display tags for the groups overview
    "group-ui": globalThis.httpVueLoader("./group-ui-controls.vue"),
    "smooth-range": globalThis.httpVueLoader("/static/vue/smoothrange.vue"),
    "media-browser": globalThis.httpVueLoader("./media-browser.vue"),
    "slideshow-telemetry": globalThis.httpVueLoader("./signagetelemetry.vue"),
    "fixture-presets-dialog": globalThis.httpVueLoader(
      "./fixture-presets-dialog.vue"
    ),
    "cue-logic-dialog": globalThis.httpVueLoader("./cue-logic-dialog.vue"),
    "preset-editing-dialog": globalThis.httpVueLoader(
      "./preset-editing-dialog.vue"
    ),
    "cue-media-dialog": globalThis.httpVueLoader("./cue-media-dialog.vue"),
  },
};
</script>
