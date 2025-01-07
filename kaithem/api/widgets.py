import dataclasses

from kaithem.src import widgets


def widget_docstring():
    """

        Example code:

    ```python
    from kaithem.api.widgets import APIWidget

    t = APIWidget(echo=False, id="YourWidgetID")

    def f(user: str, value, connection_id: str):
        t.send_to(f"Echoing {value} from {user} on {connection_id}", connection_id)

    t.attach2(f)

    ```html
    {% extends "pagetemplate.j2.html" %}

    {% block title %} {basename} {% endblock %}

    {% block body %}

    <script type="module">
        import {APIWidget} from "/static/js/widget.mjs?cache_version=c6d0887e-af6b-11ef-af85-5fc2044b2ae0"
        let api_link = new APIWidget("{{t.uuid}}");

        api.upd = (val) => alert(val)
        api.send("MyValue")
    </script>

    {% endblock %}

    ```

    """


@dataclasses.dataclass
class PeerInfo:
    address: str
    battery: str | None


def peer_info_for_connection(connection_id: str):
    """Get the peer address for a connection"""
    c = widgets.ws_connections[connection_id]
    return PeerInfo(address=c.peer_address, battery=c.batteryStatus)


APIWidget = widgets.APIWidget
