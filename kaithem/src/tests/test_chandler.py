from kaithem.src.chandler import scenes
from kaithem.src.sound import test_sound_logs
from kaithem.src.sound import play_logs
import time
import logging


def test_make_scene():
    s = scenes.Scene("TestingScene1", id='TEST')

    assert 'TEST' in scenes.scenes

    s.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == 'default'

    s.add_cue('cue2')
    s.goto_cue('cue2')
    assert s.cue.name == 'cue2'
    s.close()

    assert "TestingScene1" not in scenes.scenes_by_name


def test_play_sound():
    s = scenes.Scene("TestingScene2", id='TEST')

    assert 'TEST' in scenes.scenes

    s.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == 'default'

    s.add_cue('cue2', sound="alert.ogg")
    s.goto_cue('cue2')
    time.sleep(1)

    # Dummy test sounds end right away
    assert play_logs[-1][0] == 'play'
    assert play_logs[-1][1] == 'TEST'
    assert play_logs[-1][2].endswith('alert.ogg')

    s.close()
    assert "TestingScene2" not in scenes.scenes_by_name


def test_trigger_shortcuts():
    s = scenes.Scene(name="TestingScene3", id='TEST')
    s2 = scenes.Scene(name="TestingScene4", id='TEST2')

    s.go()
    s2.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == 'default'

    s.add_cue('cue2', trigger_shortcut="foo")

    s2.add_cue("cue2", shortcut="foo")

    s.goto_cue('cue2')

    # Cue2 in s should trigger the shortcut code foo, which triggers Cue2 in s2
    assert s2.cue.name == 'cue2'
    s.close()
    s2.close()
    assert "TestingScene3" not in scenes.scenes_by_name
    assert "TestingScene4" not in scenes.scenes_by_name

=tv('/system/alerts.level') >= 30 

def test_cue_logic():
    logging.warning(scenes.rootContext.commands.scriptcommands)
    s = scenes.Scene(name="TestingScene5", id='TEST')
    s2 = scenes.Scene(name="TestingScene6", id='TEST2')

    s.go()
    s2.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == 'default'

    s.add_cue('cue2', rules=[
        ["cue.enter", [['goto', 'TestingScene6', 'cue2']]],
        ["cue.enter", [['setAlpha', '=SCENE', '0.76']]]
    ]
    )

    s2.add_cue("cue2")

    s.goto_cue('cue2')
    time.sleep(0.5)
    assert s2.cue.name == 'cue2'
    assert s.alpha == 0.76

    s.close()
    s2.close()
    assert "TestingScene5" not in scenes.scenes_by_name
    assert "TestingScene6" not in scenes.scenes_by_name

def test_():
    logging.warning(scenes.rootContext.commands.scriptcommands)
    s = scenes.Scene(name="TestingScene5", id='TEST')
    s2 = scenes.Scene(name="TestingScene6", id='TEST2')

    s.go()
    s2.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == 'default'

    s.add_cue('cue2', rules=[
        ["cue.enter", [['goto', 'TestingScene6', 'cue2']]],
        ["cue.enter", [['setAlpha', '=SCENE', '0.76']]]
    ]
    )

    s2.add_cue("cue2")

    s.goto_cue('cue2')
    time.sleep(0.5)
    assert s2.cue.name == 'cue2'
    assert s.alpha == 0.76

    s.close()
    s2.close()
    assert "TestingScene5" not in scenes.scenes_by_name
    assert "TestingScene6" not in scenes.scenes_by_name
