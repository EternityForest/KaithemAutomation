const css = `

.snackbars {
    display: block;
    position: fixed;
    left: 0;
    bottom: 0;
    width: 100vw;
    height: 0;
    z-index: 100;
    overflow: visible;
}

@scope (.snackbars) {
    :scope{
        --box-bg: var(--grey-2);
        --fg: var(--black-1);
        --border-radius: 20px;
        --control-border-radius: 20px;
    }

    .snackbar {
    position: absolute;
    box-sizing: border-box;
    left: 1.5%;
    bottom: 48px;
    width: 96%;
    transform-origin: center;
    will-change: transform;
    transition: transform 300ms ease, opacity 300ms ease;
    }

    .snackbar[aria-hidden='false'] {
    -webkit-animation: snackbar-show 300ms ease 1;
            animation: snackbar-show 300ms ease 1;
    }

    .snackbar[aria-hidden='true'] {
    -webkit-animation: snackbar-hide 300ms ease forwards 1;
            animation: snackbar-hide 300ms ease forwards 1;
    }

    @-webkit-keyframes snackbar-show {
    from {
        opacity: 0;
        transform: translate3d(0, 100%, 0)
    }
    }

    @keyframes snackbar-show {
    from {
        opacity: 0;
        transform: translate3d(0, 100%, 0)
    }
    }

    @-webkit-keyframes snackbar-hide {
    to {
        opacity: 0;
        transform: translateY(100%);
    }
    }

    @keyframes snackbar-hide {
    to {
        opacity: 0;
        transform: translateY(100%);
    }
    }


    .snackbar--container {
    display: flex;
    flex-wrap: wrap;
    background: var(--box-bg);
    border-radius: var(--border-radius);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
    color: var(--fg);
    cursor: default;
    margin-bottom: 10px;
    }

    .snackbar--text {
    flex: 1 1 auto;
    padding: 16px;
    font-size: 100%;
    border-radius: var(--border-radius) 0px 0px var(--border-radius);
    }

    .snackbar--input {
        height: 36px;
        margin: auto 3px auto 3px;
        flex-grow: 3
    }

    .snackbar--button {
    position: relative;
    flex: 0 1 auto;
    height: 36px;
    margin: auto 3px auto 3px;
    min-width: 5em;
    background: none;
    border: 1px solid;
    border-radius: var(--control-border-radius);
    font-weight: inherit;
    padding-left: 3px;
    padding-right: 3px;

    letter-spacing: 0.02em;
    font-size: 100%;
    text-transform: uppercase;
    text-align: center;
    cursor: pointer;
    overflow: hidden;
    transition: background-color 200ms ease;
    outline: none;
    }
    .snackbar--button:hover {
    background-color: rgba(0, 0, 0, 0.15);
    }
    .snackbar--button:focus:before {
    content: '';
    position: absolute;
    left: 50%;
    top: 50%;
    width: 120%;
    height: 0;
    padding: 0 0 120%;
    margin: -60% 0 0 -60%;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 50%;
    transform-origin: center;
    will-change: transform;
    -webkit-animation: focus-ring 300ms ease-out forwards 1;
            animation: focus-ring 300ms ease-out forwards 1;
    pointer-events: none;
    }
    @-webkit-keyframes focus-ring {
    from {
        transform: scale(0.01);
    }
    }
    @keyframes focus-ring {
    from {
        transform: scale(0.01);
    }
    }
}
`;

let e = document.createElement('style');
e.innerHTML = css;
let h = document.head;
h.insertAdjacentElement('afterbegin', e);

/*@copyright
Modified from https://snackbar.egoist.dev/

The MIT License (MIT)

Copyright (c) EGOIST <0x142857@gmail.com> (https://egoist.sh)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
*/


