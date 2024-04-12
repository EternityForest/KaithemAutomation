from kaithem.src import webapproot


def test_make_demo_device():
    assert webapproot.webapproot().about()
    assert webapproot.webapproot().tagpoints()
    assert webapproot.webapproot().modules.index()
