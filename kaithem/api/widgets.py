from kaithem.src import widgets


def widget_docstring():
    """

        Example code:
        Python setup code:

        ```python
    from kaithem.api.widgets import APIWidget

    t = APIWidget(echo=False, id="YourWidgetID")

    def f(user: str, value, connection_id: str):
        t.send_to(f"Echoing {value} from {user} on {connection_id}", connection_id)

    t.attach2(f)

    # This returns an HTML string to embed in a page
    # which also includes /static/js/widget.js

    t.render("js_var_name")
        ```

        HTML/Jinja2
        ```html
    {% extends "pagetemplate.j2.html" %}

    {% block title %} {basename} {% endblock %}

    {% block body %}

    <script type="module">
        import { api } from '/apiwidget/esm/${api.uuid}'
        api.upd = (val) => alert(val)
        api.send("MyValue")
    </script>

    {% endblock %}

        ```

    """


APIWidget = widgets.APIWidget
