# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import time
import traceback
from types import MethodType

from . import messagebus, tagpoints

globalMethodRateLimit = [0.0]


def tagErrorHandler(tag, f, val):
    try:
        from .plugins import CorePluginEventResources

        if f.__module__ in CorePluginEventResources.eventsByModuleName:
            CorePluginEventResources.eventsByModuleName[
                f.__module__
            ].handle_exception()
        else:
            if isinstance(f, MethodType):
                # Better than nothing to have this global limit instead of no posted errors at all.
                if time.monotonic() > globalMethodRateLimit[0] + 60 * 30:
                    globalMethodRateLimit[0] = time.monotonic()
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "First err in tag subscriber "
                        + str(f)
                        + " from "
                        + str(f.__module__)
                        + " to "
                        + tag.name,
                    )

            elif not hasattr(f, "_kaithemFirstErrorMarker"):
                f._kaithemFirstErrorMarker = True
                messagebus.post_message(
                    "/system/notifications/errors",
                    "First err in tag subscriber "
                    + str(f)
                    + " from "
                    + str(f.__module__)
                    + " to "
                    + tag.name,
                )
    except Exception:
        print(traceback.format_exc(chain=True))


tagpoints.subscriber_error_handlers = [tagErrorHandler]
