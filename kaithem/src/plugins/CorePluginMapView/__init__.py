# SPDX-License-Identifier: GPL-3.0-or-later
import kaithem.api.apps_page

app = kaithem.api.apps_page.App(
    "coreplugins_mapview",
    "Map View",
    "/static/vite/kaithem/src/plugins/CorePluginMapView/index.html",
)
app.icon = "/static/img/16x9/nautical-map.avif"

kaithem.api.apps_page.add_app(app)
