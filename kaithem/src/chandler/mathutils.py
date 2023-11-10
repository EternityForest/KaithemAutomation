
import datetime
import time
import pytz
import math


def ease(x: float):
    x = min(1, max(0, x))
    return -(math.cos(math.pi * x) - 1) / 2


def dt_to_ts(dt, tz=None):
    "Given a datetime in tz, return unix timestamp"
    if tz:
        utc = pytz.timezone("UTC")
        return (
            tz.localize(dt.replace(tzinfo=None))
            - datetime.datetime(1970, 1, 1, tzinfo=utc)
        ) / datetime.timedelta(seconds=1)

    else:
        # Local Time
        ts = time.time()
        offset = (
            datetime.datetime.fromtimestamp(
                ts) - datetime.datetime.utcfromtimestamp(ts)
        ).total_seconds()
        return (
            (dt - datetime.datetime(1970, 1, 1)) / datetime.timedelta(seconds=1)
        ) - offset


# https://gist.github.com/devxpy/063968e0a2ef9b6db0bd6af8079dad2a
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
OCTAVES = list(range(11))
NOTES_IN_OCTAVE = len(NOTES)


def number_to_note(number: int) -> str:
    octave = number // NOTES_IN_OCTAVE
    note = NOTES[number % NOTES_IN_OCTAVE]
    return note + str(octave)

