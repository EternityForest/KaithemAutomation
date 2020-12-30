

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
<%!
#Code Here runs once when page is first rendered. Good place for import statements.
%>

<%
__doc__= "#Python Code here runs every page load"
%>

<h2>{basename}</h2>
<title>{basename}</title>

<div class="sectionbox">
  Content here
</div>
"""


def default(basename, **kw):
    return{
        "resource-type": "page",
        "body": defaulthtml.format(basename=basename),
        'require-method': ['GET', 'POST'],
        'require-permissions': [],
        'resource-timestamp': int(time.time()*1000000),
        'resource-type': 'page'
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
        'resource-type': 'page'
    }


templates = {'default': default, 'freeboard': freeboard}


vue = """
<div id="app">
  {{ message }}
</div>
var app = new Vue({
  el: '#app',
  data: {
    message: 'Hello Vue!'
  }
})
"""
