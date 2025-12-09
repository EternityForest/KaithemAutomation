import os

from kaithem.src.directories import vardir
from wasm_kegs import packages

package_store = packages.PackageStore(
    [
        os.path.join(
            vardir,
            "wasm-kegs",
        ),
        os.path.join(os.path.dirname(__file__), "builtin_kegs"),
    ]
)
