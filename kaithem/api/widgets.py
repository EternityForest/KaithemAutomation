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
        import {APIWidget} from "/static/js/widget.mjs"
        let api_link = new APIWidget("{{t.uuid}}");

        api.upd = (val) => alert(val)
        api.send("MyValue")
    </script>

    {% endblock %}

    ```

    """


APIWidget = widgets.APIWidget
