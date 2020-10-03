


import time

freeboardhtml="""
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
    '/static/js/freeboard/extralibs/math.min.js',
    '/static/js/freeboard/extralibs/keyboard.min.js',
    '/static/js/freeboard/extralibs/luxon.min.js'
]
%>


<freeboard-data>
</freeboard-data>

<title>Dashboard</title>

${{kaithem.web.freeboard(page, kwargs, plugins)}}
<style>
     /*
     Here you can adjust the theme of your board
      */
    :root {{
        --main-bg-color: #534d5c;
        --main-bg-size: default;
        /*--main-bg-image: */   /*Default is a data URI*/
          --box-bg-color:#444659d7;
        --widget-bg-color: #A1A1A1;
        --border-color: #26362f;
        --bar-bg-color: #534152;
        --fg-color: #cfcfcf;
        --reverseout-bg: #dddddd;
        --reverseout-fg: black;
        --greyout-color: rgba(200,200,200,0.8);
        --dialog-bg: rgba(0,0,0,0.25);
        --highlight-color:  rgb(153, 235, 0);
        --main-font: B612;

        --pane-border-radius: 1.2em;
        --pane-padding:0.6em;
        --dialog-border-radius:2em;
        --border-width:2px;
        --border-style: solid;
        --button-fg-color: #b1b1b1;

        --header-fg-color: white;
        --header-bg-color:#444659;

    }}

    @font-face {{
        font-family:  B612;
        src: url(/static/fonts/b612/b612-v4-latin-regular.woff2);
    }}
</style>
"""



defaulthtml="""
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

def default(basename,**kw):
    return{
    "resource-type":"page",
    "body":defaulthtml.format(basename=basename),
    'require-method': ['GET', 'POST'],
    'require-permissions': [],
    'resource-timestamp': int(time.time()*1000000),
    'resource-type': 'page'
    }


def freeboard(basename,**kw):
    return{
    "resource-type":"page",
    "body":freeboardhtml.format(basename=basename),
    'no-navheader':True,
    'no-header': True,
    'require-method': ['GET', 'POST'],
    'require-permissions': [],
    'resource-timestamp': int(time.time()*1000000),
    'resource-type': 'page'
    }




templates={'default': default,'freeboard': freeboard}



vue="""
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

