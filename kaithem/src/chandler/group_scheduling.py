from __future__ import annotations

import datetime
import time
import traceback
from typing import TYPE_CHECKING

import structlog

from .. import util
from .mathutils import dt_to_ts

if TYPE_CHECKING:
    from . import groups
    from .cue import Cue

logger = structlog.get_logger()

# TODO Must be called under slow_group_lock_context,
# Add formal restriction


def get_schedule_jump_point(group: groups.Group) -> None | tuple[str, float]:
    """

    Get a cue name and a timestamp to jump to, representing the most recent
    time-based cue change that would have happened in the past if we were
    active to run it.

    Returns:
        None or cuename, entered_time
    """

    # Avoid confusing stuff even though we technically could implement it.
    if group.default_next.strip():
        raise RuntimeError(
            "Group's default next is not empty, __schedule__ doesn't work here."
        )

    def processlen(raw_length) -> str:
        # Return length but always a string and empty if it was 0
        try:
            raw_length = float(raw_length)
            if raw_length:
                return str(raw_length)
            else:
                return ""
        except Exception:
            return str(raw_length)

    consider: list[Cue] = []

    found: dict[str, bool] = {}

    # Start at the current cue, this looop just gets a set of cues to
    # consider
    pointer = group.cue
    idx = group.pointer_for_cue(pointer)

    for safety_counter in range(1000):
        # The logical next cue, except that __fast_forward also points to the next in sequence
        nextname = ""

        if pointer.next_cue and not pointer.next_cue == "__schedule__":
            nextname = pointer.next_cue
            if nextname not in group.cues:
                if not nextname.startswith("__"):
                    raise RuntimeError(
                        f"Reference to nonexistent cue {nextname} in group {group.name}"
                    )
            c = group.cues[nextname]
            idx = group.pointer_for_cue(c)

        else:
            if idx < (len(group.cues_ordered) - 1):
                nextname = group.cues_ordered[idx + 1].name
                idx += 1

        if pointer is not group.cue:
            if str(pointer.next_cue).startswith("__"):
                raise RuntimeError(
                    "Found special __ cue, fast forward not possible"
                )

            if str(pointer.length).startswith("="):
                raise RuntimeError(
                    "Found special =expression length cue, fast forward not possible"
                )

        if processlen(pointer.length) or pointer is group.cue:
            consider.append(pointer)
            found[pointer.name] = True
        else:
            break

        if (nextname not in group.cues) or (nextname in found):
            break

        pointer = group.cues[nextname]

    times: dict[str, float] = {}

    last = None

    scheduled_count = 0

    # Follow chain of next cues to get a set to consider
    for cue in consider:
        if processlen(cue.length).startswith("@"):
            scheduled_count += 1
            ref = datetime.datetime.now()
            selector = util.get_rrule_selector(processlen(cue.length)[1:], ref)
            a: datetime.datetime = selector.before(ref)

            # Hasn't happened yet, can't fast forward past it
            if not a:
                break

            if not a.tzinfo:
                a = a.astimezone()

            a2 = dt_to_ts(a)

            # We found the end time of the cue.
            # If that turns out to be the most recent,
            # We go to the one after that if it has a next,
            # Else just go to
            idx = group.pointer_for_cue(cue)
            if idx < (len(group.cues_ordered) - 1):
                next_in_sequence = group.cues_ordered[idx + 1]
                times[next_in_sequence.name] = a2
            elif cue.next_cue in group.cues:
                times[cue.next_cue] = a2
            else:
                times[cue.name] = a2

            last = a2

        else:
            if last:
                times[cue.name] = last + float(cue.length)

    # Now we do the directly scheduled cues.
    # This won't perfectly reflect what would have happened if it were always running.
    # If you have tons of both scheduled start and end cues mixed with external triggered stuff,
    # But if things are complex enough it gets it wrong, you have way too much going on anyway.

    for i in group.cues:
        cue = group.cues[i]

        if len(cue.schedule_at) > 1:
            try:
                ref = datetime.datetime.now()
                selector = util.get_rrule_selector(cue.schedule_at[1:], ref)
                a: datetime.datetime = selector.before(ref)
                if a:
                    if not a.tzinfo:
                        a = a.astimezone()

                    a2 = dt_to_ts(a)
                    scheduled_count += 1
                    times[cue.name] = a2

            except Exception:
                logger.error(traceback.format_exc())
                continue
    # Can't fast forward without a scheduled cue
    if scheduled_count:
        most_recent: tuple[float, str | None] = (0.0, None)

        # Find the scheduled one that occurred most recently
        for entry in times:
            if times[entry] > most_recent[0]:
                if times[entry] < time.time():
                    most_recent = times[entry], entry
        if most_recent[1]:
            return (most_recent[1], most_recent[0])