(function (global, factory) {
    typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
        typeof define === 'function' && define.amd ? define(['exports'], factory) :
            (global = global || self, factory(global.snackbar = {}));
}(undefined, function (exports) {

    function _call(body, then, direct) {

        try {
            var result = Promise.resolve(body());
            return then ? result.then(then) : result;
        } catch (e) {
            return Promise.reject(e);
        }
    }

    function _invokeIgnored(body) {
        var result = body();

        if (result && result.then) {
            return result.then(_empty);
        }
    }

    function _empty() { }

    function _await(value, then, direct) {

        if (!value || !value.then) {
            value = Promise.resolve(value);
        }

        return then ? value.then(then) : value;
    }
    var instances = {
        left: [],
        center: [],
        right: []
    };
    var instanceStackStatus = {
        left: true,
        center: true,
        right: true
    };

    var Snackbar = function Snackbar(message, options) {
        var this$1$1 = this;
        if (options === void 0) options = {};

        var timeout = options.timeout; if (timeout === void 0) timeout = 0;
        var actions = options.actions; if (actions === void 0) actions = [{
            text: 'dismiss',
            callback: function () { return this$1$1.destroy(); }
        }];
        var position = options.position; if (position === void 0) position = 'center';

        var maxStack = options.maxStack; if (maxStack === void 0) maxStack = 3;
        this.message = message;
        this.options = {
            input: options.input || false,
            timeout: timeout,
            actions: actions,
            position: position,
            maxStack: maxStack,
            accent: options.accent || null,
        };
        this.wrapper = this.getWrapper(this.options.position);
        this.insert();
        instances[this.options.position].push(this);
        this.stack();
    };


    Snackbar.prototype.getWrapper = function getWrapper(position) {
        var wrapper = document.querySelector((".snackbars-" + position));

        if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = "snackbars snackbars-" + position;
            document.body.appendChild(wrapper);
        }

        return wrapper;
    };

    Snackbar.prototype.insert = function insert() {
        var this$1$1 = this;

        var el = document.createElement('div');
        el.className = 'snackbar';
        el.setAttribute('aria-live', 'assertive');
        el.setAttribute('aria-atomic', 'true');
        el.setAttribute('aria-hidden', 'false');
        var container = document.createElement('div');
        container.className = 'snackbar--container';



        el.appendChild(container); // Append message

        var text = document.createElement('div');
        text.className = 'snackbar--text';

        if (this.options.accent) {
            text.className += " " + this.options.accent;
        }

        if (typeof this.message === 'string') {
            text.textContent = this.message;
        } else {
            text.appendChild(this.message);
        }

        container.appendChild(text); // Add action buttons


        if (this.options.input) {
            this.inputElement = document.createElement('input');
            this.inputElement.className = 'snackbar--input';

            container.appendChild(this.inputElement);

            setTimeout(() => this.inputElement.focus(), 50);
        }
        if (this.options.actions) {
            var loop = function () {
                var action = list[i];

                var text$1 = action.text;
                var callback = action.callback;
                var button = document.createElement('button');
                button.className = 'snackbar--button';
                button.innerHTML = text$1;

                if (action.accent) {
                    button.className += ' ' + action.accent;
                }

                function click() {
                    this$1$1.stopTimer();

                    if (callback) {
                        callback(button, this$1$1);
                    } else {
                        this$1$1.destroy();
                    }
                }

                if (action.enterKey) {
                    if (this$1$1.inputElement) {
                        this$1$1.inputElement.addEventListener("keyup", function (event) {
                            if (event.key === "Enter") {
                                click();
                            }
                        });
                    }
                }

                button.addEventListener('click', click);
                container.appendChild(button);
            };

            for (var i = 0, list = this$1$1.options.actions; i < list.length; i += 1) loop();
        }

        this.startTimer();
        el.addEventListener('mouseenter', function () {
            this$1$1.expand();
        });
        el.addEventListener('mouseleave', function () {
            this$1$1.stack();
        });
        this.el = el;
        this.wrapper.appendChild(el);
    };

    Snackbar.prototype.stack = function stack() {
        var this$1$1 = this;

        instanceStackStatus[this.options.position] = true;
        var positionInstances = instances[this.options.position];
        var l = positionInstances.length - 1;
        positionInstances.forEach(function (instance, i) {
            // Resume all instances' timers if applicable
            instance.startTimer();
            var el = instance.el;

            if (el) {
                el.style.transform = "translate3d(0, -" + ((l - i) * 15) + "px, -" + (l - i) + "px) scale(" + (1 - 0.05 * (l - i)) + ")";
                var hidden = l - i >= this$1$1.options.maxStack;
                this$1$1.toggleVisibility(el, hidden);
            }
        });
    };

    Snackbar.prototype.expand = function expand() {
        var this$1$1 = this;

        instanceStackStatus[this.options.position] = false;
        var positionInstances = instances[this.options.position];
        var l = positionInstances.length - 1;
        positionInstances.forEach(function (instance, i) {
            // Stop all instances' timers to prevent destroy
            instance.stopTimer();
            var el = instance.el;

            if (el) {
                el.style.transform = "translate3d(0, -" + ((l - i) * el.clientHeight) + "px, 0) scale(1)";
                var hidden = l - i >= this$1$1.options.maxStack;
                this$1$1.toggleVisibility(el, hidden);
            }
        });
    };

    Snackbar.prototype.toggleVisibility = function toggleVisibility(el, hidden) {
        if (hidden) {
            this.visibilityTimeoutId = window.setTimeout(function () {
                el.style.visibility = 'hidden';
            }, 300);
            el.style.opacity = '0';
        } else {
            if (this.visibilityTimeoutId) {
                clearTimeout(this.visibilityTimeoutId);
                this.visibilityTimeoutId = undefined;
            }

            el.style.opacity = '1';
            el.style.visibility = 'visible';
        }
    };
    /**
     * Destory the snackbar
     */


    Snackbar.prototype.destroy = function destroy() {
        var _this = this;

        return _call(function () {
            var el = _this.el;
            var wrapper = _this.wrapper;
            return _invokeIgnored(function () {
                if (el) {
                    // Animate the snack away.
                    el.setAttribute('aria-hidden', 'true');
                    return _await(new Promise(function (resolve) {
                        var eventName = getAnimationEvent(el);

                        if (eventName) {
                            el.addEventListener(eventName, function () { return resolve(); });
                        } else {
                            resolve();
                        }
                    }), function () {
                        wrapper.removeChild(el); // Remove instance from the instances array

                        var positionInstances = instances[_this.options.position];
                        var index = undefined;

                        for (var i = 0; i < positionInstances.length; i++) {
                            if (positionInstances[i].el === el) {
                                index = i;
                                break;
                            }
                        }

                        if (index !== undefined) {
                            positionInstances.splice(index, 1);
                        } // Based on current status, refresh stack or expand style


                        if (instanceStackStatus[_this.options.position]) {
                            _this.stack();
                        } else {
                            _this.expand();
                        }
                    });
                }
            });
        });
    };

    Snackbar.prototype.startTimer = function startTimer() {
        var this$1$1 = this;

        if (this.options.timeout && !this.timeoutId) {
            this.timeoutId = self.setTimeout(function () { return this$1$1.destroy(); }, this.options.timeout);
        }
    };

    Snackbar.prototype.stopTimer = function stopTimer() {
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = undefined;
        }
    };


    function getAnimationEvent(el) {
        var animations = {
            animation: 'animationend',
            OAnimation: 'oAnimationEnd',
            MozAnimation: 'Animationend',
            WebkitAnimation: 'webkitAnimationEnd'
        };

        for (var i = 0, list = Object.keys(animations); i < list.length; i += 1) {
            var key = list[i];

            if (el.style[key] !== undefined) {
                return animations[key];
            }
        }

        return;
    }

    function createSnackbar(message, options) {
        return new Snackbar(message, options);
    }
    function destroyAllSnackbars() {
        var instancesArray = [];
        Object.keys(instances).map(function (position) { return instances[position]; }).forEach(function (positionInstances) { return instancesArray.push.apply(instancesArray, positionInstances); });
        return Promise.all(instancesArray.map(function (instance) { return instance.destroy(); }));
    }

    exports.Snackbar = Snackbar;
    exports.createSnackbar = createSnackbar;
    exports.destroyAllSnackbars = destroyAllSnackbars;

    Object.defineProperty(exports, '__esModule', { value: true });

}));

