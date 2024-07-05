import datetime
import math

import dateutil
import dateutil.tz


def ease(x: float):
    x = min(1, max(0, x))
    return -(math.cos(math.pi * x) - 1) / 2


def dt_to_ts(dt: datetime.datetime) -> float:
    "Given a datetime, return unix timestamp"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dateutil.tz.tzlocal())

    d2 = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    time_delta = dt - d2
    ts = int(time_delta.total_seconds())
    return ts


# https://gist.github.com/devxpy/063968e0a2ef9b6db0bd6af8079dad2a
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
OCTAVES = list(range(11))
NOTES_IN_OCTAVE = len(NOTES)


def number_to_note(number: int) -> str:
    octave = number // NOTES_IN_OCTAVE
    note = NOTES[number % NOTES_IN_OCTAVE]
    return note + str(octave)
