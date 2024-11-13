import { encode, decode } from './thirdparty/msgpackr.esm.js';
import picodash from './thirdparty/picodash/picodash-base.esm.js'

try { globalThis.kaithemapi } catch { globalThis.kaithemapi = undefined }

if (globalThis.kaithemapi == undefined) {

	var KaithemWidgetApiSnackbar = function (m, d) {
		picodash.snackbar.createSnackbar(m, (d||10)*1000);
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
						if (lastDidSnackbarError < Date.now() + 60000) {
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
						self.uuidToWidgetId[m[0]] = m[1];
						self.widgetIDtoUUID[m[1]] = m[0];
					}
				],

				"__FORCEREFRESH__": [
					function (m) {
						window.location.reload();
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
			poll_ratelimited: function () { },

			subscribe: function (key, callback) {


				if (key in this.serverMsgCallbacks) {
					this.serverMsgCallbacks[key].push(callback);
				}

				else {
					this.serverMsgCallbacks[key] = [callback];
				}

				//If the ws is open, send the subs list, else wait for the connection handler to do it when we first reconnect.
				if (this.connection) {
					if (this.connection.readyState == 1) {
						var j = { "subsc": Object.keys(this.serverMsgCallbacks), "upd": [] }
						this.connection.send(JSON.stringify(j))
					}
				}
			},

			unsubscribe: function (key, callback) {
				var arr = this.serverMsgCallbacks[key];


				if (key in arr) {

					for (var i = 0; i < arr.length; i++) { if (arr[i] === callback) { arr.splice(i, 1); } }
				}

				if (arr.length == 0) {

					//Delete the now unused mapping
					if (key in this.uuidToWidgetId) {
						delete this.widgetIDtoUUID[this.uuidToWidgetId[key]];
						delete this.uuidToWidgetId[key];
					}



					delete this.serverMsgCallbacks[key]


					//If the ws is open, send the subs list. If not, we by definition aren't subscribed, and we already removed it from the local list.
					if (this.connection) {
						if (this.connection.readyState == 1) {
							var j = { "unsub": [key], "upd": [] }
							this.connection.send(JSON.stringify(j))
						}
					}
				}
			},

			sendErrorMessage: function (error) {
				if (this.lastErrMsg) {
					if (this.lastErrMsg > (Date.now() - 10000)) {
						return
					}
				}
				this.lastErrMsg = Date.now();

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
				return window.location.protocol.replace("http", "ws") + "//" + window.location.host
			},

			can_show_error: 1,
			usual_delay: 0,
			reconnect_timeout: 1500,

			reconnector: null,
			// Very first time, give it some extra before clearing old msgs
			lastDisconnect: Date.now() + 15000,

			connect: function () {
				var apiobj = this

				this.connection = new WebSocket(window.location.protocol.replace("http", "ws") + "//" + window.location.host + '/widgets/ws');

				this.connection.onclose = function (e) {
					apiobj.lastDisconnect = Date.now();
					console.log(e);
					if (apiobj.reconnector) {
						clearTimeout(apiobj.reconnector)
						apiobj.reconnector = null;
					}
					apiobj.reconnector = setTimeout(function () { apiobj.connect() }, apiobj.reconnect_timeout);
				};

				this.connection.onerror = function (e) {
					apiobj.lastDisconnect = Date.now();
					console.log(e);
					if (apiobj.reconnector) {
						clearTimeout(apiobj.reconnector)
						apiobj.reconnector = null;
					}
					if (apiobj.connection.readyState != 1) {
						apiobj.reconnect_timeout = Math.min(apiobj.reconnect_timeout * 2, 20000);
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
								catch (err) {
									apiobj.sendErrorMessage(window.location.href + "\n" + err.stack)
									console.error(err.stack)
								}
							})

						}
						else {
							var resp = JSON.parse(e.data);
							apiobj.connection.handleIncoming(resp)
						}
					}
					catch (err) {
						apiobj.sendErrorMessage(window.location.href + "\n" + err.stack)
						console.error(err.stack)
					}


				}

				this.connection.handleIncoming = function (resp) {
					//Iterate messages
					for (var n = 0; n < resp.length; n++) {
						let i = resp[n]
						for (var j in apiobj.serverMsgCallbacks[i[0]]) {
							if (resp[n].length > 1) {
								apiobj.serverMsgCallbacks[i[0]][j](resp[n][1]);
							}
							else {
								if (this.alreadyPostedAlertOnce) { }
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
				this.connection.onopen = function (e) {
					// Do not send very old messages on reconnect
					if (apiobj.lastDisconnect < (Date.now() - 5000)) {
						apiobj.toSend = [];
					}

					var j = JSON.stringify({ "subsc": Object.keys(apiobj.serverMsgCallbacks), "req": [], "upd": [["__url__", window.location.href]] })
					apiobj.connection.send(j)
					console.log("WS Connection Initialized");
					apiobj.reconnect_timeout = 1500;
					window.setTimeout(function () { apiobj.wpoll() }, 250);
				}

				this.wpoll = function () {
					//Don't bother sending if we aren'y connected
					if (this.connection.readyState == 1) {
						if (this.toSend.length > 0) {
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

					}

					if (this.toSend && (this.toSend.length > 0)) {
						window.setTimeout(this.poll_ratelimited.bind(this), 120);
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

	if (!window.onerror) {
		var globalPageErrorHandler = function (msg, url, line) {
			globalThis.kaithemapi.sendErrorMessage(url + '\n' + line + "\n\n" + msg)
		}
		window.addEventListener("unhandledrejection", event => {
			globalThis.kaithemapi.sendErrorMessage(`UNHANDLED PROMISE REJECTION: ${event.reason}`);
		});

		window.onerror = globalPageErrorHandler
	}
	//Backwards compatibility hack
	//Todo deprecate someday? or not.
	let __kwidget_doBattery = function () {
		if (navigator.userAgent.indexOf("Firefox") == -1) {

			try {
				navigator.getBattery().then(function (battery) {
					globalThis.kaithemapi.sendValue("__BATTERY__", { 'level': battery.level, 'charging': battery.charging })
				});
			}
			catch (e) {
				console.log(e)
			}

			try {
				if ('AmbientLightSensor' in window) {
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

	if (navigator.userAgent.indexOf("Firefox") == -1) {
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
							threshold: 240000,
							signal,
						});
					} catch (err) {
						// Deal with initialization errors like permission denied,
						// running outside of top-level frame, etc.
						console.error(err.name, err.message);
					}
				}
			});
		}
		catch (e) {
			//No logging, FF would spam a bunch of logs
			//console.log(e)
		}
	}

	setTimeout(__kwidget_doBattery, 60)
	setInterval(__kwidget_doBattery, 1800000)

	window.addEventListener('load', function () {
		setTimeout(function () { globalThis.kaithemapi.connect() }, 10)
	})
}

class APIWidget {
    constructor(uuid) {
        this.uuid = uuid
        this.value = "Waiting..."
        this.clean = 0;
        this._maxsyncdelay = 250
        this.timeSyncInterval = 120 * 1000;

		this._timeref = null;

        kaithemapi.subscribe("_ws_timesync_channel", this.onTimeResponse)
        kaithemapi.subscribe(this.uuid, this._upd.bind(this));
        setTimeout(this.getTime.bind(this), 500)
    }

    onTimeResponse(val) {
        {
            if (Math.abs(val[0] - this._txtime) < 0.1) {
                {
                    var t = performance.now();
                    if (t - this._txtime < this._maxsyncdelay) {
                        {
                            this._timeref = [(t + this._txtime) / 2, val[1]]

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

    _upd(val) {
        {
            if (this.clean == 0) {
                {
                    this.value = val;
                }
            }
            else {
                {
                    this.clean -= 1;
                }
            }
            this.upd(val)
        }
    }

    upd(val) {
        {
        }
    }
    getTime() {
        {
            var x = performance.now()
            this._txtime = x;
            kaithemapi.sendValue("_ws_timesync_channel", x)
        }
    }


    now(val) {
        {
            var t = performance.now()
            if (t - this._txtime > this.timeSyncInterval) {
                {
                    this.getTime();
                }
			}
			if(this._timeref == null){
				return Date.now();
			}
            return ((t - this._timeref[0]) + this._timeref[1])
        }
    }

    set(val) {
        {
            kaithemapi.setValue(this.uuid, val);
            this.clean = 2;
        }
    }

    send(val) {
        {
            kaithemapi.sendValue(this.uuid, val);
            this.clean = 2;
        }
    }
}

let kaithemapi = globalThis.kaithemapi
export { kaithemapi, APIWidget }