var snackbar$1 = snackbar;

// SPDX-License-Identifier: MIT


const dataSources = {};
const dataSourceProviders = {};
const filterProviders = {};
const awaitingDataSource = {};

const fullyLoaded = [0];

function addFilterProvider(name, cls) {
  filterProviders[name] = cls;
}

function whenFullyLoaded(f) {
  if (fullyLoaded[0] === 1) {
    f();
  } else {
    document.addEventListener('DOMContentLoaded', function (event) {
      f();
    });
  }
}

document.addEventListener('DOMContentLoaded', function (event) {
  fullyLoaded[0] = 1;
});

function wrapDeferWhenSourceAvailable(name, f) {
  /* Given f, return another function that will call f
     when the data source is available
     */

  // Wrap the function to delay until
  // The page is fully loaded,
  // Even if the data source is available.

  // This is mostly because the filters might not exist.
  // For simplicity, assume filters have no async funny buisiness and
  // Are just hardcoded.

  function deferredWrapper() {
    function runWhenPageLoaded() {
      whenFullyLoaded(function () {
        f();
      });
    }

    const already = [false];

    function makeDataSourceInBg() {
      getDataSource(name);
    }

    function onlyOnceWrapper() {
      // Make sure we only do this once
      // Since we listen to multiple sources
      if (already[0]) {
        return
      }
      already[0] = true;
      runWhenPageLoaded();
    }

    // If data source already exists, just execute
    if (dataSources[name]) {
      onlyOnceWrapper();
      return
    }

    if (!awaitingDataSource[name]) {
      awaitingDataSource[name] = [];
    }
    awaitingDataSource[name].push(onlyOnceWrapper);

    // If provider that can handle the source exists
    // Make it, it will do the rest when ready
    if (name.includes(':')) {
      if (dataSourceProviders[name.split(':')[0]]) {
        makeDataSourceInBg();
      }
    }

    // Provider not found, we'll listen for it later
    if (name.includes(':')) {
      const pname = name.split(':')[0];
      if (!awaitingDataSource[pname + ':*']) {
        awaitingDataSource[pname + ':*'] = [];
      }
      awaitingDataSource[pname + ':*'].push(makeDataSourceInBg);
    }
  }
  return deferredWrapper
}

