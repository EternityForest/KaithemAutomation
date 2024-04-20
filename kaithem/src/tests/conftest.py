# NOTICE
# This file is full of awful hacks to deal with things that should be more modular
# And testable and not need so much context.

# It starts the whole app, pointed at a ram sandbox, to run things.


import os
import shutil

import kaithem
import kaithem.src.config

if os.path.exists("/dev/shm/kaithem_tests"):
    shutil.rmtree("/dev/shm/kaithem_tests")

os.makedirs("/dev/shm/kaithem_tests/plugins/Test")

cfg = {
    "ssl-dir": "/dev/shm/kaithem_tests/ssl",
    "site-data-dir": "/dev/shm/kaithem_tests",
    # Prevent it from getting IP geolocation every time
    "location": "0,0",
    "log-format": "normal",
}


pp = """
import os
import kaithem.api.web as webapi


tp = os.path.join(os.path.dirname(__file__), "template.html")


def handle_page(*path, **kw):
    return webapi.render_jinja_template(tp, path=path, kw=kw)


webapi.add_simple_cherrypy_handler("plugin_test", permission="", handler=handle_page)


import kaithem.api.chandler as chandlerapi


def foo_command(x: str):
    "This docstring shows up in the logic editor"
    # Trigger an event in every scene
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

with open("/dev/shm/kaithem_tests/plugins/Test/__init__.py", "w") as f:
    f.write(pp)

with open("/dev/shm/kaithem_tests/plugins/Test/template.html", "w") as f:
    f.write(pt)

kaithem.initialize_app(cfg)
# TODO Sound can't be imported before config init, eventually
# A refactor should fix that
import kaithem.src.sound  # noqa

kaithem.src.sound.select_backend("test")
