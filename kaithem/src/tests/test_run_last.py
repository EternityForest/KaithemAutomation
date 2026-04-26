import datetime
import time

import stamina

from kaithem.src import systasks

from .test_chandler import TempGroup

# This messess everything up with the
# cue scheduling and time_machine
systasks.enable_time_jump_detect = False


# Time travel breaks anything that runs after
def test_schedule_at():
    import time_machine

    with TempGroup() as grp:
        grp.add_cue("cue2")
        start = datetime.datetime.now().astimezone()
        with time_machine.travel(start, tick=True) as traveller:
            in_5_minutes = start + datetime.timedelta(minutes=5)
            grp.cues[
                "cue2"
            ].schedule_at = f"@{in_5_minutes.strftime('%I:%M%p')}"
            time.sleep(0.5)

            assert grp.cue.name == "default"
            traveller.shift(datetime.timedelta(minutes=2))
            time.sleep(0.5)

            assert grp.cue.name == "default"

            traveller.shift(datetime.timedelta(minutes=6))
            time.sleep(0.5)
            for attempt in stamina.retry_context(
                on=AssertionError, attempts=10
            ):
                with attempt:
                    assert grp.cue.name == "cue2"


def test_schedule_at_cancel():
    import time_machine

    with TempGroup() as grp:
        grp.add_cue("cue2")
        start = datetime.datetime.now().astimezone()
        with time_machine.travel(start, tick=True) as traveller:
            in_5_minutes = start + datetime.timedelta(minutes=5)
            grp.cues[
                "cue2"
            ].schedule_at = f"@{in_5_minutes.strftime('%I:%M%p')}"
            time.sleep(0.5)

            assert grp.cue.name == "default"
            traveller.shift(datetime.timedelta(minutes=2))
            time.sleep(0.5)

            assert grp.cue.name == "default"
            grp.cues["cue2"].schedule_at = ""
            traveller.shift(datetime.timedelta(minutes=6))
            time.sleep(2)
            assert grp.cue.name == "default"


def test_schedule_at_disabled():
    import time_machine

    with TempGroup() as grp:
        grp.add_cue("cue2")
        grp.enable_timing = False
        start = datetime.datetime.now().astimezone()
        with time_machine.travel(start, tick=True) as traveller:
            in_5_minutes = start + datetime.timedelta(minutes=5)
            grp.cues[
                "cue2"
            ].schedule_at = f"@{in_5_minutes.strftime('%I:%M%p')}"
            time.sleep(0.5)
            assert grp.cue.name == "default"
            traveller.shift(datetime.timedelta(minutes=2))
            time.sleep(0.5)
            assert grp.cue.name == "default"
            traveller.shift(datetime.timedelta(minutes=6))
            time.sleep(3)
            assert grp.cue.name == "default"


def test_script_timer_triggers():
    import time_machine

    with TempGroup() as grp:
        grp.add_cue("cue2")
        start = datetime.datetime.now().astimezone()
        with time_machine.travel(start, tick=True) as traveller:
            in_5_minutes = start + datetime.timedelta(minutes=5)
            grp.cue.rules = [
                [
                    f"@{in_5_minutes.strftime('%I:%M%p')}",
                    [["goto", grp.name, "cue2"]],
                ]
            ]
            traveller.shift(datetime.timedelta(minutes=6))
            time.sleep(3)
            assert grp.cue.name == "cue2"
