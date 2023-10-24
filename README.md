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



### Connecting Multiple Servers

Most Kaithem features that can do this, rely on MQTT, as per the "No reinvented wheels" philosophy.  To set up an MQTT server,
do this as root.  Using encryption with MQTT is harder, but many tutorials exist.  MQTT in Kaithem is powered by Paho-MQTT.

```
apt-get -y install mosquitto

cat << "EOF" >> /etc/mosquitto/conf.d/kaithem.conf
persistance false
allow_anonymous true
EOF

systemctl restart mosquitto.service
```


### Instant digital signage

If you are trying to do digital signage, go to Settings > File Manager(Public webserver files) and upload a .mp4 file.
It will detect that the file is in the public folder and give you a digital signage link button.

Set your homepage to redirect to that link, you should be done!

#### Signage with audio

Audio is managed through the Kaithem mixer.  It should work out of the box if you're using the headphone jack.

Otherwise if using HDMI, or if you want to remotely adjust volume, go to the mixer and make sure that channel has the output you want selected, and that the input matches Chromium's name. You can also add effects like EQ from this page.  Don't forget to save the setup as the default!


## Manual Install in a virtualenv

Install git-lfs if you don't have it, to clone the repo
```bash
sudo apt install git-lfs
git lfs install --skip-repo
```


### Install system packages

Most of these have to do with audio features, not all are needed.

```bash
sudo apt install scrot mpv lm-sensors  python3-netifaces python3-gst-1.0  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly fluidsynth libfluidsynth3 gstreamer1.0-pocketsphinx x42-plugins baresip gstreamer1.0-opencv  gstreamer1.0-vaapi python3-opencv
```


### Actually install Kaithem
```bash
sudo apt install python3-virtualenv
git clone --depth 1 https://github.com/EternityForest/KaithemAutomation
cd KaithemAutomation
virtualenv --system-site-packages ../kaithem_venv
source ../kaithem_venv/bin/activate
pip install -r requirements_frozen.txt
```

If you are more adventurous, instead you can install direct_dependencies.py and get the unfrozen versions of everything.


### Running Kaithem quickly

From inside your Kaithem folder:

```bash
source ../kaithem_venv/bin/activate
python3 dev_run.py
```

Then visit http://localhost:8002 and log in with your normal Linux username and password.



### Sound on Ubuntu

Kaithem does not support advanced audio features on anything other than pipewire via the JACK protocol.

Out of the box, JACK apps don't work on Ubuntu. Try:
```bash
sudo apt install pipewire-audio-client-libraries
systemctl --user restart pipewire-media-session pipewire pipewire-pulse
sudo cp /usr/share/doc/pipewire/examples/ld.so.conf.d/pipewire-jack-*.conf /etc/ld.so.conf.d/
sudo ldconfig
```
ewire-audio-client-libraries
This will make ALL jack apps go through pipewire, you won't ever need to launch jackd.
I'm not sure why you would ever want to use the original JACK server, so this shouldn't cause any issues.


### VSCode Dev
In the VS code terminal in the root of the project

```bash
virtualenv --system-site-packages .venv
source .venv/bin/activate
pip install --ignore-installed -r requirements_frozen.txt 
```

Ctrl-shift-p, select the interpreter in the venv.

dev_run.py can be your entry point for debug. If you get weird errors, check your debug launch config and
make sure it's not overriding the interpreter, because then you would be running outside the virtualenv.

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

### 0.70.0

- :bug: Fix bogus "sound did not report as playing" message
- :sparkles: "Make file publically acessible" option in the upload for file resources.
- :bug: Fix disabling resource serving
- :sparkles: Dmesg viewer
- :sparkles: Simple_light is now the default theme, as Chrome can on some devices be unhappy with complex themes
- :bug: Improve slow/hanging shutdown
- :bug: Fix Mixer processes hanging around when they should not be

### 0.69.20

- :sparkles: Py3.11 Sipport
- :sparkles: Map tile server now integrated, works out of the box, and autofetches missing tiles if you have the settings permission.
- :bug: Fix multilevel nested folders regression
- :sparkles: -1 in cue sound fade in disables crossfading.
- :bug: Fix sound fading out
- :bug: Fix sound speed not getting correctly set in some cases
- :sparkles: Chandler uses sine-in-out easing for lighting fades
- :sparkles: BETA if you have the settings permission, now you can browse edit SQLite databases(Powered by a customized sqlite-web)
- :sparkles: We now monitor dmesg hourly to detect IO Errors
- :coffin: HBMQTT removed, along with it the embedded MQTT broker
- :coffin: Kaithem.mqtt deprecated
- :bug: Fix module.timefunc issues in chandler.
- :bug: Fix deleting device that has subdevice
- :bug: Fix zombie devices messing up page width
- :sparkles: Chandler console icons now show which cues have any lighting commands
- :bug: Fix Chandler backtracking not happening if the cue you are going to is specified as the "next" cue for the current one
- :bug: Fix typo that caused exported Chandler setup files to not load teh fixture assignments.  Old files will still work on the new version.
- :coffin: Simplify locking in Chandler to only use one lock.


### 0.69.1
Moving to Tornado was a rather large change, this release is mostly cleanup.

- :sparkles: Alt top banner HTML option in user pages
- :bug: Can specify per-page theme name instead of full CSS url
- :bug: Fix raw websockets used in NVR streaming
- :bug: Fix tagpoint page fake buttons


### 0.69.0

- :sparkles: Use the Tornado server
- :sparkles: Per-connection Websocket handler threads eliminate global bogdown on blocking socket actions
- :coffin: enable-js, enable-websockets, drayer-port, and other useless config options removed.
- :coffin: config validation no longer rejects additional properties.
- :coffin: We no longer support starting as root and dropping permissions. Use systemd features for port 80.




License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
