![AI generated picture of a tavern](kaithem/data/static/img/nov23-ai-watercolor-tavern.webp)


![Linux](badges/linux.png)
![Single Board Computer badge](badges/sbc.png)
![DMX](badges/dmx.png)
![Python](badges/python.png)

![Offline First](badges/offline-first.png)
![GPLv3 Badge](badges/gpl-v3.png)
![Pre-commit Badge](badges/pre-commit.png)
![Makefile Badge](badges/makefile.png)
![Ten Year Project](badges/ten-years.png)
![Pytest](badges/pytest.png)

Kaithem is Linux home/commercial automation server written in pure Python(3.10 and up). Not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

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

### Development

Info for devs here on the wiki (https://github.com/EternityForest/KaithemAutomation/wiki/Development)


Recent Changes
============
(See [Full Changelog](kaithem/src/docs/changes.md))
