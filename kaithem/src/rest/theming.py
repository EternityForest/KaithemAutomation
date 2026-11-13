# SPDX-License-Identifier: GPL-3.0-or-later

"""Stable public theming API.

Kaithem layers several stylesheets: a base design system, Kaithem's own
additions, per-install settings, and a chosen theme.  ``style.css``
flattens that into a single stylesheet link a page can include.
"""

import quart

from kaithem.src import settings_overrides, theming
from kaithem.src.config import config
from kaithem.src.cors import allow_request_subdomains
from kaithem.src.quart_app import app

# Stylesheets loaded before the theme, so the theme can override them.
BASE_STYLESHEETS = (
    "/static/css/barrel.css",
    "/static/css/kaithem.css",
)

# reason.  Internal detail of ``style.css``, not a public API.
DYNAMIC_STYLESHEET = "/api/theming/dynamic.css"


def resolve_theme_url(theme: str) -> str:
    """Turn a theme name or stylesheet URL into a stylesheet URL.

    Registered theme names (see ``theming.cssthemes``) map to their
    URL, anything else is assumed to already be a URL.
    """
    registered = theming.cssthemes.get(theme)
    return registered.css_url if registered else theme


def is_safe_css_url(url: str) -> bool:
    """Reject anything that could break out of the ``@import`` string."""
    return not any(char in url for char in ('"', "\\", "\n", "\r"))


def install_css() -> str:
    """Per-install CSS, currently just the configured UI font."""
    font = settings_overrides.get_val("core/ui_font") or "AtkinsonHyperlegible"
    return f"""
:root {{
    --main-font: {font};
}}
    """


@app.route(DYNAMIC_STYLESHEET, methods=["GET"])
@allow_request_subdomains()
async def theming_install_css():
    """Server-wide stylesheet imported by ``style.css``."""
    response = await app.make_response(install_css())
    response.mimetype = "text/css"
    return response


@app.route("/api/theming/style.css", methods=["GET"])
@allow_request_subdomains()
async def theming_style_css():
    """Every stylesheet a page needs, as a single import.

    Query parameters:
        theme: Barrel theme name or stylesheet URL, overriding the
               system theme for this page only.
        v:     Ignored, a cache-busting version from the page.
    """
    theme = (
        quart.request.args.get("theme", "").strip()
        or theming.getCSSTheme()
        or config["theme_url"]
    )

    theme_url = resolve_theme_url(theme)
    if not is_safe_css_url(theme_url):
        return quart.Response("Invalid theme", status=400)

    imports = [
        *BASE_STYLESHEETS,
        DYNAMIC_STYLESHEET,
        theme_url,
    ]
    css = "\n".join(f'@import url("{url}");' for url in imports)

    response = await app.make_response(css)
    response.mimetype = "text/css"
    return response
