![Logo](kaithem/data/static/img/klogoapr22.jpg)

Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It's more low level than your average HA system, but it allows you to control anything python can.

It runs on python3, but it is not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE. "Events" are sections of code that run when a trigger condition happens. Trigger conditions can be polled expressions, internal message bus
events, or time-based triggers using a custom semi-natural language parser.

![Editing an event](screenshots/edit-event.jpg)


Almost the entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure auto-save.

![Lighting control](screenshots/basictheme_lightboard.png)

Kaithem also includes a module called Chandler, which is a full web-based lighting control board with a visual
programming language for advanced interactive control.

Kaithem is still beta, but I've used it in production applications running for months at a time. 

It wasn't designed for any kind of safety-critical application, but it is meant to be reliable enough for most home and commercial applications.

Installation
============

## Documentation
Kaithem's help files are being migrated to markdown. You can browse right on github,
or access the full help via the web interface!
*  [help](kaithem/src/docs/help.md)
*  [FAQ(old)](kaithem/src/docs/faq.md)


## Setup
See [This page](kaithem/src/docs/setup.md). Or, *to just try things out, git clone and run kaithem/kaithem.py, then visit port 8001(for https) or port 8002(for not-https) on localhost. That's really all you need to do.*

There are many optional dependancies in the .deb recommended section that enable extra features. All are available in the debian repos and do not need to be compiled, except for Cython, which is installed automatically by the postinstall script of the debian package, or can easily be manually installed with "sudo pip3 install Cython".

At the moment, Cython is only used to give audio mixer gstreamer threads realtime priority.

In particular, everything to do with sound is handled by dependancies, and python3-libnacl and python3-netifaces are recommended as several networking features require them.

Several other audio file players may still work, but the only one supported and suggested is libmpv, on Debian provided by libmpv-dev.


### Systemd service

Ajdust as needed  to point to your paths and users.  Or just use emberos.
```ini
[Unit]
Description=KaithemAutomation python based automation server
After=basic.target time-sync.target sysinit.service zigbee2mqtt.service
Type=simple


[Service]
TimeoutStartSec=0
ExecStart=/opt/kaithem/kaithem/kaithem.py -c /sketch/kaithem/config.yaml
Restart=on-failure
RestartSec=15
OOMScoreAdjust=-800
Nice=-15
#Make it try to act like a GUI program if it can because some user-added python modules might
#make use of that.
Environment="DISPLAY=:0"

#This may cause some issues but I think it's a better way to go purely because of
#The fact that we can use PipeWire instead of managing jack, without any conflicts.

#Also, node red runs as pi, lets stay standard.
User=pi
#Bluetooth scannning and many other things will need this
#Setting the system time is used for integration with GPS stuff.
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_TIME



[Install]
WantedBy=multi-user.target

```

# To download all optional dependancies
```
sudo apt install pulseaudio python3-pyserial python3-pytz python3-dateutil lm-sensors python3-netifaces python3-jack-client python3-gst-1.0 python3-libnacl jack-tools jackd2 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad swh-plugins sudo apt install tap-plugins caps  gstreamer1.0-plugins-ugly python3-psutil fluidsynth libfluidsynth2 network-manager python3-paho-mqtt python3-dbus python3-lxml gstreamer1.0-pocketsphinx x42-plugins baresip autotalent libmpv-dev python3-dev libbluetooth-dev libcap2-bin

sudo pip3 install beacontools[scan]
```

### Security
At some point, you should probably set up a proper SSL certificate in kaithem/var/ssl. The debian installer will generate one at
/var/lib/kaithem/ssl/certificate.key that you can replace with a real one if you don't want to go self-signed.


### Debugging

It shouldn't happen, but if things get real messed up, use SIGUSR1 to dump hte state of all threads to /dev/shm/
"killall -s USR1 kaithem" works if you have setproctitle.

#### with GDB
If using GDB python, you may need to use "handle SIG32 nostop" to suppress abboying notifications:

gdb python3
$handle SIG32 nostop
$run YOUR_KAITHEM_PY_FILE





Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
=============
### 0.67.1
- Fix very long sound loop counts
- Fix RTMidi compatibility with new py libs
- Faster boot time with some devices
- SoundFuse algorithm more aggressive

### 0.66.0

- JackMIDIListener has been removed.  Instead, all connected ALSA midi devices automatically generate tag points for last pressed note and all CC values.
- All connected midi devices now also report to the message bus
- JackFluidSynth plugin now only accepts MIDI on the internal message bus.  
- python-rtmidi is required to use these features.  This is all on account of some unreliable performance and excess complexity with jack midi.
- Chandler can now respond directly to MIDI, no code needed
- Chandler bugfix with smart bulb hue and saturation channels not blending the way you might expect.
- Using a caching strategy we avoid calling ALSA sound card listing functions when not needed to stop occasional bad noises(Much lower JACK latency is possible)
- Chandler Pavillion encrypted protocol sync removed(MQTT alternative coming soon)
- Chandler scene notes now just uses a plain HTTP textarea

- *Major breaking changes*

- The ALSA sound card aliases system has been removed. We no longer support multiple devices except with JACK
- *Audio file playback is now done with libmpv.  All other backends are deprecated.   You should have python-mpv on your system!*
- This greatly increases audio performance and stability.
- We no longer support a2jmidid or aliases for MIDIs.  Use ALSA midi directly, almost no use cases will need advanced routing.


### 0.65.64
- Now we support those cheap SainSmart relay boards with a tagpoint based interface.  Use the Relayft245r device type.
- Freeboard default values don't clobber existing stuff if it is there, for the slider and switch widgets.
- Broadcast Center sends snackbar text alerts to most/all devices accessing the server
- kaithemobj.widgets.sendGlobalAlert(message, duration) to programmatically send HTML in a snackbar to all devices.
- New tag.control: expose API gives write only control, for when you want to both claim the tag and separately see it's current real value
- New /pages/chandler/sendevent?event=NAME&value=VALUE API
- User pages now show telemetry on what WS connections are open from what IP addresses on what pages. Use
- BREAKING CHANGE: the default topics used by the MQTT Tag sync no longer use a slash.
- Correctly handle MQTT passsive connections that are created after the real connection



License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
