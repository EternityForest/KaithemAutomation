import os

from kaithem.src.directories import vardir
from kaithem.src.wasm_kegs import packages

package_store = packages.PackageStore().ensure_package(
    os.path.join(
        vardir,
        "wasm-kegs",
    )
)
