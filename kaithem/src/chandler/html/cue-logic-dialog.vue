<style scoped></style>

<template>
  <div
    class="window w-full modal"
    popover
    id="cueLogicDialog"
    ontoggle="globalThis.handleDialogState(event)"
    v-if="currentcue && editinggroup">
    <header>
      <div class="tool-bar">
        <h4>{{ currentcue.name }} Logic</h4>
        <button
          class="nogrow"
          data-testid="close-logic"
          type="button"
          popovertarget="cueLogicDialog"
          popovertargetaction="hide">
          <i class="mdi mdi-close"></i>Close
        </button>
      </div>
    </header>

    <div>
      <h3>Automation Logic</h3>
      <details class="help">
        <summary><i class="mdi mdi-help-circle-outline"></i></summary>
        <p>
          Here you can create rules that apply whenever the group is in this
          cue, to do things like trigger other cues when this one enters or
          exits.
        </p>

        <p>
          Action parameters can use spreadsheet-style =expressions. The special
          function tv('name') or stv('name') gets the value of a tag or string
          tag.
        </p>

        <p>
          The variables "event.name", "event.value", and "event.time" are
          available to get info on the event that triggered a rule.
        </p>
      </details>
    </div>
    <div class="card w-sm-full" style="overflow: visible">
      <label
        >Inherit rules from
        <div style="overflow: visible">
          <combo-box
            :modelValue="currentcue.inheritRules"
            :disabled="editinggroup.name == '__rules__' || no_edit"
            @change="
              setcueproperty(
                currentcue.id,
                'inheritRules',
                $event
              )
            "
            :options="
              useBlankDescriptions(groupcues[editinggroup.id])
            "></combo-box>
        </div>
        <p>Inherited rules run after directly set rules.</p>
        <p>
          If a cue named __rules__ exists, <br />
          all cues will additionally inherit from that cue.
        </p>
      </label>
    </div>
    <hr />

    <script-editor
      :completers="completers"
      v-bind:example_events="example_events"
      :modelValue="currentcue.rules"
      @update:model-value="setcueproperty(currentcue.id, 'rules', $event)"
      v-bind:commands="availablecommands"
      v-bind:groups="cueNamesByGroupName()"
      v-bind:vars="editinggroup.vars"
      v-bind:parentgroup="editinggroup.name"
      :disabled="no_edit">
    </script-editor>

    <div style="display: flex; flex-wrap: wrap">
      <div
        style="
          border-style: solid;
          flex-grow: 3;
          margin: 0.5em;
          padding: 0.5em;
        ">
        <h3>Group Variables</h3>
        <table border="1">
          <tr v-for="(v, i) in editinggroup.vars" :key="i">
            <td>{{ i }}</td>
            <td>{{ v }}</td>
          </tr>
        </table>
      </div>

      <div
        style="
          border-style: solid;
          flex-grow: 1;
          margin: 0.5em;
          padding: 0.5em;
        ">
        <h3>Timers</h3>
        <table border="1" style="width: 98%">
          <tr v-for="(v, i) in editinggroup.timers" :key="i + v">
            <td>{{ i }}</td>
            <td
              style="width: 8em"
              v-bind:class="{
                warning: v - unixtime < 60,
                blinking: v - unixtime < 5,
              }">
              {{ formatInterval(v - unixtime) }}
            </td>
          </tr>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
import { dictView, useBlankDescriptions, formatInterval } from "./utils.mjs";

const example_events_base = [
  ["now", "Run when script loads"],
  ["cue.exit", "When exiting the cue"],
  ["cue.enter", "When entering a cue"],
  ["=tv('TagPointName')", "Run when tag point is nonzero"],
  [
    "=/tv('TagPointName')",
    "Run when tag point newly becomes nonzero(edge trigger)",
  ],
  ["=~tv('TagPointName')", "Run when tag point changes"],
  [
    "=+tv('TagPointName')",
    "Run when changes and is not zero(Counter/bang trigger)",
  ],
  ["button.a", "A button in groups sidebar"],
  [
    "keydown.a",
    "When a lowercase A is pressed in the Send Events mode on the console",
  ],
  [
    "=log(90)",
    "Example polled expression. =Expressions are polled every few seconds or on certain triggers.",
  ],
  ["@january 5th", "Run every jan 5 at midnight"],
  ["@every day at 2am US/Pacific", "Time zones supported"],
  ["@every 10 seconds", "Simple repeating trigger"],
  ["=isNight()", "Run if it is nighttime(polled)"],
  ["=isNight()", "Run if it is nighttime(polled)"],
  [
    "=tv('/system/alerts.level') >= 30 ",
    "Run if the highest priority alert is warning(30), error(40), or critical(50) level",
  ],
  ["=isDark()", "Run if it is civil twilight"],
  [
    "script.poll",
    "Run every fast(~24Hz) polling cycle of the script, not the same as =expressions",
  ],
];