function whenSourceAvailable(name, f) {
  /* Runs f when the source is available. Source may be a list of names.
      Empty names are ignored.

    */

  if (typeof name === 'string') {
    name = [name];
  }

  for (let i of name) {
    i = i || '';
    if (i.length > 0) {
      f = wrapDeferWhenSourceAvailable(i, f);
    }
  }

  f();
}

async function addDataSourceProvider(name, cls) {
  dataSourceProviders[name] = cls;
  if (awaitingDataSource[name + ':*']) {
    while (awaitingDataSource[name + ':*'].length > 0) {
      await awaitingDataSource[name + ':*'].pop()();
    }
  }
}

function getDataSource(dsName) {
  if (!dataSources[dsName]) {
    const CLS = dataSourceProviders[dsName.split(':')[0]];
    if (!CLS) {
      throw new Error('Unknown data source: ' + dsName)
    }
    const ds = new CLS(dsName, {});
    ds.register();
    ds.autoCreated = true;
  }
  return dataSources[dsName]
}

function getFilter(filterName, prevInChain) {
  // Previous in chain is optional, and may
  // Either be a data source or a filter
  filterName = filterName.trim();
  let f = new filterProviders[filterName.split(':')[0]](filterName, {}, prevInChain);

  if (prevInChain) {
    if (prevInChain.config.readonly)
      f.readonly = true;
  }

  return f
}

class DataSource {
  constructor(name, config) {
    if (dataSources[name]) {
      throw new Error('Duplicate data source name: ' + name)
    }

    this.name = name;
    this.type = 'DataSource';
    this.users = [];
    this.lastPush = 0;

    this.config = config || {};

    this.history = [];
  }

  async getData() {
  }

  async getHistory() {
    return this.history
  }

  async register() {

  }

  async ready() {
    dataSources[this.name] = this;
    if (awaitingDataSource[this.name]) {
      while (awaitingDataSource[this.name].length > 0) {
        await awaitingDataSource[this.name].pop()();
      }
    }
  }

  subscribe(fn) {
    this.users.push(fn);
  }

  unsubscribe(fn) {
    this.users = this.users.filter(user => user !== fn);

    // If there are still no users after 15s, then we remove the data source
    function f() {
      if (this.users.length === 0) {
        if (this.autoCreated) {
          this.close();
          delete picodash.dataSources[this.name];
        }
      }
    }

    if (this._gc_timer) {
      clearInterval(this._gc_timer);
    }
    this._gc_timer = setTimeout(f.bind(this), 15000);
  }

  async pushData(data) {
    /*
        Used to push data to all interested widgets
        */

    // Fix out of order data
    const n = new Date();

    this.history.push([n, data]);
    this.history = this.history.slice(-100);

    if (n < this.lastPush) {
      return
    }

    this.lastPush = n;
    for (const i in this.users) {
      await this.users[i](data);
    }
  }

  close() {
  }
}

class Filter {
  constructor(s, cfg, prev) {
    this.config = cfg;

    // One read only carries forward
    if (prev) {
      if (prev.config.readonly) {
        this.config.readonly = true;
      }
    }

    this.prev = prev;
    s = s.split(':')[1];

    while (s.includes('  ')) {
      s = s.replace('  ', ' ');
    }
    s = s.trim();
    this.args = s.split(' ');
  }

  async get(unfiltered) {
    // Takes a val in unfiltered format and returns a new one in filtered
    return unfiltered
  }

