# Kaithem Automation

![AI generated banner of a boardwalk tavern](kaithem/data/static/img/banner.avif)

![Linux](badges/linux.png)
![Python](badges/python.png)
![Ten Year Project](badges/ten-years.png)

![Offline First](badges/offline-first.png)
![GPLv3 Badge](badges/gpl-v3.png)
![Single Board Computer badge](badges/sbc.png)

![Pytest](badges/pytest.png)
![Ruff](badges/ruff.png)


> Amidst the mists and fiercest frosts,\
> with stoutest wrists and loudest boasts,\
> He thrusts his fists against the posts,\
> And still insists he sees the ghosts.

Kaithem is Linux home/commercial automation server written in pure Python(3.10 and up). Resource usage is low enough to run well on the Raspberry Pi from an SD card

You automate things by directly writing python and HTML via a web IDE, or by using the built-in Chandler module, which is a full web-based lighting aud audio control board with a visual programming language.

## Screenshots 🏕️

### No-code automation logic editor

![Logic Editor](screenshots/cue-logic-mobile.avif)

### JACK/Pipewire audio mixer with FX

![Audio Mixer](screenshots/audio-mixer-mobile.avif)

### Lighting presets

![Preset Selector](screenshots/preset-selection.avif)

### Trigger Lighting and automation cues

![Cues List](screenshots/cues-list.avif)

### Device Integrations

![Device Page](screenshots/device-page.avif)



See the barrel.css [demo](https://eternityforest.github.io/barrel.css/) for more themes


## Installation 🌲

>The careful text-books measure\
>  (Let all who build beware!)\
> The load, the shock, the pressure\
>  Material can bear.


First you'll need to get [pipx](https://pipx.pypa.io/stable/installation/) and uv, if you haven't yet.  In the future, pipx will likely not be needed at all, for now this seems to be the most convenient way to get uv.

```bash
sudo apt install pipx
# This may prompt you to log out and log back in
python3 -m pipx ensurepath
pipx install uv
uv tool update-shell
```

Next you can just install it right from PyPi!
Be aware that pipx takes a while on a raspberry pi.

```bash
uv tool install --force kaithem

kaithem-scripts root-install-system-dependencies

```

To get the latest dev version, do this instead.  You probably don't want this.
```bash
uv tool install --force --from git+https://github.com/EternityForest/KaithemAutomation kaithem
```

### System Configuration 🛠️

> So, when the buckled girder\
>  Lets down the grinding span,\
> The blame of loss, or murder,\
>  Is laid upon the man.\
>    Not on the Stuff — the Man!

kaithem-scripts provides some helpful utilities to set up the system.

Scripts starting with . will do sudo by themselves, you call them as your normal user,
and sudo will prompt you if needed.  This is because running uv/pipx scripts directly with root
would need extra setup.

```bash

# Launch at startup
kaithem-scripts user-start-kaithem-at-boot

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
# On boot in a fullscreen kiosk, under the default user.

# Should work on non-pi systems that use lightdm too.
# Note this reconfgures lots of stuff and can't be undone except manually.
kaithem-scripts root-install-kiosk

# Sets sudo to passwordless by creating a /etc/sudoers.d/sudo-nopasswd file
# 0.89.0+ only
kaithem-scripts root-enable-passwordless-sudo

```

## Manual dev install 🖐️

Info for devs here on the wiki (https://github.com/EternityForest/KaithemAutomation/wiki/Development)


Recent Changes 🕗
============
> Good men, the last wave by, crying how bright\
> Their frail deeds might have danced in a green bay,\
> Rage, rage against the dying of the light.

(See [Full Changelog](kaithem/src/docs/changes.md))
