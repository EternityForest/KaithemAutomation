import datetime
import time

from .test_chandler import TempGroup


# Time travel breaks anything that runs after
def test_schedule_at():
    import dateutil.tz
    import time_machine

    with TempGroup() as grp:
        grp.add_cue("cue2")
        start = datetime.datetime.now(dateutil.tz.tzlocal())
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
            assert grp.cue.name == "cue2"


def test_schedule_at_disabled():
    import dateutil.tz
    import time_machine

    with TempGroup() as grp:
        grp.add_cue("cue2")
        grp.enable_timing = False
        start = datetime.datetime.now(dateutil.tz.tzlocal())
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
    import dateutil.tz
    import time_machine

    with TempGroup() as grp:
        grp.add_cue("cue2")
        start = datetime.datetime.now(dateutil.tz.tzlocal())
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
