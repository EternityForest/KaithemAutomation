import sys

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.src import util


def test_private_ip_check():
    assert util.is_private_ip("127.0.0.1")
    assert util.is_private_ip("10.0.0.67")
    assert util.is_private_ip("::1")

    # Todo: shoyld we actually consider mesh
    # networks to be private?
    assert util.is_private_ip("fe80::1")

    assert not util.is_private_ip("100.27.132.170")
    assert not util.is_private_ip("89.207.132.170")
