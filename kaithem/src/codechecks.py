import io

import pyflakes.api
import pyflakes.checker
import pyflakes.reporter

# These could do false negatives. But it's kinda the best we can easily do.
pyflakes.checker.Checker.builtIns.add("kaithem")
pyflakes.checker.Checker.builtIns.add("event")
pyflakes.checker.Checker.builtIns.add("page")
pyflakes.checker.Checker.builtIns.add("module")
pyflakes.checker.Checker.builtIns.add("__topic")
pyflakes.checker.Checker.builtIns.add("__value")


def check(str, fn):
    buf = io.StringIO()
    x = pyflakes.reporter.Reporter(buf, buf)

    pyflakes.api.check(str, fn, x)
    return buf.getvalue().strip()
