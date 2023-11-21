from kaithem.src.chandler import scenes


def test_make_scene():
    s = scenes.Scene("TestingScene", id='TEST')

    assert 'TEST' in scenes.scenes

    s.go()
    
    assert s.active
    assert s in scenes.activeScenes
    assert s.cue.name == 'default'

    s.addCue('cue2')
    s.goto_cue('cue2')
    assert s.cue.name == 'cue2'
