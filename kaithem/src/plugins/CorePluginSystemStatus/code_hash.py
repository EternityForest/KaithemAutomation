import hashlib
import os
from typing import Any

this_file_dir = os.path.dirname(os.path.realpath(__file__))
src_dir = os.path.dirname(os.path.dirname(os.path.dirname(this_file_dir)))


def hash_dir(dir: str, root_dir: str, hash_obj: Any | None = None):
    if hash_obj is None:
        hash = hashlib.sha256()
    else:
        hash = hash_obj
    listdir = os.listdir(dir)
    for entry in sorted(listdir):
        if "__pycache__" in entry:
            continue
        if entry.startswith("."):
            continue
        fullpath = os.path.join(dir, entry)

        if os.path.islink(fullpath):
            continue
        elif os.path.isdir(fullpath):
            hash.update(entry.encode("utf-8") + b"\n")
            hash_dir(fullpath, root_dir, hash)
        else:
            relpath = os.path.relpath(fullpath, root_dir)
            hash.update(relpath.encode("utf-8") + b"\n")
            with open(fullpath, "rb") as f:
                hash.update(f.read())
    return hash


def get_code_hash() -> str:
    return hash_dir(src_dir, src_dir).hexdigest()


if __name__ == "__main__":
    print(src_dir)
    print(get_code_hash())
