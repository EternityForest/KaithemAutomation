import { encode, decode } from './thirdparty/msgpackr.esm.js';
import picodash from './thirdparty/picodash/picodash-base.esm.js'

try { globalThis.kaithemapi } catch { globalThis.kaithemapi = undefined }

if (globalThis.kaithemapi == undefined) {

	var KaithemWidgetApiSnackbar = function (m, d) {
		picodash.snackbar.createSnackbar(m, (d || 10) * 1000);
	}

	globalThis.kaithemapi = function () {
		var x = {


			checkPermission: async function (perm) {
				let permissionurl = "/api.core/check-permission/" + perm

				return fetch(permissionurl, {
					method: "GET",
				}).then(response => {
					return response.json()
				})
			},

			toSend: [],
			enableWidgetGoneAlert: true,
			lastDidSnackbarError: 0,
			first_error: 1,
			serverMsgCallbacks: {
				"__WIDGETERROR__": [
					function (m) {
						console.error(m);
						if (lastDidSnackbarError < Date.now() + 60_000) {
							lastDidSnackbarError = Date.now()
							KaithemWidgetApiSnackbar("Ratelimited msg" + m)
						}
					}
				],
				"__SHOWMESSAGE__": [
					function (m) {
						alert(m);
					}
				],
				"__SHOWSNACKBAR__": [
					function (m) {
						KaithemWidgetApiSnackbar(m[0], m[1]);
					}
				],

				"__KEYMAP__": [
					function (m) {
						globalThis.uuidToWidgetId[m[0]] = m[1];
						globalThis.widgetIDtoUUID[m[1]] = m[0];
					}
				],

				"__FORCEREFRESH__": [
					function (m) {
						globalThis.location.reload();
					}
				]


			},

			//Unused for now
			uuidToWidgetId: {},
			widgetIDtoUUID: {},


			subscriptions: [],
			connection: 0,
			use_mp: 0,

			//Doe nothinh untiul we connect, we just send that buffered data in the connection handler.
			//Todo don't dynamically define this at all?
			poll_ratelimited: function () {},

			subscribe: function (key, callback) {


				if (key in this.serverMsgCallbacks) {
					this.serverMsgCallbacks[key].push(callback);
				}

				else {
					this.serverMsgCallbacks[key] = [callback];
				}

				//If the ws is open, send the subs list, else wait for the connection handler to do it when we first reconnect.
				if (this.connection && this.connection.readyState == 1) {
						var j = { "subsc": Object.keys(this.serverMsgCallbacks), "upd": [] }
						this.connection.send(JSON.stringify(j))
					}
			},

			unsubscribe: function (key, callback) {
				var array = this.serverMsgCallbacks[key];


				if (key in array) {

					for (var i = 0; i < array.length; i++) { if (array[i] === callback) { array.splice(i, 1); } }
				}

				if (array.length === 0) {

					//Delete the now unused mapping
					if (key in this.uuidToWidgetId) {
						delete this.widgetIDtoUUID[this.uuidToWidgetId[key]];
						delete this.uuidToWidgetId[key];
					}



					delete this.serverMsgCallbacks[key]


					//If the ws is open, send the subs list. If not, we by definition aren't subscribed, and we already removed it from the local list.
					if (this.connection && this.connection.readyState == 1) {
							var j = { "unsub": [key], "upd": [] }
							this.connection.send(JSON.stringify(j))
						}
				}
			},

			sendErrorMessage: function (error) {
				if (this.lastErrMsg && this.lastErrMsg > (Date.now() - 10_000)) {
						return
					}
				this.lastErrMsg = Date.now();

				try {
					error = error+"\n"+error.stack
				}
				catch (error_) {
					console.error(error_)
				}

				this.sendValue("__ERROR__", error)


			},

			register: function (key, callback) {
				this.subscribe(key, callback);
			},

			setValue: function (key, value) {
				this.toSend.push([key, value])
				this.poll_ratelimited();
			},

			sendValue: function (key, value) {
				this.toSend.push([key, value])
				this.poll_ratelimited();
			},

			sendTrigger: function (key, value) {
				var d = { 'upd': [[key, value]] };
				if (this.use_mp0) {
					var j = new Blob([encode(d)]);
				}
				else {
					var j = JSON.stringify(d);
				}

				this.connection.send(j);
			},

			wsPrefix: function () {
				return globalThis.location.protocol.replace("http", "ws") + "//" + globalThis.location.host
			},

			can_show_error: 1,
			usual_delay: 0,
			last_connected: 0,
			reconnect_timeout: 1500,

			reconnector: null,
			// Very first time, give it some extra before clearing old msgs
			lastDisconnect: Date.now() + 15_000,

			connect: function () {
				var apiobj = this

				this.connection = new WebSocket(globalThis.location.protocol.replace("http", "ws") + "//" + globalThis.location.host + '/widgets/ws');

				this.connection.addEventListener('close', function (e) {


					picodash.snackbar.createSnackbar("Lost connection to server", {
						timeout: 5000,
						accent: 'error'
					});


					apiobj.lastDisconnect = Date.now();
					console.log(e);
					if (apiobj.reconnector) {
						clearTimeout(apiobj.reconnector)
						apiobj.reconnector = null;
					}
					apiobj.reconnector = setTimeout(function () { apiobj.connect() }, apiobj.reconnect_timeout);
				});

				this.connection.onerror = function (e) {
					apiobj.lastDisconnect = Date.now();
					console.log(e);
					if (apiobj.reconnector) {
						clearTimeout(apiobj.reconnector)
						apiobj.reconnector = null;
					}
					if (apiobj.connection.readyState != 1) {
						apiobj.reconnect_timeout = Math.min(apiobj.reconnect_timeout * 2, 20_000);
						apiobj.reconnector = setTimeout(function () { apiobj.connect() }, apiobj.reconnect_timeout);
					}
				};


				this.connection.onmessage = function (e) {
					try {
						if (typeof (e.data) == 'object') {
							apiobj.use_mp = 1;

							var resp = [0];
							e.data.arrayBuffer().then(function (buffer) {
								var buffer2 = new Uint8Array(buffer);
								try {
									apiobj.connection.handleIncoming(decode(buffer2));
								}
								catch (error) {
									apiobj.sendErrorMessage(globalThis.location.href + "\n" + error.stack)
									console.error(error.stack)
								}
							})

						}
						else {
							var resp = JSON.parse(e.data);
							apiobj.connection.handleIncoming(resp)
						}
					}
					catch (error) {
						apiobj.sendErrorMessage(globalThis.location.href + "\n" + error.stack)
						console.error(error.stack)
					}


				}

				this.connection.handleIncoming = function (resp) {
					//Iterate messages
					for (let i of resp) {
						for (var j in apiobj.serverMsgCallbacks[i[0]]) {
							if (i.length > 1) {
								apiobj.serverMsgCallbacks[i[0]][j](i[1]);
							}
							else {
								if (this.alreadyPostedAlertOnce) {}
								else {
									this.alreadyPostedAlertOnce = true
									if (this.enableWidgetGoneAlert) {
										alert("A widget used by this page no longer exists on the server.  Try refreshing later.")
									}
								}
							}
						}
					}
				}
				this.connection.addEventListener('open', function (e) {

					try {
						if (apiobj.last_connected) {
							picodash.snackbar.createSnackbar("Reconnected", {
								timeout: 5000,
								accent: 'success'
							});
						}
					}
					catch (error) {
						console.log(error)
					}

					apiobj.last_connected = Date.now();

					// Do not send very old messages on reconnect
					if (apiobj.lastDisconnect < (Date.now() - 5000)) {
						apiobj.toSend = [];
					}

					var j = JSON.stringify({ "subsc": Object.keys(apiobj.serverMsgCallbacks), "req": [], "upd": [["__url__", globalThis.location.href]] })
					apiobj.connection.send(j)
					console.log("WS Connection Initialized");
					apiobj.reconnect_timeout = 1500;
					globalThis.setTimeout(function () { apiobj.wpoll() }, 250);
				})

				this.wpoll = function () {
					//Don't bother sending if we aren'y connected
					if (this.connection.readyState == 1 && this.toSend.length > 0) {
							var toSend = { 'upd': this.toSend, };
							if (this.use_mp0) {
								var j = new Blob([encode(toSend)]);
							}
							else {
								var j = JSON.stringify(toSend);
							}

							this.connection.send(j);
							this.toSend = [];
						}

					if (this.toSend && (this.toSend.length > 0)) {
						globalThis.setTimeout(this.poll_ratelimited.bind(this), 120);
					}

				}

				this.lastSend = 0
				this.pollWaiting = null

				//Check if wpoll has ran in the last 44ms. If not run it.
				//If it has, set a timeout to check again.
				//This code is only possible because of the JS single threadedness.
				this.poll_ratelimited = function () {
					var d = new Date();
					var n = d.getTime();

					if (n - this.lastSend > 44) {
						this.lastSend = n;
						this.wpoll()
					}
					//If we are already waiting on a poll, don't re-poll.
					else {
						if (this.pollWaiting) {
							clearTimeout(this.pollWaiting)
						}
						this.pollWaiting = setTimeout(this.poll_ratelimited.bind(this), 50 - (n - this.lastSend))
					}
				}



			}
		}
		x.self = x
		return x
	}
	globalThis.kaithemapi = globalThis.kaithemapi()

	if (!globalThis.onerror) {
		var globalPageErrorHandler = function (message, url, line, col, tb) {
			globalThis.kaithemapi.sendErrorMessage(url + '\n' + line + "\n\n" + message + "\n\n" + tb);
		}
		globalThis.addEventListener("unhandledrejection", event => {
			globalThis.kaithemapi.sendErrorMessage(`UNHANDLED PROMISE REJECTION: ${event.reason}`);
		});

		globalThis.onerror = globalPageErrorHandler
	}
	//Backwards compatibility hack
	//Todo deprecate someday? or not.
	let __kwidget_doBattery = function () {
		if (!navigator.userAgent.includes("Firefox")) {

			try {
				navigator.getBattery().then(function (battery) {
					globalThis.kaithemapi.sendValue("__BATTERY__", { 'level': battery.level, 'charging': battery.charging })
				});
			}
			catch (error) {
				console.log(error)
			}

			try {
				if ('AmbientLightSensor' in globalThis) {
					const sensor = new AmbientLightSensor();
					sensor.addEventListener('reading', event => {
						globalThis.kaithemapi.sendValue("__SENSORS__", { 'ambientLight': sensor.illuminance })
					});
				}
			}
			catch {
				console.log(e);
			}
		}
	}

	if (!navigator.userAgent.includes("Firefox")) {
		try {
			navigator.permissions.query({ name: 'idle-detection' }).then(async function (result) {
				if (result.state === 'granted') {
					try {
						const controller = new AbortController();
						const signal = controller.signal;

						const idleDetector = new IdleDetector();
						idleDetector.addEventListener('change', () => {
							const userState = idleDetector.userState;
							const screenState = idleDetector.screenState;
							globalThis.kaithemapi.sendValue("__USERIDLE__", { 'userState': userState, 'screenState': screenState })

						});

						await idleDetector.start({
							threshold: 240_000,
							signal,
						});
					} catch (error) {
						// Deal with initialization errors like permission denied,
						// running outside of top-level frame, etc.
						console.error(error.name, error.message);
					}
				}
			});
		}
		catch {
			//No logging, FF would spam a bunch of logs
			//console.log(e)
		}
	}

	setTimeout(__kwidget_doBattery, 60)
	setInterval(__kwidget_doBattery, 1_800_000)

	window.addEventListener('load', function () {
		setTimeout(function () { globalThis.kaithemapi.connect() }, 10)
	})
}

