import structlog
from scullery import scheduling

from kaithem.src import alerts, geolocation, messagebus, tagpoints
from kaithem.src import astrallibwrapper as sky

refs = []

log = structlog.get_logger("system")


def is_dark():
    lat, lon = geolocation.getCoords()

    if lat is None or lon is None:
        raise RuntimeError(
            "No server location set, fix this in system settings"
        )

    return sky.is_dark(lat, lon)


def is_night():
    lat, lon = geolocation.getCoords()

    if lat is None or lon is None:
        raise RuntimeError(
            "No server location set, fix this in system settings"
        )
    return sky.is_night(lat, lon)


def create():
    def civil_twilight():
        try:
            if is_dark():
                return 1
            else:
                return 0
        except Exception:
            return -1

    twilightTag = tagpoints.Tag("/sky/civil_twilight")
    twilightTag.min = -1
    twilightTag.max = 1
    twilightTag.interval = 60
    twilightTag.description = (
        "Unless overridden, 1 if dark, else 0, -1 if no location is set"
    )
    twilightTag.expose("view_status")
    refs.append(twilightTag)

    alertTag = tagpoints.Tag("/system/alerts.level")
    alertTag.description = "The level of the highest priority alert that is currently not acknowledged"
    alertTag.writable = False
    alertTag.min = 0
    alertTag.max = alerts.priorities["critical"]
    alertTag.expose("view_status")
    refs.append(alertTag)

    def atm(t, v):
        alertTag.value = alerts.priorities[v]

    refs.append(atm)

    messagebus.subscribe("/system/alerts/level", atm)
    alertTag.value = alerts.priorities[
        alerts.highest_unacknowledged_alert_level()
    ]

    def night():
        try:
            if is_night():
                return 1
            else:
                return 0
        except Exception:
            return -1

    nTag = tagpoints.Tag("/sky/night")
    nTag.min = -1
    nTag.max = 1
    nTag.interval = 60
    nTag.description = (
        "Unless overridden, 1 if night, else 0, -1 if no location is set"
    )
    nTag.expose("view_status")

    refs.append(night)
    refs.append(nTag)

    @scheduling.scheduler.every_minute
    def f():
        twilightTag.value = civil_twilight()
        nTag.value = night()

    f()

    refs.append(f)


create()
# Probably best not to automatically do anything that could cause IP traffic?
# ipTag.set_alarm("NoInternetAccess", condition="not value")
