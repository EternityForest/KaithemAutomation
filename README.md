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
![Ruff](badges/ruff.png)
![Poetry](badges/poetry.png)
> Amidst the mists and fiercest frosts,\
> with stoutest wrists and loudest boasts,\
> He thrusts his fists against the posts,\
> And still insists he sees the ghosts.

Kaithem is Linux home/commercial automation server written in pure Python(3.10 and up). Not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE, or by using the built-in Chandler module, which is a full web-based lighting aud audio control board with a visual programming language adding interactivity.

## Installation 🌲

>The careful text-books measure\
>  (Let all who build beware!)\
> The load, the shock, the pressure\
>  Material can bear.


First you'll need to get [pipx](https://pipx.pypa.io/stable/installation/) if you haven't yet.

```bash
sudo apt install pipx git
python3 -m pipx ensurepath
```

Next you can clone the git repo and install

```bash
git clone --depth 1 https://github.com/EternityForest/KaithemAutomation
cd KaithemAutomation
pipx install --verbose .

sudo /home/pi/.local/bin/kaithem-scripts root-install-system-dependencies```


### System Configuration
kaithem-scripts provides some helpful utilities to set up the system.
Note that these are also accessible as Make targets n the repo.

```bash

# Currently, most distros don't have pipewire JACK enabled by default, which
# is needed for the audio mixing features.
kaithem-scripts root-use-pipewire-jack

# This activates a maxvolume service, which sets volume to full at boot.
kaithem-scripts user-max-volume-at-boot

# Linux by default has a LOT of stuff that writes
# excessively to the SD card. On a raspberry pi this
# Should make the system much more reliable without
# making anything work differently, except for putting logs in RAM
kaithem-scripts root-install-sd-protection

# Sets up a collection of misc tweaks that are recommended for kaithem.
kaithem-scripts root-install-linux-tweaks

# Installs Mosquitto and sets it up to allow anonymous clients.
kaithem-scripts root-enable-anon-mqtt

# Installs Mosquitto and sets it up to allow anonymous clients.
kaithem-scripts root-uninstall-bloatware

# Set up the Pi to display the Kaithem homepage(Can configure redirect in settings)
# On boot in a fullscreen kiosk
kaithem-scripts root-install-kiosk



```




## Manual dev install

See the [wiki page](https://github.com/EternityForest/KaithemAutomation/wiki/Development)


Tips and Troubleshooting ⁉️
========================
> So, when the buckled girder\
>  Lets down the grinding span,\
> The blame of loss, or murder,\
>  Is laid upon the man.\
>    Not on the Stuff — the Man!

### Access from Anywhere 🌍

See Wiki Tutorial
(https://github.com/EternityForest/KaithemAutomation/wiki/Remote-Access)


#### Still broken?

Unfortunately, it doesn't work on pi, you'll need to prefix stuff that should use jack with pw-jack.

```bash
pw-jack poetry run python dev_run.py
```
Kaithem's installer does this automatically when you use

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

To run as a systemd user service(Runs as soon as you log in or the desktop/kiosk starts)
Expect the command to take about 15 minutes.


```bash
sudo make root-use-pipewire-jack
make user-start-kaithem-at-boot
```


### Make sure the SD card stays fresh 🍃

On a dedicated system, you probably want to disable a buch of
stuff the Pi comes with that normally writes to the SD card all the time,
disable auto update for most system packages(Assuming you're on a private network),
and a few other tweaks.

```bash
sudo make root-install-linux-tweaks
sudo make root-install-sd-protection
```

### Development 🖥️

Info for devs here on the wiki (https://github.com/EternityForest/KaithemAutomation/wiki/Development)


Recent Changes 🕗
============
> Good men, the last wave by, crying how bright\
> Their frail deeds might have danced in a green bay,\
> Rage, rage against the dying of the light.

(See [Full Changelog](kaithem/src/docs/changes.md))
