![AI generated picture of a tavern](kaithem/data/static/img/nov23-ai-watercolor-tavern.webp)

Kaithem is Linux home/commercial automation server written in pure python, HTML, Mako, and CSS. It runs on python3, but it is not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE, or by using the built-in Chandler module, which is a full web-based lighting aud audio control board with a visual programming language adding interactivity.

Installation
============

## How to run it!

```bash
git clone --depth 1 https://github.com/EternityForest/KaithemAutomation
cd KaithemAutomation
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


### Access from Anywhere

You can remotely access Kaithem(or any other service you might want!) using zrok(https://zrok.io/).

This service has a lot of features, but you can get started with just a few commands.

First, set up a *strong* password, and be aware that Kaithem has not had third party security audits.

For an extra layer of security, do not share the access URL with anyone who shouldn't have access.

This installs the latest zrok in /usr/local/bin.  You may need to update manually by running root-install-zrok again.

```bash
make root-install-zrok

# This will prompt you for an email address.
# When you get the email, use the activation link.
zrok invite

# The activation link will give you a token
zrok activate <token>

# This creates a systemd service as your user
# which will make kaithem publically available at a randomly generated URL.
# It will automatically start when your user logs in.
# Go to https://api.zrok.io/ to see the status of this share.
make user-setup-zrok-sharing
```

To disable this, just use normal systemd commands:

```bash

# This stops the sharing service
systemctl --user stop kaithem-zrok-share.service
# Stop it from running at boot
systemctl --user disable kaithem-zrok-share.service

```

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

Some systems like to set volume to 40% at boot, at the ALSA mixer level. Try:

```bash
make user-max-volume-at-boot
```
as whatever user you plan to run kaithem under.

You can also try setting volume to full and storing it
```bash
amixer set Master 100%
sudo alsactl store
```

### Sound bad on the Pi?

You might not have pipewire configured correctly.  The pi default config seems
to set the buffer too low. 

Update kaithem and run `make user-set-global-pipewire-conf` as the user that will be doing this stuff, to get some reasonable defaults. `nano ~/.config/pipewire/pipewire.conf` to tweak further.

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


### Dependencies for devs

To update dependencies, run `make dev-update-dependencies`.

This installs `direct_dependencies.txt` in the project folder .isolated_venv, uses that to build
a new `requirements_frozen.txt`, and installs that into the main .venv.

The reason we do this is so that we always have a non `system-site-packages` venv to test in,
but also to let you manually play around in the .venv.

Should you want to clean things or start over, it's best to just burn it to the ground and delete the virtualenvs.


To run inside the isolated virtualenv, deactivate the current virtualenv and run `make dev-run-isolated` 

### Tests
The new unit tests initiative uses pytest.  Use the test_run.py file if you want to run them in the debugger.


Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
============

### 0.75.1
- :bug: Fix chandler scenes sometimes sharing all data for the default cues
- :bug: Fix makefile install process
- :bug: More reliable max-volume-at-boot script
- :sparkles: Web console runs in ~/kaithem/venv if it exists(Change this if desired in kaithem's bashrc)
- :sparkles: Settings page link to set ALSA mixer volume to full

### 0.75.0
- :sparkles: Default page title is now the hostname
- :sparkles: Devices report feature lets you print out all the device settings
- :bug: Nuisance gstreamer output
- :bug: esphome api key correctly marked as secret 
- :sparkles: Improve maps quality
- :sparkles: Chandler shows time at which each scene entered the current cue

### 0.74.0
- :sparkles: Use Terminado and xterm.js to finally provide a proper system console shell!!!
- :bug: Fix recursion issue in device.handle_error
- :bug: Fix chatty logs from aioesphomeapi
- :coffin: Deprecate kaithem.web.controllers
- :sparkles: kaithem.web.add_wsgi_app and add_tornado_app to allow for addon apps from other frameworks.
- :lipstick: Legacy /static/widget.js moved to /static/js/widget.js
- :lipstick: Third party JS moved to /static/js/thirdparty/
- :sparkles: Support AppRise notifications(Configure them in global settings)


### 0.73.2
- :bug: Fix crackling audio on some systems by using the system suggested PipeWire quantum

License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
