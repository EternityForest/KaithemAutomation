# SPDX-License-Identifier: GPL-3.0-or-later

import time

defaulthtml = """
{{% extends "pagetemplate.j2.html" %}}

{{% block title %}} {basename} {{% endblock %}}

{{% block body %}}

<main>
  <h2>{basename}</h2>
  <section>
    Content here
  </section>
</main>

{{% endblock %}}
"""


servicehtml = """
{result}
"""

vueApp = r"""
<%inherit file="/pagetemplate.html" />
<%block name="title">{basename}</%block>

<main>
<script src="/static/js/thirdparty/vue3.js"></script>


<section id="app">
<h2>{basename}</h2>

\{\{message\}\}
</section>

</main>

<script>
  const { createApp, ref } = Vue;

      const app = createApp({
        data() {
          return {
            message: "Hello World!"
          }
        }
      }).mount('#app')
</script>
"""


def default(basename, **kw):
    return {
        "template_engine": "jinja2",
        "resource": {"type": "page", "modified": int(time.time())},
        "body": defaulthtml.format(basename=basename),
        "require_method": ["GET", "POST"],
        "require_permissions": [],
        "no_navheader": True,
        "no_header": True,
    }


def vue(basename, **kw):
    return {
        "resource": {
            "type": "page",
            "modified": int(time.time()),
        },
        "body": vueApp.replace("{basename}", basename),
        "require_method": ["GET", "POST"],
        "require_permissions": [],
        "no_navheader": True,
        "no_header": True,
    }


# For making a web API call
def service(basename, **kw):
    return {
        "resource": {
            "type": "page",
            "modified": int(time.time()),
        },
        "body": servicehtml,
        "no_navheader": True,
        "no_header": True,
        "require_method": ["GET", "POST"],
        "require_permissions": [],
        "template_engine": "jinja2",
    }


templates = {
    "default": default,
    "service": service,
    "vue3": vue,
}
