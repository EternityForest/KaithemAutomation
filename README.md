# Kaithem Automation

![AI generated banner of a tavern](kaithem/data/static/img/16x9/kaithem-tavern.avif)

![Linux](badges/linux.png)
![Python](badges/python.png)
![Ten Year Project](badges/ten-years.png)
![Offline First](badges/offline-first.png)
![GPLv3 Badge](badges/gpl-v3.png)
![Single Board Computer badge](badges/sbc.png)
![Pytest](badges/pytest.png)
![Ruff](badges/ruff.png)
![Ruff](badges/uv.png)


> Amidst the mists and fiercest frosts,\
> with stoutest wrists and loudest boasts,\
> He thrusts his fists against the posts,\
> And still insists he sees the ghosts.

Kaithem is Linux home/commercial automation server written in pure Python(3.10 and up). Resource usage is low enough to run well on the Raspberry Pi from an SD card

You automate things by directly writing python and HTML via a web IDE, or by using the built-in Chandler module, which is a full web-based lighting aud audio control board with a visual programming language.

## Screenshots 🏕️

![Cues List](screenshots/cues-list.avif)
![Preset Selector](screenshots/preset-selection.avif)
![Audio Mixer](screenshots/audio-mixer-mobile.avif)
![Logic Editor](screenshots/cue-logic-mobile.avif)
![Device Page](screenshots/device-page.avif)


See the barrel.css [demo](https://eternityforest.github.io/barrel.css/) for more themes


## Installation 🌲


>The careful text-books measure\
>  (Let all who build beware!)\
> The load, the shock, the pressure\
>  Material can bear.


Assuming you're on Debian or similar and have uv installed,
you can run it directly from UV tool.


```bash
sudo apt install -y mpv lm-sensors python3-gst-1.0  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad gstreamer1.0-tools swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly libfluidsynth3 gstreamer1.0-pocketsphinx x42-plugins gstreamer1.0-opencv  gstreamer1.0-vaapi gstreamer1.0-pipewire

uv tool install --force kaithem

# Start it
kaithem

```


### System Configuration 🛠️

> So, when the buckled girder\
>  Lets down the grinding span,\
> The blame of loss, or murder,\
>  Is laid upon the man.\
>    Not on the Stuff — the Man!

For real deployment or adding plugins like Matter support, see the scripts [here](https://github.com/EternityForest/kaithem-scripts/tree/main/debian)



## Dev install 🖐️

Info for devs here on the wiki (https://github.com/EternityForest/KaithemAutomation/wiki/Development)

### Build dependencies
Dashbeard(https://github.com/EternityForest/Dashbeard) must be cloned into the same folder you cloned this repo into.

### Setup

First get all system dependencies as per the main install section.

```bash
uv sync

# Need to set up Rust if you don't already have everything
# All Rust code currently compiles to .wasm
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup target add wasm32-unknown-unknown

# Need install deps to build the frontend with npm
npm install

make build
```

Recent Changes 🕗
============
![AI generated banner of a water snake](kaithem/data/static/img/16x9/lightning-water-snake.avif)

> Good men, the last wave by, crying how bright\
> Their frail deeds might have danced in a green bay,\
> Rage, rage against the dying of the light.

(See [Full Changelog](kaithem/src/docs/changes.md))
