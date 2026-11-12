# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the stable public theming API (``kaithem.src.rest``)."""

from kaithem.src.tests.helpers import make_client


async def test_style_css_is_only_imports_in_order():
    client = await make_client()
    response = await client.get("/api/theming/style.css")

    assert response.status_code == 200
    assert response.mimetype == "text/css"

    css = (await response.get_data()).decode()
    lines = [line for line in css.splitlines() if line.strip()]

    for line in lines:
        assert line.startswith('@import url("') and line.endswith('");')

    assert css.index("barrel.css") < css.index("kaithem.css")
    assert css.index("kaithem.css") < css.index("install.css")


async def test_style_css_theme_param_overrides_system_theme():
    client = await make_client()
    response = await client.get("/api/theming/style.css?theme=nord")

    css = (await response.get_data()).decode()
    assert '"/static/css/nord.css"' in css
    assert css.index("nord.css") > css.index("kaithem.css")


async def test_style_css_empty_theme_falls_back_to_system_theme():
    client = await make_client()
    fallback = await client.get("/api/theming/style.css")
    empty = await client.get("/api/theming/style.css?theme=")

    assert await empty.get_data() == await fallback.get_data()


async def test_style_css_rejects_unsafe_theme():
    client = await make_client()
    response = await client.get(
        "/api/theming/style.css",
        query_string={"theme": 'x"); body { display: none }'},
    )

    assert response.status_code == 400


async def test_install_css_sets_main_font():
    client = await make_client()
    response = await client.get("/api/theming/install.css")

    assert response.status_code == 200
    assert response.mimetype == "text/css"
    assert "--main-font:" in (await response.get_data()).decode()


async def test_legacy_dynamic_css_route_is_gone():
    client = await make_client()
    response = await client.get("/dynamic.css/123")

    assert response.status_code == 404


async def test_page_template_links_one_stylesheet():
    from kaithem.src import pages, quart_app

    async with quart_app.app.test_request_context("/"):
        html = pages.render_jinja_template(
            "pagetemplate.j2.html",
            _k_usr_page_theme="/static/css/nord.css",
        )

    assert html.count("/api/theming/style.css") == 1
    assert "/dynamic.css/" not in html
    assert 'src="/static/js/style.mjs"' in html
    assert "nord.css" in html
