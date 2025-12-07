import os
import threading
import tomllib
import zipfile

_local = threading.local()


def get_package_store():
    if not hasattr(_local, "store"):
        raise RuntimeError("PackageStore not in use")
    if not _local.store:
        raise RuntimeError("PackageStore not in use")
    return _local.store


def parse_plugin_name(plugin: str) -> tuple[str, str]:
    x = plugin.split(":")

    plugin = x[-1]
    package = ":".join(x[:-1])

    return package, plugin


class PackageStore:
    def __init__(
        self, paths: list[str] = ["~/.local/share/wasm-kegs/packages"]
    ):
        """Path must be the package store directory"""
        for path in paths:
            p = os.path.expanduser(path)
            os.makedirs(p, exist_ok=True)

        self.paths = paths

    def __enter__(self):
        if hasattr(_local, "store") and _local.store:
            raise RuntimeError("PackageStore already in use")
        _local.store = self
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        _local.store = None

    def ensure_package(self, package: str) -> str:
        if os.path.isdir(package):
            return package

        for p in self.paths:
            path = os.path.join(p, package)
            if os.path.exists(path):
                return path

        if package.endswith(".keg"):
            path = os.path.join(
                os.path.dirname(package),
                "cache",
                os.path.basename(package)[:-4],
            )

            if os.path.exists(path):
                print(f"Using cached package {path}")
                return path

            print(f"Extracting {package} to {path}")

            zipfile.ZipFile(package).extractall(path + "~")
            os.rename(path + "~", path)

            return path

        raise RuntimeError(f"Could not find package {package}")

    def find_plugin(self, plugin) -> str:
        package, plugin = parse_plugin_name(plugin)
        packagedir = self.ensure_package(package)

        with open(os.path.join(packagedir, "keg.toml"), "rb") as f:
            manifest = tomllib.load(f)

        pl = manifest["plugins"]
        pm = None
        for i in pl:
            if i["name"] == plugin:
                pm = i
                break

        if pm is None:
            raise RuntimeError(f"Plugin {plugin} not found in keg.toml")

        plugin_path = os.path.join(
            packagedir, pm.get("path", "plugins/" + pm["name"])
        )
        return plugin_path