  async set(val) {
    // Takes a val in filter format and returns a new one in unfiltered
    return val
  }

  async close() {

  }
}

const picodash = {
  dataSources,
  whenSourceAvailable,
  dataSourceProviders,
  getDataSource,
  DataSource,
  Filter,
  getFilter,
  addFilterProvider,
  addDataSourceProvider,
  snackbar: snackbar$1
};

class BaseDashWidget extends HTMLElement {
  onData(data) {

  }

  onExtraData(src, data) {

  }

  _subscribeToExtraSource(srcname) {
    const s = this.extraSources[srcname];
    function f(data) {
      this.onExtraData(srcname, data);
    }
    this.extraSourceSubscribers[srcname] = f;
    s.subscribe(f.bind(this));
  }

  connectedCallback() {
    this.innerHTML = 'Awating Data Source';
    async function f() {
      this.source = picodash.getDataSource(this.getAttribute('source'));

      this.extraSources = {};
      this.extraSourceSubscribers = {};

      for (const i of this.getAttributeNames()) {
        if (i.startsWith('source-')) {
          const srcname = i.replace('source-', '');
          this.extraSources[srcname] = picodash.getDataSource(this.getAttribute(i));
          this._subscribeToExtraSource(srcname);
        }
      }

      this.filterStack = [];
      let prevFilter = this.source;

      if (this.getAttribute('filter')) {
        const fs = this.getAttribute('filter').split('|');
        for (const i in fs) {
          prevFilter = picodash.getFilter(fs[i], prevFilter);
          this.filterStack.push(prevFilter);
        }
      }

      async function f(data) {
        data = await this.runFilterStack(data);
        await this.onData(data);
      }

      this.setterFunc = f.bind(this);

      async function push(newValue) {
        const d = await this.runFilterStackReverse(newValue);

        if (d == null || d === undefined) {
          picodash.snackbar.createSnackbar("Value not set!", { accent: 'warning', timeout: 5000 });
          return null
        }

        try {
          await this.source.pushData(d);
        }
        catch (e) {
          picodash.snackbar.createSnackbar("Error setting value!", { accent: 'danger', timeout: 5000 });
          throw e
        }
        return d
      }

      this.pushData = push.bind(this);
      this.source.subscribe(this.setterFunc);
      this.onDataReady();
    }

    const waitFor = [];

    // Get all the sources including the main one,
    // And wait for them to be ready

    for (const i of this.getAttributeNames()) {
      if (i.startsWith('source-')) {
        waitFor.push(this.getAttribute(i));
      }
    }
    waitFor.push(this.getAttribute('source'));
    picodash.whenSourceAvailable(waitFor, f.bind(this));
  }

  async runFilterStackReverse(data) {
    try {
      for (const i in this.filterStack) {
        data = await this.filterStack[this.filterStack.length - 1 - i].set(data);
      }
    }
    catch (e) {
      picodash.snackbar.createSnackbar("Value not set, likely invalid.", { accent: "error", timeout: 3000 });
      throw e
    }
    return data
  }

  async runFilterStack(data) {
    for (const i in this.filterStack) {
      data = await this.filterStack[i].get(data);
    }
    return data
  }

  getActiveConfig() {
    /* Return the config of either the top filter in the stack,
        or the source, if there are no filters.
        */
    if (this.filterStack.length > 0) {
      return this.filterStack[this.filterStack.length - 1].config
    } else {
      return this.source.config
    }
  }

  disconnectedCallback() {
    if (this.source) {
      this.source.unsubscribe(this.setterFunc);
    }

    for (const i in this.filterStack) {
      this.filterStack[i].close();
    }
    for (const j in this.extraSources) {
      this.extraSources[j].unsubscribe(this.extraSourceSubscribers[j]);
    }
  }

  async refresh() {
    let data = await this.source.getData();
    data = await this.runFilterStack(data);
    return data
  }
}

picodash.BaseDashWidget = BaseDashWidget;

class ButtonDashWidget extends BaseDashWidget {
    async onData(data) {
        try {
            this.data = parseFloat(data);
        } catch (e) {
            console.log(e);
        }
    }

    async onDataReady() {
        this.innerHTML = '';
        this.appendChild(this.buttonEl);

        this.dummy = () => { };

        const x = await this.refresh();
        await this.onData(x);
    }

