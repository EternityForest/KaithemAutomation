# fix https://github.com/python/cpython/issues/91216
# TODO this is a yucky hack but pytest won't load
import importlib.metadata
import sys

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


import pytest


class MyPlugin:
    def pytest_sessionfinish(self):
        print("*** test run reporting finishing")


@pytest.fixture(scope="function", autouse=True)
def exit_pytest_first_failure():
    if pytest.TestReport.outcome == "failed":
        pytest.exit("Exiting pytest")


if __name__ == "__main__":
    if not sys.gettrace():
        sys.exit(
            pytest.main(["-qq", "-x", "--cov=kaithem"], plugins=[MyPlugin()])
        )
    else:
        sys.exit(pytest.main(["-qq", "-x"], plugins=[MyPlugin()]))
