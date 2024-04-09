# fix https://github.com/python/cpython/issues/91216
# TODO this is a yucky hack but pytest won't load

import importlib.metadata

try:
    import typeguard  # noqa
except Exception:
    v = importlib.metadata.version

    def version(p):
        x = v(p)
        if not x:
            raise importlib.metadata.PackageNotFoundError()
        return p

    importlib.metadata.version = version

import sys

import pytest


class MyPlugin:
    def pytest_sessionfinish(self):
        print("*** test run reporting finishing")


if __name__ == "__main__":
    sys.exit(pytest.main(["-qq"], plugins=[MyPlugin()]))