    connectedCallback() {
        const x = [];
        const b = document.createElement('button');
        this.buttonEl = b;

        // Move elements *before* the superclass adds the placeholder.
        for (var i of this.childNodes) {
            x.push(i);
        }
        for (var i of x) {
            this.removeChild(i);
            this.buttonEl.appendChild(i);
        }

        super.connectedCallback();

        b.onclick = async () => {
            if (this.extraSources.pressed) {
                v = await this.extraSources.pressed.getData();
            } else {
                var v = this.data + 1;
            }

            await this.pushData(v);
        };
        this.appendChild(b);

        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                if (mutation.addedNodes.length) {
                    for (const n of mutation.addedNodes) {
                        if (n.nodeName != 'BUTTON') {
                            this.removeChild(n);
                            this.buttonEl.appendChild(n);
                        }
                    }
                }
            });
        });

        observer.observe(this, { childList: true });
    }
}
customElements.define('ds-button', ButtonDashWidget);

class SpanDashWidget extends BaseDashWidget {
    async onData(data) {
        let unit = this.getActiveConfig().unit || '';
        this.innerText = data + unit;
    }

    async onDataReady() {
        const x = await this.refresh();
        await this.onData(x);
    }
}
customElements.define('ds-span', SpanDashWidget);

class MeterDashWidget extends BaseDashWidget {
    async onDataReady() {
        const m = document.createElement('meter');
        this.meter = m;
        const cfg = this.getActiveConfig();

        this.meter.min = cfg.min || this.getAttribute('min') || -1;
        this.meter.max = cfg.max || this.getAttribute('max') || 1;
        this.meter.high = cfg.high || this.getAttribute('high') || 1000000000;
        this.meter.low = cfg.low || this.getAttribute('low') || -1000000000;
        this.meter.style.width = '100%';
        this.innerHTML = '';
        this.appendChild(m);

        const x = await this.refresh();
        await this.onData(x);
    }

    async onData(data) {
        this.meter.value = data;
    }
}

customElements.define('ds-meter', MeterDashWidget);

class InputDashWidget extends picodash.BaseDashWidget {
    async onData(data) {
        if (this.input.type == 'checkbox') {
            if (data == true) {
                data = true;
            }
            else if (data == false) {
                data = false;
            }
            else {
                data = parseFloat(data) > 0;
            }
            this.input.checked = data;
        }
        else {
            if (data == true) {
                data = 1;
            }
            if (data == false) {
                data = 0;
            }
            this.input.value = data;
        }
        this.lastVal = data;
    }

    async onDataReady() {
        const cfg = this.getActiveConfig();

        this.input = document.createElement('input');
        if (cfg.readonly) {
            this.input.disabled = true;
        }

        for (const i of ['min', 'max', 'high', 'low']) {
            var x = cfg[i] || this.getAttribute(i);

            if (typeof x !== 'undefined') {
                this.input[i] = x;
            }
        }

        let stp = cfg.step || 0.000001;

        if (!this.getAttribute('step')) {
            if (stp == parseInt(stp)) {
                stp=stp;
            }
            else {
                stp = "any";
            }
        }
        else {
            this.getAttribute('step');
        }

        this.input.className = this.className || '';
        this.className = '';

        this.input.type = this.getAttribute('type') || 'text';
        this.input.disabled = this.input.disabled || this.getAttribute('disabled') || false;
        this.input.placeholder = this.getAttribute('placeholder') || '';

        if(this.input.type == 'number'){
            this.input.step = stp;
        }

        if (this.getAttribute('list')) {
            this.input.list = this.getAttribute('list') || '';
        }

        this.innerHTML = '';
        this.appendChild(this.input);
        this.style.display = 'contents';

        async function f(e) {
            let v = null;

            if (this.input.type == 'checkbox') {
                v = this.input.checked;
            }
            else {
                v = this.input.value;
            }

            if (this.input.type == 'number') {
                v = parseFloat(v);
            }

            if (this.input.type == 'checkbox') {
                if (v == true) {
                    v = true;
                }
                else if (v == false) {
                    v = false;
                }
                else {
                    v = parseFloat(v) > 0;
                }
            }

            // Get before set, some filters need to know the latest value
            await this.refresh();
            let rc = await this.pushData(v);

            // Setting failed, return to the last good value
            if (rc == null) {
                if (this.input.type == 'checkbox') {
                    this.input.checked = this.lastVal;
                }
                else {
                    this.input.value = this.lastVal;
                }
            }
        }
        this.input.onchange = f.bind(this);
        var x = await this.refresh();
        await this.onData(x);
    }
}
customElements.define('ds-input', InputDashWidget);

