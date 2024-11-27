# NOTICE
# This file is full of awful hacks to deal with things that should be more modular
# And testable and not need so much context.

# It starts the whole app, pointed at a ram sandbox, to run things.

import sys

if "--collect-only" not in sys.argv:
    import builtins
    import os
    import shutil

    import kaithem
    import kaithem.src.config

    if os.path.exists("/dev/shm/kaithem_tests"):
        shutil.rmtree("/dev/shm/kaithem_tests")

    os.makedirs("/dev/shm/kaithem_tests/plugins/Test")

    old_open = open

    def open2(path, mode="r", *args, **kwargs):
        if not (str(path).startswith("/dev/shm/")) and not path == "/dev/null":
            if "w" in mode or "a" in mode:
                if "__pycache__" not in str(path):
                    raise RuntimeError(
                        "Unit testing is not allowed to write outside of /dev/shm"
                    )

        return old_open(path, mode, *args, **kwargs)

    builtins.open = open2

    cfg = {
        "ssl_dir": "/dev/shm/kaithem_tests/ssl",
        "site_data_dir": "/dev/shm/kaithem_tests",
        # Prevent it from getting IP geolocation every time
        "location": "0.123,0.345",
        "log_format": "normal",
        "local_access_only": True,
    }

    pp = """
import os

import kaithem.api.chandler as chandlerapi


def foo_command(x: str):
    "This docstring shows up in the logic editor"
    # Trigger an event in every group
    chandlerapi.trigger_event(x)

    # Jump to any cue that has the shortcut
    chandlerapi.shortcut(x)
    return True

chandlerapi.add_command("foo_command", foo_command)
    """

    pt = """
{% extends "pagetemplate.j2.html" %}

{% block title %}Title Here{% endblock %}

{% block body %}
<main>
    <section class="window paper">
        <h2>Path</h2>

        {% for i in path %}
        <p>{{i}}</p>
        {% endfor %}

        <h2>URL Params</h2>
        <p>{{kw}}</p>

    </section>
</main>
{% endblock %}
    """

    test_group = """
active: true
alpha: 1
backtrack: true
blend: normal
blend_args: {}
bpm: 60
command_tag: ''
crossfade: 0
cues:
c1:
    length: 0.5
    number: 10000
    track: false
    values:
    /unit_testing/t2:
        value: 183.0

default:
    length: 0.5
    number: 5000
    values:
    /unit_testing/t1:
        value: 132.0
default_next: ''
display_tags: []
event_buttons: []
hide: false
info_display: ''
midi_source: ''
mqtt_server: ''
mqtt_sync_features: {}
music_visualizations: ''
notes: ''
priority: 50
slide_overlay_url: ''
slideshow_layout: |
<style>
    slideshow-app {
        display: flex;
        flex-wrap: wrap;
        flex-direction: row;
    }

    main{
        display: flex;
        flex-direction: column;
        flex-grow:10;
    }

    media-player {
        flex-grow: 5;
    }

    .sidebar {
        background: linear-gradient(175deg, rgba(36,36,36,1) 0%, rgba(77,77,77,1) 100%);
        max-width: calc(max(30%, min(24em, 100%) ));
        text-wrap: wrap;
    }

</style>


<slideshow-app>
    <main>
        <header></header>
        <media-player></media-player>
        <footer></footer>
    </main>
    <div class="sidebar" v-if="cueText" v-html="cueText">
    </div>
</slideshow-app>
sound_output: ''
utility: false
uuid: efcae37b3e78437cad5098eadf3a172d

    """

    with open("/dev/shm/kaithem_tests/plugins/Test/__init__.py", "w") as f:
        f.write(pp)

    with open("/dev/shm/kaithem_tests/plugins/Test/template.html", "w") as f:
        f.write(pt)

    os.makedirs("/dev/shm/kaithem_tests/chandler/groups")

    with open(
        "/dev/shm/kaithem_tests/chandler/groups/unit_testing.yaml", "w"
    ) as f:
        f.write(test_group)

    kaithem.initialize_app(cfg)
    # TODO Sound can't be imported before config init, eventually
    # A refactor should fix that
    import kaithem.src.sound  # noqa

    kaithem.src.sound.select_backend("test")
