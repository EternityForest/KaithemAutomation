import os
import sys

if "--collect-only" not in sys.argv:
    import kaithem.src.pylogginghandler
    from kaithem.src import directories


def test_log_flush():
    kaithem.src.pylogginghandler.syslogger.flush()

    ls = os.listdir(os.path.join(directories.logdir, "dumps"))
    ls = [i for i in ls if i.endswith(".log")]

    assert len(ls)

    with open(os.path.join(directories.logdir, "dumps", ls[0])) as f:
        d = f.read()

    # Make sure stuff is actually in the file
    assert "[info" in d