class LogWindowDashWidget extends BaseDashWidget {
    onData(data, timestamp) {
        const v = document.createElement('article');
        const p = document.createElement('p');
        const h = document.createElement('header');

        const d = new Date();
        h.innerText = d.toLocaleString();
        p.innerText = data;
        v.appendChild(h);

        v.appendChild(p);

        this.insertBefore(v, this.children[0]);

        if (this.childElementCount > 100) {
            this.removeChild(this.children[this.childElementCount - 1]);
        }
    }

    async onDataReady() {
        this.innerHTML = '';
        const history = await this.source.getHistory();

        for (const i in history) {
            const v = document.createElement('article');
            const p = document.createElement('p');
            const h = document.createElement('header');

            const d = history[i][0];
            h.innerText = d.toLocaleString();

            let txt = history[i][1];
            txt = await this.runFilterStack(txt);
            if (txt == null || txt === undefined) {
                continue
            }

            p.innerText = txt;
            v.appendChild(h);

            v.appendChild(p);
            this.insertAdjacentElement('afterbegin', v);
        }
    }
}
customElements.define('ds-logwindow', LogWindowDashWidget);

class RandomDataSource extends picodash.DataSource {
  constructor(name, config) {
    super(name, config);

    this.config.min = 0;
    this.config.max = 1;
    this.config.high = 0.9;
    this.config.low = 0.1;

    function upd() {
      this.pushData(Math.random() * 2 - 1);
    }
    this.interval = setInterval(upd.bind(this), 1000);
  }

  async getData() {
    return Math.random() * 2 - 1
  }

  async close() {
    if (this.interval) {
      clearInterval(this.interval);
    }
  }

  async register() {
    super.register();
    super.ready();
  }
}

class FixedDataSource extends picodash.DataSource {
  constructor(name, config) {
    super(name, config);
    this.config.readonly = true;
    this.data = JSON.parse(name.split(':')[1] || '');
  }

  async getData() {
    return this.data
  }

  async pushData(data) {
    // Don't allow changes.
    data = this.data;
    super.pushData(data);
  }

  async register() {
    super.register();
    super.ready();
  }
}

class SimpleVariableDataSource extends picodash.DataSource {
  constructor(name, config) {
    super(name, config);
    this.data = config.default || '';
  }

  async getData() {
    return this.data
  }

  async pushData(data) {
    this.data = data;
    super.pushData(data);
  }

  async register() {
    super.register();
    super.ready();
  }
}

class PromptDataSource extends picodash.DataSource {
  constructor(name, config) {
    super(name, config);
    this.prompt = name.split(":")[1];
    this.config.readonly = true;
  }

  async getData() {
    // Get rid of the old one if any
    if (this.cancel) {
      this.cancel();
      this.cancel = null;
    }

    let _this = this;
    const promise1 = new Promise((resolve, reject) => {


      let sb = picodash.snackbar.createSnackbar(_this.prompt, {
        input: true,
        actions: [
          {
            text: 'Confirm',
            enterKey: true,
            callback(button, snackbar) {
              snackbar.destroy();
              resolve(snackbar.inputElement.value);
            }
          },
          {
            text: 'Cancel',
            callback(button, snackbar) {
              snackbar.destroy();
              resolve(null);
            }
          }
        ]
      });

      function cancel() {
        sb.destroy();
        resolve(null);
      }

      this.cancel = cancel;

    });

    return promise1
  }

  async pushData(data) {
    throw new Error("Not pushable")
  }

  async register() {
    super.register();
    super.ready();
  }
}

picodash.addDataSourceProvider('random', RandomDataSource);
picodash.addDataSourceProvider('fixed', FixedDataSource);
picodash.addDataSourceProvider('prompt', PromptDataSource);

picodash.SimpleVariableDataSource = SimpleVariableDataSource;

class Snackbar extends picodash.Filter {
  constructor(s, cfg, prev) {
    super(s, cfg, prev);
    if (prev) {
      this.config = prev.config;
    }
    this.lastData = null;

    this.str = s.split(":")[1];
  }

  async notify() {
    picodash.snackbar.createSnackbar(this.str, { timeout: 5000 });
  }

  async get(unfiltered) {
    // Convert from unfiltered to filtered

    if (this.lastData != null) {
      if (this.lastData != unfiltered) {
        this.notify();
      }
    }

    this.lastData = unfiltered;
    return this.lastData
  }

  async set(val) {
    return (await this.get(val))
  }
}


picodash.addFilterProvider('notify', Snackbar);


class Vibrate extends Snackbar {
  async notify() {
    navigator.vibrate(200);
  }
}