class APIWidget {
	constructor(uuid, handler, defer_connect) {
		this.uuid = uuid
		this.value = "Waiting..."
		this.clean = 0;
		this._maxsyncdelay = 250
		this.timeSyncInterval = 120 * 1000;

		this._timeref = null;

		if (handler) {
			this.upd = handler;
		}

		if (!defer_connect) {
			this.connect();
		}
	}

	connect() {
		kaithemapi.subscribe("_ws_timesync_channel", this.onTimeResponse)
		kaithemapi.subscribe(this.uuid, this._upd.bind(this));
		setTimeout(this.getTime.bind(this), 500)
	}
	onTimeResponse(value) {
		{
			if (Math.abs(value[0] - this._txtime) < 0.1) {
				{
					var t = performance.now();
					if (t - this._txtime < this._maxsyncdelay) {
						{
							this._timeref = [(t + this._txtime) / 2, value[1]]

							this._maxsyncdelay = (t - this._txtime) * 1.2;
						}
					}
					else {
						{

							this._maxsyncdelay = this._maxsyncdelay * 2;
						}
					}
				}
			}
		}
	}

	_upd(value) {
		{
			if (this.clean == 0) {
				{
					this.value = value;
				}
			}
			else {
				{
					this.clean -= 1;
				}
			}
			this.upd(value)
		}
	}

	upd(value) {
		{}
	}
	getTime() {
		{
			var x = performance.now()
			this._txtime = x;
			kaithemapi.sendValue("_ws_timesync_channel", x)
		}
	}


	now(value) {
		{
			var t = performance.now()
			if (t - this._txtime > this.timeSyncInterval) {
				{
					this.getTime();
				}
			}
			if (this._timeref == null) {
				return Date.now();
			}
			return ((t - this._timeref[0]) + this._timeref[1])
		}
	}

	set(value) {
		{
			kaithemapi.setValue(this.uuid, value);
			this.clean = 2;
		}
	}

	send(value) {
		{
			kaithemapi.sendValue(this.uuid, value);
			this.clean = 2;
		}
	}
}

let kaithemapi = globalThis.kaithemapi
export { kaithemapi, APIWidget }