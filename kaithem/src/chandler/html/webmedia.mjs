const atypes = ['.ogg', '.oga', '.aac', '.m4a', '.mp3', '.opus']
const itypes = ['.png', '.jpg', '.bmp', '.tiff', '.webp', '.gif', '.avif']

let telemetryStatus = "LOADED"
let link = null

function setLink(l) {
    link = l
}

let telemetryName = localStorage.getItem('friendly_slideshow_device_name') || ''
function sendTelemetry() {
    if (!link) {
        return;
    }
    link.send(['telemetry', {
        'status': telemetryStatus,
        'name': telemetryName
    }])
}

function setTelemetryStatus(s) {
    telemetryStatus = s
    sendTelemetry()
}

function setTelemetryName(s) {
    telemetryName = s
    sendTelemetry()
}

setInterval(
    function () {
        sendTelemetry()
    }, 60000
)



class makePlayer {
    constructor(c, group) {
        this.group = group
        this.presets = {}
        this.isSound = function (fn) {
            for (var i of atypes) {
                if (fn.indexOf(i) > -1) {
                    return true;
                }
            }

            return false;
        };

        this.isStillImage = function (fn) {
            for (var i of itypes) {
                if (fn.indexOf(i) > -1) {
                    return true;
                }
            }

            return false;
        };


        this.getButterchurn = function () {

            if (this.butterchurn == undefined) {
                this.butterchurn_canvas = document.createElement('canvas')
                this.butterchurn_canvas.height = window.innerHeight
                this.butterchurn_canvas.width = window.innerWidth
                this.butterchurncontext = new AudioContext();


                var presets = {};
                if (window.butterchurnPresets) {
                    Object.assign(presets, butterchurnPresets.getPresets());
                }
                if (window.butterchurnPresetsExtra) {
                    Object.assign(presets, butterchurnPresetsExtra.getPresets());
                }

                if (window.butterchurnPresetsExtra2) {
                    Object.assign(presets, butterchurnPresetsExtra2.getPresets());
                }

                if (presets) {
                    this.presets = _(presets).toPairs().sortBy(([k, v]) => k.toLowerCase()).fromPairs().value();
                }
                else {
                    this.presets = {}
                }

                this.presetKeys = _.keys(this.presets);
                this.butterchurn_options = []


                var visualizer = butterchurn.default.createVisualizer(this.butterchurncontext, this.butterchurn_canvas, {
                    width: window.innerWidth,
                    height: window.innerHeight,
                    pixelRatio: window.devicePixelRatio || 1,
                    textureRatio: 1,
                });

                function nextPreset(blendTime = 5.7) {
                    var numPresets = player2.presetKeys.length;
                    if (numPresets) {
                        if (player2.butterchurn_options.length) {
                            var presetIndex = Math.floor(Math.random() * player2.butterchurn_options.length);
                            visualizer.loadPreset(player2.presets[player2.butterchurn_options[presetIndex]], blendTime);
                        }
                        else {
                            var presetIndex = Math.floor(Math.random() * player2.presetKeys.length);
                            visualizer.loadPreset(player2.presets[player2.presetKeys[presetIndex]], blendTime);
                        }

                    }
                }


                nextPreset(0);
                var cycleInterval = setInterval(() => nextPreset(2.7), 12000);
                this.butterchurn = visualizer;
            }
            return this.butterchurn;
        }

        this.isButterchurn = function (fn) {
            //Mor of a guess than anything exact
            if (fn.startsWith('milkdrop:')) {
                return true;
            }
            return false;
        };

        this.isHTML = function (fn) {
            //Mor of a guess than anything exact
            if (fn.endsWith('.html')) {
                return true;
            }

            if (fn.endsWith('.com')) {
                return true;
            }

            if (fn.endsWith('.net')) {
                return true;
            }


            if (fn.endsWith('.org')) {
                return true;
            }


            //If the part after the last dot, or the whole thing if no dots, is longer than 4,
            //it's not an extension
            if (fn.split(".").slice(-1)[0].length > 4) {
                return true;
            }

            return false;

        };


        this.cstyle = {
            top: '0px',
            right: '0px',
            width: '100%',
            height: '100%',
            position: 'absolute',
            overflow: 'hidden',
            margin: '0px',
            padding: '0px',
            'border-width': '0px',
            background: 'none',
            'mix-blend-mode': 'lighten'

        }

        this.vstyle = {
            top: '0px',
            right: '0px',
            height: "100%",
            width: '100%',
            margin: '0px',
            padding: '0px',
            position: 'absolute',
            "max-height": '100%',
            "max-width": '100%',
            "object-fit": 'contain',
        };

        this.setStyles = function (element, styles) {
            for (var s in styles) {
                element.style[s] = styles[s];
            }
        };


        this.currentLayer = document.createElement('div');
        this.setStyles(this.currentLayer, this.cstyle);

        this.altLayer = document.createElement('div');
        this.setStyles(this.altLayer, this.cstyle);


        c.appendChild(this.currentLayer);
        c.appendChild(this.altLayer);
        var parent = this;


        this.currentMedia = 0;
        this.altMedia = 0;
        this.fadeTask = 0;
        this.fadeStart = 0;
        this.fadeLength = 0;
        this.targetVolume = 0.1;


        this.task = function () {

            if (parent.fadeLength == -1) {
                return;
            }
            if (parent.fadeLength == 0) {
                if (parent.currentMedia) {
                    parent.currentMedia.volume = parent.targetVolume;
                    if (parent.currentMedia.paused) {

                        // If not completed
                        if (parent.currentMedia.position < parent.currentMedia.duration - 0.5) {
                            parent.playLater(parent.currentMedia)
                        }
                    }
                }


                parent.currentLayer.style.opacity = '100%'

                if (parent.altMedia) {
                    parent.altMedia.volume = 0;
                    if (parent.altMedia.paused) {
                        if (parent.altMedia.position < parent.altMedia.duration - 0.5) {
                            parent.playLater(parent.altMedia)
                        }
                    }
                }

                parent.altLayer.style.opacity = '0%'

                return;
            }

            var position = Math.max(Math.min((Date.now() - parent.fadeStart) / parent.fadeLength, 1), 0);

            if (position == 1) {
                parent.fadeLength = 0;
            }


            parent.currentLayer.style.opacity = (position * 100) + '%';
            parent.altLayer.style.opacity = ((1 - position) * 100) + '%';

            if (parent.currentMedia) {
                parent.currentMedia.volume = position * parent.targetVolume;
            }

            if (parent.altMedia) {
                parent.altMedia.volume = (1 - position) * parent.targetVolume;
            }

        };

        setInterval(this.task, 1000 / 24);

        this.lastMedia = '';
        this.alertTimeout = function (mymsg, mymsecs) {
            var myelement = document.createElement("div");
            myelement.setAttribute("style", "background-color: grey;color:black; width: 450px;height: 200px;position: absolute;top:0;bottom:0;left:0;right:0;margin:auto;border: 4px solid black;font-family:arial;font-size:25px;font-weight:bold;display: flex; align-items: center; justify-content: center; text-align: center;");
            myelement.innerHTML = mymsg;
            setTimeout(function () {
                myelement.parentNode.removeChild(myelement);
            }, mymsecs);
            document.body.appendChild(myelement);
        }

        this.pli = false;

        this.playLater = function (el) {
            if (this.pli) {
                return;
            }
            if (!this.error_send_timeout) {
                this.error_send_timeout = setTimeout(function () {
                    telemetryStatus = "PLAY FAILED"
                    sendTelemetry()
                }, 20000)
            }

            this.deffered_play = el
            this.pli = setInterval(async () => {
                if (this.deffered_play) {
                    var p = this.deffered_play

                    try {
                        await p.play()
                        if (this.error_send_timeout) {
                            clearTimeout(this.error_send_timeout)
                        }
                        telemetryStatus = 'OK'
                        sendTelemetry()

                        var st = this.intended_start_pos - ((link.now() / 1000) - this.intended_start_ts)
                        st = Math.max(st, 0)
                        p.currentTime = st;

                        if (this.butterchurn) {
                            var n = this.butterchurncontext.createMediaElementSource(this.deffered_play)
                            this.connectNewButterchurnSource(n)
                        }
                        this.deffered_play = false
                        clearInterval(this.pli)
                        this.pli = false
                    }
                    catch {
                        this.alertTimeout("Must click page to play, unless you enable autoplay in browser settings.", 1000)
                    }


                }
            }, 1000)
        }
        this.connectNewButterchurnSource = function (sourceNode) {
            //sourceNode.disconnect()

            if (this.butterchurn == undefined) {
                return;
            }
            if (this.delayedAudible) {
                this.delayedAudible.disconnect();
            }

            this.delayedAudible = this.butterchurncontext.createDelay();


            this.delayedAudible.delayTime.value = 0.26;

            sourceNode.connect(this.delayedAudible)
            this.delayedAudible.connect(this.butterchurncontext.destination);

            this.butterchurn.connectAudio(this.delayedAudible);

            this.butterchurncontext.resume()
        }


        this.playMedia = async function (t, f, st, sessionTag) {

            var ts = link.now() / 1000

            if (t.children.length > 0) {
                t.removeChild(t.children[0]);
            }

            if (!f) {
                return;
            }

            if (this.isButterchurn(f)) {
                var s = document.createElement('audio');
                var s2 = this.getButterchurn()
                t.appendChild(s);
                t.appendChild(this.butterchurn_canvas);
            }


            if (this.isSound(f)) {
                var s = document.createElement('audio');
                s.addEventListener("ended", (event) => {
                    link.send(['mediaEnded', sessionTag])
                });

                t.appendChild(s);

            }

            else if (this.isStillImage(f)) {
                t.appendChild(document.createElement('img'));
            }

            else if (this.isHTML(f)) {
                t.appendChild(document.createElement('iframe'));
            }

            else {
                var x = document.createElement('video')
                x.addEventListener("ended", (event) => {
                    link.send(['mediaEnded', sessionTag])
                });
                t.appendChild(x);
            }

            if (this.isButterchurn(f)) {
                f = f.split("milkdrop:")[1]
            }

            var x = "WebMediaServer?group=" + this.group + "&file=" + encodeURIComponent(f);


            if (this.isHTML(f)) {
                t.children[0].src = f
                this.setStyles(t.children[0], {
                    height: '100%', width: '100%', 'border-width': '0px', margin: '0px', padding: '0px'
                })

            }
            else {
                t.children[0].src = x;
                this.setStyles(t.children[0], this.vstyle)
            }


            if (!(this.isStillImage(f) || this.isHTML(f))) {
                t.children[0].volume = 0;


                this.intended_start_pos = st
                this.intended_start_ts = ts

                let st = st - ((link.now() / 1000) - ts)
                st = Math.max(st, 0)
                t.children[0].currentTime = st;
                t.children[0].controls = true;

                try {
                    await t.children[0].play();
                    if (this.error_send_timeout) {
                        clearTimeout(this.error_send_timeout)
                    }
                    telemetryStatus = 'OK'

                    if (this.butterchurn) {
                        var n = this.butterchurncontext.createMediaElementSource(t.children[0])
                        this.connectNewButterchurnSource(n)
                    }
                }
                catch (e) {
                    this.playLater(t.children[0]);

                }
                return t.children[0];
            }
            return null;
        };


        //The session tag lets you switch to something that is the same file, restarting
        this.switchMedia = async function (v, t, startAt, sessionTag) {

            if (this.lastMedia == v + sessionTag) {
                return null;
            }
            this.lastMedia = v + sessionTag;

            this.fadeStart = link.now();

            // ye switcharoo
            var x = this.currentLayer;
            this.currentLayer = this.altLayer;
            this.altLayer = x;

            this.currentLayer.style.opacity = '0%';

            this.fadeLength = -1;
            this.altMedia = this.currentMedia;
            this.currentMedia = await this.playMedia(this.currentLayer, v, startAt, sessionTag);

            this.fadeLength = Math.max(0, (t - startAt) * 1000)

            if (v && v.length == 0) {
                document.getElementsByTagName('media-player')[0].class = 'player-idle'
            }
            else {
                document.getElementsByTagName('media-player')[0].class = ''
            }
        };

        setInterval(() => {
            if (this.butterchurn) {
                this.butterchurn.render();
            }
        }, 24)

    }
}

export { makePlayer, setLink, setTelemetryName, setTelemetryStatus, sendTelemetry }