export default {
  template: "#template",

  props: [
    "currentcue",
    "editinggroup",
    "no_edit",
    "setcueproperty",
    "groupmeta",
    "groupcues",
    "availabletags",
    "availablecommands",
    "unixtime",
  ],
  data: function () {
    let d = {};
    d.gotoGroupCuesCompleter = this.gotoGroupCuesCompleter.bind(this);
    d.gotoGroupNamesCompleter = this.gotoGroupNamesCompleter.bind(this);
    d.cueNamesByGroupName = this.cueNamesByGroupName.bind(this);
    d.defaultExpressionCompleter = this.defaultExpressionCompleter.bind(this);
    d.tagPointsCompleter = this.tagPointsCompleter.bind(this);
    return { completers: d };
  },
  methods: {
    dictView: dictView,
    useBlankDescriptions: useBlankDescriptions,
    formatInterval: formatInterval,

    gotoGroupNamesCompleter: function (_dummy) {
      let c = [["=GROUP", "This group"]];

      let x = this.groupmeta;

      if (!x) {
        return [];
      }

      for (let i in x) {
        c.push([x[i].name, ""]);
      }
      return c;
    },

    gotoGroupCuesCompleter: function (a) {
      let c = [];
      let n = a[1];
      if (n.includes("=GROUP")) {
        n = this.editinggroup.name;
      }

      for (let i in this.groupmeta) {
        let s = this.groupmeta[i];
        if (s.name == n) {
          n = i;
          break;
        }
      }

      let x = this.groupcues[n];

      if (!x) {
        return [];
      }

      for (let i in x) {
        c.push([i, ""]);
      }
      c.push(["__next__", "Next cue"], ["__random__", ""], ["__shuffle__", ""]);

      return c;
    },

    tagPointsCompleter: function (_a) {
      let c = [];
      for (let i in this.availabletags) {
        c.push([i, ""]);
      }
      return c;
    },

    defaultExpressionCompleter: function (_a) {
      let c = [
        ["1", "Literal 1"],
        ["0", ""],
        ["=1+2+3", "Spreadsheet-style expression"],
        ['=tv("TagName")', "Get the value of TagName(0 if nonexistant)"],
        [
          '=stv("TagName")',
          "Get the value of a string tagpoint(empty if nonexistant)",
        ],
        ["=random()", "Random from 0 to 1"],
        ["=GROUP", "Name of the group"],
      ];
      for (let i in this.availabletags) {
        c.push(['=tv("' + i + '")', ""]);
      }
      return c;
    },

    cueNamesByGroupName: function () {
      let d = {};
      for (let i in this.groupmeta) {
        d[this.groupmeta[i].name] = [];

        for (let j in this.groupcues[i]) {
          d[this.groupmeta[i].name].push(j);
        }
      }
      return d;
    },
  },
  components: {
    "combo-box": globalThis.httpVueLoader("/static/vue/ComboBox.vue"),
    "script-editor": globalThis.httpVueLoader("./script-editor.vue"),
  },
  computed: {
    example_events: function () {
      let event_ = [];

      for (let i in example_events_base) {
        event_.push(example_events_base[i]);
      }

      for (let n in this.availabletags) {
        let i = this.availabletags[n];
        event_.push(["=tv('" + n + "')", "While tag is nonzero"]);
        if (i == "trigger") {
          event_.push(["=+tv('" + n + "')", "On every nonzero change"]);
        }
        if (i == "bool") {
          event_.push([
            "=/tv('" + n + "')",
            "When tag newly becomes nonzero(edge trigger)",
          ]);
        }
      }

      return event_;
    },
  },
};
</script>
