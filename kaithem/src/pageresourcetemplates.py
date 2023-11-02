

import time

freeboardhtml = """
<%doc>
NOTE: This page is self modifying and embeds it's own editor to customize the page!
You should not need to modify this code, except for changing the theme.
Just visit the page with admin permissions to get started.



The layout you create gets saved back to this file in the freeboard-data tag, as standard YAML.
kaithem.web.freeboard() handles the real work of generating the page, and also handles saving.
</%doc>

<%!
#Add your plugins here.
plugins=[
]
%>


<freeboard-data>
</freeboard-data>

<title>Dashboard</title>

${{kaithem.web.freeboard(page, kwargs, plugins)}}

"""


defaulthtml = """
<%inherit file="/pagetemplate.html" />
<%block name="title">{basename}</%block>

<main>
  <h2>{basename}</h2>
  <section>
    Content here
  </section>
</main>
"""


servicehtml = """
${result}
"""

vueApp = """
<%inherit file="/pagetemplate.html" />
<%block name="title">{basename}</%block>

<main>
<script src="/static/js/vue3.js"></script>


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
    return{
        "resource-type": "page",
        "body": defaulthtml.format(basename=basename),
        'require-method': ['GET', 'POST'],
        'require-permissions': [],
        'resource-timestamp': int(time.time()*1000000),
        'resource-type': 'page',
        'no-navheader': True,
        'no-header': True,
    }


def vue(basename, **kw):
    return{
        "resource-type": "page",
        "body": vueApp.replace("{basename}",basename),
        'require-method': ['GET', 'POST'],
        'require-permissions': [],
        'resource-timestamp': int(time.time()*1000000),
        'resource-type': 'page',
        'no-navheader': True,
        'no-header': True,
    }


def freeboard(basename, **kw):
    return{
        "resource-type": "page",
        "body": freeboardhtml.format(basename=basename),
        'no-navheader': True,
        'no-header': True,
        'require-method': ['GET', 'POST'],
        'require-permissions': [],
        'resource-timestamp': int(time.time()*1000000),
    }


#For making a web API call
def service(basename, **kw):
    return{
        "resource-type": "page",
        "body": servicehtml,
        'no-navheader': True,
        'no-header': True,
        'require-method': ['GET', 'POST'],
        'require-permissions': [],
        'resource-timestamp': int(time.time()*1000000),
        'template-engine': "mako"
    }

templates = {'default': default, 'freeboard': freeboard, 'service': service, "vue3": vue}
