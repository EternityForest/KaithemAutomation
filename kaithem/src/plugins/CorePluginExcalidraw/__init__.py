# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import os
import quart
from kaithem.src import quart_app
t = os.path.join(os.path.dirname(__file__), "dist")

@quart_app.app.route("/plugin-excalidraw/dist/<path:path>")
async def excalidraw_dist(path: str = ""):
    path = path

    return await quart.send_file(os.path.join(t, path))
