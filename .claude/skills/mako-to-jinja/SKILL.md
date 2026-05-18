---
description: Migrate Mako template files to Jinja2, and migrate any Python code that uses the file.
---

## Project info

Jinja2 files are rendered using
'pages.render_jinja_template(file, **kwargs_for_template)'

from kaithem.pages

Reusable Jinja templates live in /kaithem/src/html/jinjatemplates. That's only for geberic reusable templates.

Normal page files are in appropriate subdirectories of /kaithem/src/html/

Paths given to render_jinja_template are relative to /kaithem/src/html/


Almost every page uses a template.

Most Jinja pages look like this, pagetemplate.j2.html replaces the old pageheader and
pagefooter imports.

```
{% extends "pagetemplate.j2.html" %}

{% block body %}

{% endblock %}
```


## Instructions

Grep for the name of the files that render this template, by grepping for the base name of the file in project *.py files

Use a command like `find /home/daniel/Projects/KaithemAutomation -type f -name "*.py" -exec grep -l "foo/bar" {} +`

Find all inline procedural code in the Mako template, and move that code into the function which calls the template.

This code may be embedded in nested loops, you will likely need to preprocess all the data up front in the calling function.

When passing data to the template render function, use dicts with clearly named keys or data classes, rather than tuples or other non self documenting structures.

Convert the mako file to a jinja2 template which uses the data we have preprocessed.  Rename it's extension to `.j2.html`

Convert the python file that loads the template to render this new file. If necessary, move it into the approproate location for jinja templates.

Remember that we need to render it with the Jinja2 environment, not the old Mako context.


Validate Jinja syntax with a command like

`python3 -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('kaithem/src/html/jinjatemplates')); t = env.get_template('modules/index.j2.html'); print('Template syntax OK')" 2>&1`