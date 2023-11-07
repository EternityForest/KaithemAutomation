![AI generated picture of a tavern](kaithem/data/static/img/nov23-ai-watercolor-tavern.webp)

Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It runs on python3, but it is not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE, or by using the built-in Chandler module, which is a full web-based lighting aud audio control board with a visual programming language adding interactivity.

Installation
============

## How to run it!

Install git-lfs if you don't have it, to clone the repo
```bash
sudo apt install git-lfs
git lfs install --skip-repo

git clone --depth 1 https://github.com/EternityForest/KaithemAutomation
cd KaithemAutomation
git lfs pull
```

Now you have the repo cloned, all the relevant commands are in the Makefile.
This is an interpreted package, but we use Make anyway to keep commands in one handy place.


### Install system packages

Many of these have to do with audio features, not all are needed. See Makefile for what is actually
installed. This also installs virtualenv support.

```bash
make root-install-system-dependencies
```


### Install kaithem in the project folder virtualenv
```bash
# Show the menu of Kaithem commands
make help

# Grab Pip dependencies and install into this cloned project folder
make dev-install

# Run the file(Launches dev_run in a virtualenv)
make dev-run
```

Then visit http://localhost:8002 and log in with your normal Linux username and password.


### Sound Mixing Broken?

Kaithem does not support advanced audio features on anything other than pipewire via the JACK protocol.

Out of the box, JACK apps might not work on Ubuntu. Try:
```bash
sudo make root-use-pipewire-jack
```

And then rebooting. In theory you can just restart the services, but it seems to need a reboot to take effect.

This will make ALL jack apps go through pipewire, you won't ever need to launch jackd.
I'm not sure why you would ever want to use the original JACK server, so this shouldn't cause any issues.

Unfortunately, it doesn't work on pi, you'll need to prefix stuff that should use jack with pw-jack.
Kaithem's installer does this automatically.

### Sound Too Quiet?

Pipewire likes to set volume to 40% at boot, at the ALSA level. Try:

```bash
make user-max-volume-at-boot
```
as whatever user you plan to run kaithem under.


### Install globally and run at boot

To run as a systemd user service(Runs as soon as you log in, use autologin or lingering to run at boot)

```bash
make user-install-kaithem
```



## Setup a kiosk the easy way on a headless Pi!

Get a fresh RasPi OS image.  Use the raspi imager tool to set up the network stuff.

SSH in and run these commands.  They reconfigure a whole lot of stuff, including protecting the disk against excessive writes, so only run this on a fresh image dedicated to the cause.


As the default user, run:

```bash
sudo make root-install-system-dependencies
sudo make root-use-pipewire-jack

# Note: These root functions assume that everything will run under the
# default user. If installing as a different user, pass KAITHEM_USER to make. 
sudo make root-install-sd-protection
sudo make root-install-linux-tweaks
sudo make root-install-kiosk

make user-max-volume-at-boot
make user-install-kaithem
sudo reboot now
```

Now it will boot into a fullscreen kiosk browser pointed at Kaithem's home page.  Log in at
PIHOSTNAME.local:8002 using your RasPi username and Password, kaithem will run as your default user(uid1000).

To change the page, you can pass KIOSK_HOME=url to make.

If you want to change that default page, go to the Kaithem Settings and set the homepage to redirect to your URL of choice(Use PIHOSTNAME.local:8002 /index to get back to the real homepage).

To update, do a `make update` in /opt/KaithemAutomation,  then rerun `make user-install-kaithem`.


### No sound from the browser?

Go to the kaithem GUI and select your output for the kiosk mixer channel.

If there is no mixer channel, make one and set the input to Chromium.  Or wait a minute, mixer channels somethines don't load immediately at boot. Then save it as the default.


### Instant digital signage

If you are trying to do digital signage, go to Settings > File Manager(Public webserver files) and upload a .mp4 file.
It will detect that the file is in the public folder and give you a digital signage link button.

Set your homepage to redirect to that link, you should be done!

#### Signage with audio

Audio is managed through the Kaithem mixer.  It should work out of the box if you're using the headphone jack.

Otherwise if using HDMI, or if you want to remotely adjust volume, go to the mixer and make sure that channel has the output you want selected, and that the input matches Chromium's name. You can also add effects like EQ from this page.  Don't forget to save the setup as the default!



### VSCode Dev
dev_run.py can be your entry point for debug. If you get weird errors, check your debug launch config and
make sure it's not overriding the interpreter, because then you would be running outside the virtualenv.


### Dependencies
To update dependencies, run `make dev-update-dependencies`. this installs `direct_dependencies.txt` in the project folder .venv.  When you're happy with the result, run `make dev-freeze-dependencies` to update the frozen requirements file.




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
