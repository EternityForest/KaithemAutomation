![Banderole Theme](screenshots/BanderoleTheme1.avif)

(Banderole Theme)


![Fugit Theme](screenshots/FugitTheme1.avif)

(Fugit theme)


![Visitors](https://api.visitorbadge.io/api/combined?path=https%3A%2F%2Fgithub.com%2FEternityForest%2FKaithemAutomation&countColor=%23263759&style=plastic)


Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It's more low level than your average HA system, but it allows you to control anything python can.

It runs on python3, but it is not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE. "Events" are sections of code that run when a trigger condition happens. Trigger conditions can be polled expressions, internal message bus
events, or time-based triggers using a custom semi-natural language parser.

![Editing an event](screenshots/edit-event.webp)


Almost the entire server state is maintained in RAM, and any changes you make to your code never touches the disk unless you explicitly save or configure auto-save.

![Lighting control](screenshots/lightboard.webp)
![Sound Mixer](screenshots/mixer.webp)


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




## Setup the easy way, even works headless!

Get a fresh RasPi OS image.  Use the raspi imager tool to set up the network stuff.

SSH in and run these commands.  They reconfigure a whole lot of stuff, including protecting the disk against excessive writes.

```
cd /opt
sudo git clone --depth 1 https://github.com/EternityForest/KaithemAutomation
cd KaithemAutomation
sudo bash kaithem-kioskify.sh
sudo reboot now
```

Now it will boot into a fullscreen kiosk browser pointed at Kaithem's home page.  Log in at
PIHOSTNAME.local:8002 using your RasPi username and Password, kaithem will run as your default user(uid1000).

If you want to change that default page, go to the Kaithem Settings and set the homepage to redirect to your URL of choice(Use PIHOSTNAME.local:8002 /index to get back to the real homepage)


### Instant digital signage

If you are trying to do digital signage, go to Settings > File Manager(Public webserver files) and upload a .mp4 file.
It will detect that the file is in the public folder and give you a digital signage link button.

Set your homepage to redirect to that link, you should be done!

#### Signage with audio

Audio is managed through the Kaithem mixer.  It should work out of the box if you're using the headphone jack.

Otherwise if using HDMI, or if you want to remotely adjust volume, go to the mixer and make sure that channel has the output you want selected, and that the input matches Chromium's name. You can also add effects like EQ from this page.  Don't forget to save the setup as the default!




## NixOS

This is a work in progress, but it does in fact run!!


## Manual Setup Stuff
See [This page](kaithem/src/docs/setup.md). Or, *to just try things out, git clone and run dev_run.py, then visit port 8001(for https) or port 8002(for not-https) on localhost. That's really all you need to do.*

Since there are initially no users, one is created using the name and password of the Linux user actually running the app.
This means you must run kaithem as a user that supports logins.

Note that to clone everything properly you must have git-lfs installed and set up, otherwise you won't get the tflite
data file needed for video recognition.

To set this up globally, do `sudo apt install git-lfs` then `git lfs install --skip-repo`. No I don't know why
Git doesn't have this in the core by default.

There are many optional dependancies in the .deb recommended section that enable extra features. All are available in the debian repos and do not need to be compiled, except for Cython, which is installed automatically by the postinstall script of the debian package, or can easily be manually installed with "sudo pip3 install Cython".

At the moment, Cython is only used to give audio mixer gstreamer threads realtime priority.

In particular, everything to do with sound is handled by dependancies, and python3-libnacl and python3-netifaces are recommended as several networking features require them.

Several other audio file players may still work, but the only one supported and suggested is mpv, on Debian provided by mpv and libmpv-dev.


## To install all required and optional dependencies 

```bash
sudo apt install scrot mpv libmpv-dev python3 cython3 build-essential python3-msgpack python3-future python3-serial  python3-tz  python3-dateutil  lm-sensors  python3-netifaces python3-jack-client  python3-gst-1.0  python3-libnacl  jack-tools  jackd2  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly  python3-psutil  fluidsynth libfluidsynth2  network-manager python3-paho-mqtt python3-dbus python3-lxml gstreamer1.0-pocketsphinx x42-plugins baresip autotalent libmpv-dev python3-dev  libbluetooth-dev libcap2-bin rtl-433  python3-toml  python3-rtmidi python3-pycryptodome  gstreamer1.0-opencv  gstreamer1.0-vaapi python3-pillow python3-scipy ffmpeg python3-skimage python3-setproctitle python3-tornado
```

You will also need Python's tflite_runtime for deep learning image recognition in the NVR.  
`python3 -m pip install tflite-runtime`  will do it on linux.

You don't need a model! A version of efficientdet-lite0 is included.  Accuracy should be better than the bare
model itself as we use heuristics to reduce false positives.

If you want to use ESPHome, you need to install `pip3 install aioesphomeapi`, as this has non-python dependencies we can't easily incluse, just like tflite-runtime.

Both are included by the kioskify script.


### Systemd service

Ajdust as needed  to point to your paths and users.  Or just use emberos.

Leave of the pw-jack in the front of ExecStart if you do not have PipeWire(If not on a Red Hat system or EmberOS, you likely don't yet as of now)

```ini
[Unit]
Description=KaithemAutomation python based automation server
After=basic.target time-sync.target sysinit.service zigbee2mqtt.service pipewire.service


[Service]
TimeoutStartSec=0
ExecStart=/usr/bin/bash -o pipefail -c /usr/bin/ember-launch-kaithem
Restart=on-failure
RestartSec=15
OOMScoreAdjust=-800
Nice=-15
#Make it try to act like a GUI program if it can because some modules might
#make use of that.  Note that this is a bad hack hardcoding the UID.
#Pipewire breaks without it though.
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
Environment="XDG_RUNTIME_DIR=/run/user/1000"
Environment="DISPLAY=:0"

#This may cause some issues but I think it's a better way to go purely because of
#The fact that we can use PipeWire instead of managing jack, without any conflicts.

#Also, node red runs as pi/user 1000, lets stay standard.
User=1000
#Bluetooth scannning and many other things will need this
#Setting the system time is used for integration with GPS stuff.
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_TIME CAP_SYS_NICE
SecureBits=keep-caps

LimitRTPRIO= 95
LimitNICE= -20
LimitMEMLOCK= infinity
Type=simple

[Install]
WantedBy=multi-user.target

```

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

### 0.68.48
- :coffin: Remove the Chandler tag permissions system, as it is too complex to properly assess the security model. It can now access any tag.
- :sparkles: JACK mixer has a noise gate now
- :sparkles: Link on settings page to take screenshot of server(Useful for checking on signage)
- :bug: Fix hang at shutdown
- :sparkles: New Banderole theme, probably the best example to learn theming
- :sparkles: Control RasPi and maybe others system power and activity LEDs via the tag points interface.
- :sparkles: auto_record datapoint on the NVRChannel for temporarily disabling recording
- :sparkles: Devices framework now has a WeatherClient, No API key needed thanks to wttr.in! :sunny: :cloud: :rainbow:
- :sparkles: Github based online assets library, seamlessly browse and download music and SFX right in Chandler
- :sparkles: Basic support for ESPHome devices(BinarySensor, Number, Sensor, TextSensor, Switch) including reconnect logic
- :bug: Fix zeroconf exceptions
- :sparkles: Chandler is no longer a module, it is now a built in, always-there tab.  Look forward to deeper integrations!
- :sparkles: Chandler audio cues play much faster than before
- :sparkles: Non-writable device data points can be "faked"
- :coffin: p class="help" deprecated, used details class="help"
- :sparkles: simple_light and simple_dark themes are official
  
### 0.68.47
- :bug: More robust responsive video
- :sparkles: Screen rotation setting in web UI
- :sparkles: Work on a proper theme chooser engine
- 
### 0.68.46
- :bug: Video signage auto restart fixes
- 
### 0.68.45
- :sparkles: Digital signage chrome error resillience
- :bug: New versions of NumPy needed a fix for the NVR labels file loading


### 0.68.44
- :bug: Faster and more reliable jackmixer startup
- :sparkles: Improve kioskify

### 0.68.43
- :bug: Remove notification for tripped->normal transition
- :sparkles: Show tripped alerts on main page
- :sparkles: Thread start/stop logging now shows thread ID
- :sparkles: Chandler cue media speed, windup, and winddown, to simulate the record player spinup/down or "evil dying robot" effect.
- :bug: Fix temperature alerts chattering on and off if near threshold
- :coffin: Remove code view for Chandler fixture types
- :sparkles: Can now import OP-Z fixture definitions from a file in Chandler(you can select which ones out of the file to import)
-  :coffin: BREAKING: You now run kaithem in the CLI by running dev_run.py.
-  :coffin: BREAKING: You must update Chandler to the new version in included the library, the old one will not work.
-  :coffin: EspruinoHub removed
-  :coffin: Icons other than icofont are gone
-  :sparkles: Should work on Python3.11
-  :sparkles: Can now configure / to redirect to some other page.  Use /index directly to get to the real home.
-  :bug: Fix editing file resources regression
-  :sparkles: /user_static/FN will now serve vardir/static/FN
-  :sparkles: Kaithem-kioskify script configures the whole OS as an embedded controller/signage device from a fresh Pi image



License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
