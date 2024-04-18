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
> Amidst the mists and fiercest frosts,
>
> with stoutest wrists and loudest boasts,
>
> He thrusts his fists against the posts,
>
> And still insists he sees the ghosts.

Kaithem is Linux home/commercial automation server written in pure Python(3.10 and up). Not tested outside of Linux. Resource usage is low enough to run well on the Raspberry Pi.

You automate things by directly writing python and HTML via a web IDE, or by using the built-in Chandler module, which is a full web-based lighting aud audio control board with a visual programming language adding interactivity.

Installation 🌲
============
>The careful text-books measure
>
>  (Let all who build beware!)
>
> The load, the shock, the pressure
>
>  Material can bear.


```bash
git clone --depth 1 https://github.com/EternityForest/KaithemAutomation
cd KaithemAutomation
```

Now you have the repo cloned, all the relevant commands are in the Makefile.
This is an interpreted package, and we use Poetry and pipx,
but we also use Make just to keep commands in one handy place.


### Install system packages 🔠

Many of these have to do with audio features, not all are needed. See Makefile for what is actually
installed. This also installs virtualenv support.

It installs the full suite of GStreamer plugins, and OpenCV
for NVR object detection, so it's a bit heavy.

```bash
make root-install-system-dependencies
```

### Get pipx and Poetry 🌻

Skip this if you already have them!

```bash
# pipx is a wonderful tool that installs
# Applications in virtual environments
# and makes them available on the command line.

sudo apt install pipx

python3 -m pipx ensurepath

# Poetry manages project
# specific virtual environments
pipx install poetry
```

After doing this, log out and log back into the py.
The program doesn't appear in your usable packages until you do that, because Debian strangely enough doesn't have the directory
on PATH by default

### Install kaithem in the project folder virtualenv 🍱

Now that you have the system dependencies, you should have pipx from your package manager.

cd into the folder you cloned, probably with
`cd ~/KaithemAutomation`

```bash
# This line tells Poetry to put
# it's virtualenv right in the project folder
# Where apps like VS Code will know how to work with it
# If you intend to do any development.

# If you already have a .venv in your folder, it
# May be best to delete it and start over.
poetry config --local virtualenvs.in-project true

# This config setting is needed on many platforms,
# the keyring is not used with Kaithem and on
# some systems enabling it crashes everything.
poetry config --local keyring.enabled false

poetry install -v

# Poetry will run it in the virtualenv
poetry run python dev_run.py

# Hit Ctrl-C to stop. may need to try a few times if there are mamy active threads, or just wait a few.

# On some systems, to use audio mixing
# You may need to run 'sudo make root-use-pipewire-jack'
# And prefix everything that uses JACK with pw-jack

# pw-jack poetry run python dev_run.py


```

Expect this to take a few minutes.  If it gets stuck at Preparing...
it is probably not actually stuck and just needs a few.  It should only be 15mins max though, at least on a Pi4.

Then visit http://YOUR_PI_ADDRESS:8002/index and log in with your normal Linux username and password.

Most likely it will be http://raspberrypi.local:8002/index  if you
kept the defaults when installing.


Tips and Troubleshooting ⁉️
========================
> So, when the buckled girder
>
>  Lets down the grinding span,
>
> The blame of loss, or murder,
>
>  Is laid upon the man.
>
>    Not on the Stuff — the Man!

### Access from Anywhere 🌍

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
> Good men, the last wave by, crying how bright
>
> Their frail deeds might have danced in a green bay,
>
> Rage, rage against the dying of the light.

(See [Full Changelog](kaithem/src/docs/changes.md))
