import gc
import random
import sys
import time
import uuid

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.src import modules, modules_state
    from kaithem.src.chandler import (
        core,
        groups,
    )

    if "test_chandler_module" not in modules_state.ActiveModules:
        modules.newModule("test_chandler_module")
        modules.createResource(
            "test_chandler_module",
            "test_board",
            {"resource": {"type": "chandler_board"}},
        )
    board = core.boards["test_chandler_module:test_board"]


class TempGroup:
    """Gives a running group and then cleans it up.
    Asserts a whole bunch of stuff every time.
    """

    def __init__(self, name: str | None = None):
        self.name = name or ("test_group_" + str(uuid.uuid4()).replace("-", ""))

    def __enter__(self):
        self.group = groups.Group(board, self.name)
        assert self.group.name == self.name
        board.addGroup(self.group)
        self.group.go()
        core.wait_frame()
        core.wait_frame()
        assert self.group.active
        assert self.group.alpha == 1
        assert self.group.cue.name == "default"
        assert self.name in board.groups_by_name
        assert self.group in board.active_groups
        assert self.group.id in board.groups
        assert self.group.id in groups.groups
        return self.group

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.group.close()
        core.wait_frame()
        core.wait_frame()
        board.rmGroup(self.group)
        core.wait_frame()
        core.wait_frame()
        assert self.name not in board.groups_by_name
        assert self.group not in board.active_groups
        assert self.group.id not in board.groups
        assert self.group.id not in groups.groups

        del self.group
        gc.collect()
        core.wait_frame()


def test_cue_logic_relays():
    with TempGroup() as s:
        with TempGroup() as s2:
            # Each scene makes the other re-enter the default
            s.cue.rules = []

            s2.cue.rules = [
                ["cue.enter", [["goto", s.name, "default"]]],
            ]

            for i in range(10):
                s.goto_cue("default")
                s2.goto_cue("default")

            # Make sure stuff is still happening
            x = s.entered_cue
            s2.goto_cue("default")
            core.wait_frame()
            core.wait_frame()
            assert s.entered_cue != x

            # Make sure no queued up crap happens
            s2.stop()
            core.wait_frame()
            core.wait_frame()
            x = s.entered_cue
            core.wait_frame()
            core.wait_frame()
            assert s.entered_cue == x


def test_cue_logic_oscillate_changes():
    """Do lots of random stuff while cue logic is changing stuff"""
    from kaithem.src.chandler import global_actions

    with TempGroup() as s:
        with TempGroup() as s2:
            with TempGroup() as s3:
                # S3 is just to have random stuff going in the background
                s3.cue.length = 0.1
                s3.cue.next_cue = "default"
                s3.cue.shortcut = "test_sc3"
                s3.goto_cue("default")

                s.cue.rules = []
                s.cue.shortcut = "test_sc"

                s2.cue.rules = [
                    ["cue.enter", [["goto", s.name, "default"]]],
                ]

                for i in range(5):
                    s.cue.rules = []

                    s2.cue.rules = [
                        ["cue.enter", [["goto", s.name, "default"]]],
                    ]
                    s2.cue.shortcut = "test_sc2"
                    s.setAlpha(random.random())
                    global_actions.cl_trigger_shortcut_code("test_sc3")
                    s.goto_cue("default")

                # Make sure stuff is still happening
                core.wait_frame()
                core.wait_frame()
                x = s.entered_cue
                s2.goto_cue("default")
                core.wait_frame()
                core.wait_frame()
                if s.entered_cue == x:
                    time.sleep(1)
                assert s.entered_cue != x

                global_actions.cl_trigger_shortcut_code("test_sc")
                global_actions.cl_trigger_shortcut_code("test_sc2")

                # Make sure stuff is still happening
                x = s.entered_cue
                s2.goto_cue("default")
                core.wait_frame()
                core.wait_frame()
                if s.entered_cue == x:
                    time.sleep(1)
                assert s.entered_cue != x

                # Make sure no queued up crap happens
                s2.stop()
                core.wait_frame()
                core.wait_frame()
                x = s.entered_cue
                core.wait_frame()
                core.wait_frame()
                assert s.entered_cue == x
