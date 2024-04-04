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

See Wiki Tutorial
(https://github.com/EternityForest/KaithemAutomation/wiki/Remote-Access)

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

### Development

Info for devs here on the wiki (https://github.com/EternityForest/KaithemAutomation/wiki/Development)


Recent Changes(See [Full Changelog](kaithem/src/docs/changes.md))
============


### 0.77.0

This release was going to be a simple polish and bugfix.... However, I discovered some
subtle bugs related to a legacy feature, and this turned into a pretty big cleanup effort in some older code, removing several old features.

While this release should be ready and usable,
and has been tested, you should use it with caution just due to the scope of changes involved.

Previously you could save device config both in
modules and a global devices list.  That and several other aspects of device config were
causing lots of user and implementation complexity.

Now you can only save them in modules. Keeping them in modules lets you use the import/export features and is much more powerful. You can still load legacy devices until the next version.  Please make a module and move your devices there, you can set where to save a device on the device page.


- :bug: Restore the broken optimization for events that don't need to poll
- :bug: Fix fixture types window being too small
- :bug: Fix nuisance error when deleting mixer channel
- :bug: Fix enttec open atapter showing as disconnected when it wasn't
- :bug: Fix unsupported device warnings feature
- :bug: Displayed value in UI correctly updates for refresh button
- :bug: Fix devices UI setting bad value when you specified 'false'
- :bug: Remove caching on modules listing that was casuing issues.
- :bug: Notification handler code was spawning tons of threads bogging everything down.

- :lipstick: Better combo box feel
- :lipstick: Icons switched to [MDI Icons](https://pictogrammers.com/library/mdi/) for harmony with other automation platforms.
- :lipstick: More compact strftime default


- :coffin: Remove the complicated and never-used system for creatig device types in events
- :coffin: Remove the legacy device type system and all the devices from before iot_devices.  All were unmaintained and some may have been broken by hardware vendors.
- :coffin: Remove the input and output binding feature of devices.  Chandler can do everything it could, and it was not a clean separation of device and logic.
- :coffin: Remove the bluetooth admin panel. Try [bluetuith](https://darkhz.github.io/bluetuith/)!
- :coffin: Remove some old junk files
- :coffin: kaithem.gpio is gone. Use the GPIO devices in the device manager for this purpose.
- :sparkles: BREAKING: The name of a device stored in a module is independet of module name or folder
- :sparkles: BREAKING: / now used to separate subdevice names
- :sparkles: BREAKING: Device config dirs now end with .config.d, automatic migration is impossible, however nothing except the DemoDevice uses conf dirs.
- :sparkles: BREAKING: It is no longer possible to save devices outside modules. Please migrate all devices to a module(Legacy devices still load, they just can only be saved into modules.)

- :hammer: Use pre-commit


Specific devices removed:

- BareSIP
- Kasa
- Sainsmart Relay boards
- RasPi Keypad
- JACK Fluidsynth
- Espruinio

Some may return in iot_devices later.

### 0.77.0 Beta

- :bug: Autosave did not save deletions, only changes
- :bug: Fix chandler slide overlay refreshing over and over
- :bug: Chandler missing fixtures info in UI until you modify something
- :bug: Fix some media files unable to be served to the web player
- :bug: Cues now reentrant by default again
- :bug: Fix fade in not displayed after loading
- :bug: Fix sound fade in for non-web audio
- :bug: Fix sound "windup"
- :bug: Chandler and mixer state could get out of sync if the websocket disconnected and reconnected
- :sparkles: Move universe and fixture setup to a separate chandler setup page
- :sparkles: Can now rename cues
- :bug: Fix web player not starting at the right time after needing manual click to start
- :sparkles: Can now customize the HTML for the scene web player
- :sparkles: Chandler cues can now have Markdown text content to show in the slideshow sidebar
- :sparkles: User settings are instant, no more manual save step
- :sparkles: Cues inherit rules from the special \__rules\__ cue if it exists.
- :sparkles: If sound_fade_in is 0, then use the cue lighting fade for the sound as well if it exists
- :coffin: nosecurity command line flag removed
- :sparkles: Permissions have been consolidated.
- :sparkles: Chandler has consoleNotification command to send a message to the dashboard
- :bug: Fix bug where scene timers would mess up and repeatedly fire


### 0.76.0
- :bug: Fix utility scene checkbox in chandler not showing correct value
- :bug: Fix Chandler relative length with web slides
- :bug: Fix iot_devices not setting the default
- :bug: Fix shortcut code normalization(10.0 is treated same as 10)
- :bug: Upload new chandler scene adds to rather than replaces the existing scenes
- :bug: Fix broken highlighting in some themes
- :bug: Fix support for midi devices with odd chars in the names
- :sparkles: Can hide a scene in runtime mode
- :sparkles: Chandler can now import and export audio cues in a scene as M3U playlists(With fuzzy search for broken paths!)
- :sparkles: Confirm before delete cues
- :sparkles: Add ability to move Chandler rules around
- :sparkles: Scene display tags can now be inputs
- :sparkles: Don't log thread start/stop if they have generic Thread-xx names
- :sparkles: Chandler updated to work with Vue3
- :sparkles: Chandler has autosave(10min)
- :sparkles: Chandler save setup and save scenes buttons now just one save button.
- :sparkles: Chandler has a proper loading animation
- :coffin: Raw cue data text view has been removed

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

License Terms
=============
The original python code and and the HTML files under /pages are licensed under the GNU GPL v3.

However, Kaithem includes code copied unmodifed from many other open source projects. under various licenses. This code is generally in a separate folder and accompanied by the corresponding license.