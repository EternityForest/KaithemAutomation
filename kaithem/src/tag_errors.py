from . import tagpoints, messagebus
from types import MethodType
globalMethodRateLimit = [0]

def tagErrorHandler(tag, f, val):
    try:
        from . import newevt

        if f.__module__ in newevt.eventsByModuleName:
            newevt.eventsByModuleName[f.__module__]._handle_exception()
        else:
            if isinstance(f, MethodType):
                # Better than nothing to have this global limit instead of no posted errors at all.
                if time.monotonic() > globalMethodRateLimit[0] + 60 * 30:
                    globalMethodRateLimit[0] = time.monotonic()
                    messagebus.postMessage(
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
                messagebus.postMessage(
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


tagpoints.subscriberErrorHandlers = [tagErrorHandler]
