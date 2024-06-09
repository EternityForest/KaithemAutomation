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
sudo apt install pipx
python3 -m pipx ensurepath
```

Next you can just install it right from PyPi!
Be aware that pipx takes a while on a raspberry pi.

```bash
pipx install --verbose kaithem

kaithem-scripts root-install-system-dependencies

```

### System Configuration

> So, when the buckled girder\
>  Lets down the grinding span,\
> The blame of loss, or murder,\
>  Is laid upon the man.\
>    Not on the Stuff — the Man!

kaithem-scripts provides some helpful utilities to set up the system.

Scripts starting with . need root.

```bash

# Currently, most distros don't have pipewire JACK enabled by default, which
# is needed for the audio mixing features.
kaithem-scripts root-use-pipewire-jack
kaithem-scripts user-restart-pipewire


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

Info for devs here on the wiki (https://github.com/EternityForest/KaithemAutomation/wiki/Development)


Recent Changes 🕗
============
> Good men, the last wave by, crying how bright\
> Their frail deeds might have danced in a green bay,\
> Rage, rage against the dying of the light.

(See [Full Changelog](kaithem/src/docs/changes.md))
