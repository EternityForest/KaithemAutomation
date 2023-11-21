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


### Dependencies for devs
To update dependencies, run `make dev-update-dependencies`.

This installs `direct_dependencies.txt` in the project folder .isolated_venv, uses that to build
a new `requirements_frozen.txt`, and installs that into the main .venv.

The reason we do this is so that we always have a non `system-site-packages` venv to test in,
but also



Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
============

### 0.71.2
- :bug: Fix contextInfo > context_info snake case bug
- :bug: Pipewire stuttering in some cases
- :bug: Fix page editors


### 0.71.1
- :bug: Further minor CSS work
- :bug: Fix mixing board not working on Firefox


### 0.71.0

- :bug: Further minor CSS work
- :sparkles: iot_devices now comes from Pip. There is no longer any need for git-lfs
- :bug: manually disabling a default tag alert
- :bug: Fix mixer channels not immediately connecting
- :bug: Bump scullery version to fix bugwhere similarly named JACK ports got confused
- :bug: Fix missing snake_compat.py

### 0.70.0
This release has some big changes to the install process, but not many to the
functionality.  Expect a few bugs in the next few versions as we rewrite old code to be more in line with best practices.

- :bug: Fix bogus "sound did not report as playing" message
- :sparkles: "Make file publically acessible" option in the upload for file resources.
- :bug: Fix disabling resource serving
- :sparkles: Dmesg viewer
- :sparkles: Simple_light is now the default theme, as Chrome can on some devices be unhappy with complex themes
- :bug: Improve slow/hanging shutdown
- :bug: Fix Mixer processes hanging around when they should not be
- :sparkles: Let's try to stick to Semantic Versioning for future releases
- :sparkles: Mixer can now accept m3u and m3u8 URLs as sources(Looped, high latency)
- :sparkles: Chandler cues have a "Trigger Shortcut" option and will trigger cues in other scenes having that shortcut code.
- :coffin: None of that included thirdparty stuff!  Now we use Pip dependencies
- :bug: Disenhorriblize the install instructions
- :recycle: Refactor the Chandler Python
- :coffin: Remove non-MPV audio backends
- :coffin: Remove codemirror config options
- :coffin: Remove reap library
- :coffin: Remove old jackd2 stuff 
- :coffin: Remove embedded python3 docs
- :sparkles: Simple_light is now the default theme, as Chrome can on some devices be unhappy with complex themes
- :sparkles: The buttonbar CSS class has been changed to tool-bar
- :coffin: Remove embedded python3 docs
- :sparkles: jackmixer now uses pipewire directly
- :coffin: The page header including in user pages is deprecated.  Use <%inherit file="/pagetemplate.html" /> in your code.
- :coffin: BREAKING: the styling on .sectionbox, section, and article is gone. Use .window and .card.
- :sparkles: Work on getting rid of inline styles. We are moving to a custom [CSS Framework](https://eternityforest.github.io/barrel.css/) See css.md in the docs folder.
- :coffin: MAJOR BREAKING user facing APIs are now snake_case. If you see anything not snake_case, it's deprecated.
- :sparkles: Jinja2 support in user-created pages. Mako user pages are deprecated and will eventually be removed.
- :coffin: Remove ancient example modules that had accumulated useless stuff.

License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.
However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.

Some images used in theming are taken from this site: http://webtreats.mysitemyway.com/ and may be considered non-free
by some due to a restriction on "redistribution as-is for free in a manner that directly competes with our own websites."
However they are royalty free for personal and commercial use ad do not require attribution, So I consider them appropriate
for an open project

Some icons from the silk icon set(http://www.famfamfam.com/lab/icons/silk/) have also been used under the terms of the Creative Commons Attribution license.
