# Widgets

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Widgets

> Auto-generated documentation for [widgets](../../../api/widgets.py) module.

- [Widgets](#widgets)
  - [PeerInfo](#peerinfo)
  - [peer_info_for_connection](#peer_info_for_connection)
  - [widget_docstring](#widget_docstring)

## PeerInfo

[Show source in widgets.py:44](../../../api/widgets.py#L44)

#### Signature

```python
class PeerInfo: ...
```



## peer_info_for_connection

[Show source in widgets.py:49](../../../api/widgets.py#L49)

Get the peer address for a connection

#### Signature

```python
def peer_info_for_connection(connection_id: str): ...
```



## widget_docstring

[Show source in widgets.py:6](../../../api/widgets.py#L6)

Example code:

```python
from kaithem.api.widgets import APIWidget

t = APIWidget(echo=False, id="YourWidgetID")

def f(user: str, value, connection_id: str):
    t.send_to(f"Echoing {value} from {user} on {connection_id}", connection_id)

t.attach2(f)

```

{% extends "pagetemplate.j2.html" %}

{% block title %} {basename} {% endblock %}

{% block body %}

<script type="module">
    import {APIWidget} from "/static/js/widget.mjs?"
    let api_link = new APIWidget("{{t.uuid}}");

    api.upd = (val) => alert(val)
    api.send("MyValue")
</script>

{% endblock %}

```

#### Signature

```python
def widget_docstring(): ...
```