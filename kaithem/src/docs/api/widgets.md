# Widgets

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Widgets

> Auto-generated documentation for [widgets](../../../api/widgets.py) module.

- [Widgets](#widgets)
  - [widget_docstring](#widget_docstring)

## widget_docstring

[Show source in widgets.py:4](../../../api/widgets.py#L4)

Example code:
Python setup code:

```python
from kaithem.api.widgets import APIWidget

t = APIWidget(echo=False, id="YourWidgetID")

def f(user: str, value, connection_id: str):
t.send_to(f"Echoing {value} from {user} on {connection_id}", connection_id)

t.attach2(f)

# This returns an HTML string to embed in a page
# which also includes /static/js/widget.mjs

t.render("js_var_name")
```

HTML/Jinja2

```html
{% extends "pagetemplate.j2.html" %}

{% block title %} {basename} {% endblock %}

{% block body %}
{{t.render("api")}}

<script>
api.upd = (val) => console.log(val)
api.send("MyValue")
</script>

{% endblock %}

```

#### Signature

```python
def widget_docstring(): ...
```