picodash.addFilterProvider('vibrate', Vibrate);



class Confirm extends picodash.Filter {
  constructor(s, cfg, prev) {
    super(s, cfg, prev);
    if (prev) {
      this.config = prev.config;
    }
    this.str = s.split(":")[1];

    this.cancel = null;
  }


  async get(unfiltered) {
    return unfiltered
  }

  async set(val) {

    // Get rid of the old one if any
    if (this.cancel) {
      this.cancel();
      this.cancel = null;
    }

    let _this = this;
    const promise1 = new Promise((resolve, reject) => {


      let sb = picodash.snackbar.createSnackbar(_this.str, {
        actions: [
          {
            text: 'Confirm',
            callback(button, snackbar) {
              snackbar.destroy();
              resolve(val);
            }
          },
          {
            text: 'Cancel',
            callback(button, snackbar) {
              snackbar.destroy();
              resolve(null);
            }
          }
        ]
      });

      function cancel() {
        sb.destroy();
        resolve(null);
      }

      this.cancel = cancel;

    });

    return promise1
  }
}

picodash.addFilterProvider('confirm', Confirm);


class Mult extends picodash.Filter {
  constructor(s, cfg, prev) {
    super(s, cfg, prev);
    this.m = parseFloat(this.args[0]);

    // Multiply config vals, so that widgets know
    // the range.
    for (const i of ['min', 'max', 'high', 'low', 'step']) {
      if (typeof prev.config[i] !== 'undefined') {
        this.config[i] = prev.config[i] * this.m;
      }
    }
  }

  async get(unfiltered) {
    // Convert from unfiltered to filtered
    return unfiltered * this.m
  }

  async set(val) {
    // Convert from filtered to unfiltered
    return val / this.m
  }
}

class FixedPoint extends picodash.Filter {
  constructor(s, cfg, prev) {
    super(s, cfg, prev);
    if (prev) {
      this.config = prev.config;
    }

    this.m = parseInt(this.args[0]);
  }

  async get(unfiltered) {
    // Convert from unfiltered to filtered
    try {
      return unfiltered.toFixed(parseFloat(this.m))
    } catch (e) {
      console.log(e);
      return 'NaN'
    }
  }

  async set(val) {
    // Convert from filtered to unfiltered
    return parseFloat(val)
  }
}

class Offset extends picodash.Filter {
  constructor(s, cfg, prev) {
    super(s, cfg, prev);
    this.m = parseFloat(this.args[0]);
    // Multiply config vals, so that widgets know
    // the range.

    for (const i of ['min', 'max', 'high', 'low']) {
      if (typeof prev.config[i] !== 'undefined') {
        this.config[i] = prev.config[i] + this.m;
      }
    }

    if (typeof prev.config.step !== 'undefined') {
      this.config.step = prev.config.step;
    }
  }

  async get(unfiltered) {
    // Convert from unfiltered to filtered
    return unfiltered + this.m
  }

  async set(val) {
    // Convert from filtered to unfiltered
    return val - this.m
  }
}


class Nav extends picodash.Filter {
  constructor(s, cfg, prev) {
    super(s, cfg, prev);
    this.k = parseFloat(this.args[0]) || this.args[0];
    this.lastFullData = null;
  }

  async get(unfiltered) {
    // Convert from unfiltered to filtered
    this.lastFullData = unfiltered;
    return unfiltered[this.k]
  }

  async set(val) {
    // Convert from filtered to unfiltered
    if (this.lastFullData == null) {
      throw new Error("Filter does not have a cached value to set.")
    }
    let v = structuredClone(this.lastFullData);
    v[this.k] = val;
    return v
  }
}

class JsonStringify extends picodash.Filter {
  constructor(s, cfg, prev) {
    super(s, cfg, prev);
  }

  async get(unfiltered) {
    // Convert from unfiltered to filtered
    return JSON.stringify(unfiltered, null, 2)
  }

  async set(val) {
    // Convert from filtered to unfiltered
    return JSON.parse(val)
  }
}

picodash.addFilterProvider('fixedpoint', FixedPoint);
picodash.addFilterProvider('offset', Offset);
picodash.addFilterProvider('mult', Mult);
picodash.addFilterProvider('nav', Nav);
picodash.addFilterProvider('json', JsonStringify);

/*
@copyright
SPDX - FileCopyrightText: Copyright 2024 Daniel Dunn
SPDX-License-Identifier: MIT
*/

export { picodash as default };
