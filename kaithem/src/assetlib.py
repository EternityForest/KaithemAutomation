import json
import os
import threading
import time
from typing import List

import niquests

from . import directories

fetchlock = threading.RLock()

defaultAssetPacks = [
    "https://github.com/0lhi/FreePD",
    "https://github.com/Loppansson/kenney-casino-audio-for-godot",
    "https://github.com/Calinou/kenney-interface-sounds",
    "https://github.com/Calinou/kenney-ui-audio",
    "https://github.com/EternityForest/Free-SFX",
    "https://github.com/EternityForest/Free-Music",
    "https://github.com/Loppansson/kenney-rpg-audio-for-godot",
]


class AssetPacks:
    def __init__(self, assetlib: str, assetPacks=None) -> None:
        self.assetlib: str = os.path.normpath(assetlib)
        self.assetPacks: List[str] = assetPacks or defaultAssetPacks
        self.assetPackFolders = {}

        self.assetPackNames = {}

        for i in self.assetPacks:
            url = i
            i = i.replace("https://", "").replace("github.com/", "")
            i = i.split("/")
            self.assetPackFolders[
                os.path.join(directories.vardir, "assets", i[0] + ":" + i[1])
            ] = i
            self.assetPackNames[url] = i[0] + ":" + i[1]

    def ls(self, f: str) -> List[str]:
        if os.path.normpath(f).startswith(self.assetlib + "/"):
            if not os.path.exists(f):
                os.makedirs(f, exist_ok=True)

        ap = None
        d = f
        for i in range(30):
            if d == "/":
                break
            if d in self.assetPackFolders:
                ap = d
                break
            d = os.path.dirname(d)

        x = [
            (i + "/" if os.path.isdir(os.path.join(f, i)) else i)
            for i in os.listdir(f)
        ]

        if os.path.normpath(f) == self.assetlib:
            for i in self.assetPackFolders.keys():
                n = os.path.basename(i)
                if n + "/" not in x:
                    x.append(n + "/")
        if ap:
            assetlist = fetch_list(
                self.assetPackFolders[ap][0], self.assetPackFolders[ap][1], ap
            )
            t = assetlist["tree"]
            for i in t:
                current = os.path.relpath(f, ap)
                if current == ".":
                    current = ""
                if i["path"].startswith(current) and len(i["path"]) > len(
                    current
                ):
                    if "/" not in i["path"][len(os.path.relpath(f, ap)) + 1 :]:
                        p = os.path.basename(i["path"])
                        if i["type"] == "tree":
                            p = p + "/"
                        if p not in x:
                            x.append(p)

        return x

    def ensure_file(self, f):
        with fetchlock:
            if os.path.exists(f):
                return

            ap = None
            d = f
            for i in range(30):
                if d == "/":
                    break
                if d in self.assetPackFolders:
                    ap = d
                    break
                d = os.path.dirname(d)

            if ap:
                if not os.path.exists(os.path.dirname(f)):
                    os.makedirs(os.path.dirname(f), exist_ok=True)

                current = os.path.relpath(f, ap)
                fetch_file(
                    self.assetPackFolders[ap][0],
                    self.assetPackFolders[ap][1],
                    ap,
                    current,
                )


def fetch_meta(owner, repo, folder, cachetime=30 * 24 * 3600):
    fn = os.path.join(folder, "github_api_repo.json")
    if os.path.exists(fn):
        t = os.stat(fn).st_mtime
        if t > (time.time() - cachetime):
            with open(fn) as f:
                return json.loads(f.read())
    try:
        url = "https://api.github.com/repos/" + owner + "/" + repo

        d = niquests.get(url, timeout=5)
        d.raise_for_status()

        with open(fn, "w") as f:
            f.write(d.text)

    except Exception:
        # Fallback to just using what we have.
        if os.path.exists(fn):
            with open(fn) as f:
                return json.loads(f.read())
        else:
            raise

    return json.loads(d.text)


def fetch_list(owner, repo, folder, cachetime=7 * 24 * 3600):
    fn = os.path.join(folder, "github_api_listing.json")
    if os.path.exists(fn):
        t = os.stat(fn).st_mtime
        if t > (time.time() - cachetime):
            with open(fn) as f:
                return json.loads(f.read())

    try:
        branch = fetch_meta(owner, repo, folder)["default_branch"]

        url = (
            "https://api.github.com/repos/"
            + owner
            + "/"
            + repo
            + "/git/trees/"
            + branch
            + "?recursive=1"
        )

        d = niquests.get(url, timeout=5)
        d.raise_for_status()

        with open(fn, "w") as f:
            f.write(d.text)
    except Exception:
        if os.path.exists(fn):
            with open(fn) as f:
                return json.loads(f.read())
        else:
            raise

    return json.loads(d.text)


def fetch_file(owner, repo, folder, path):
    fn = os.path.join(folder, path)
    if os.path.exists(fn):
        return

    branch = fetch_meta(owner, repo, folder)["default_branch"]
    url = (
        "https://raw.githubusercontent.com/"
        + owner
        + "/"
        + repo
        + "/"
        + branch
        + "/"
        + path
    )

    # Connection cose to try and speed things up as per
    # https://github.com/psf/requests/issues/4023
    d = niquests.get(url, timeout=5, headers={"Connection": "close"})
    d.raise_for_status()

    with open(fn, "wb") as f:
        f.write(d.content)
