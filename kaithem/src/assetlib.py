import os
import getpass
import requests
import time
import threading
import json
from . import directories
from urllib.parse import quote



class AssetPacks():

    def __init__(self, assetlib) -> None:
        self.assetlib = os.path.normpath(assetlib)
        self.assetPacks = ["https://github.com/0lhi/FreePD"]
        self.assetPackFolders = {}

        self.assetPackNames = {}

        for i in self.assetPacks:
            url = i
            i = i.replace('https://', '').replace('github.com/', '')
            i = i.split("/")
            self.assetPackFolders[os.path.join(
                directories.vardir, 'assets', i[0] + ':' + i[1])] = i
            self.assetPackNames[url] = i[0] + ':' + i[1]




    def ls(self, f):
        if os.path.normpath(f).startswith(self.assetlib + "/"):
            if not os.path.exists(f):
                os.makedirs(f, exist_ok=True)

        ap = None
        d = f
        for i in range(30):
            if (d == '/'):
                break
            if d in self.assetPackFolders:
                ap = d
                break
            d = os.path.dirname(d)

        x = os.listdir(f)

        if ap:
            l = fetch_list(self.assetPackFolders[ap]
                           [0], self.assetPackFolders[ap][1], ap)
            t = l['tree']
            for i in t:

                current = os.path.relpath(f, ap)
                if current == '.':
                    current = ''
                if i['path'].startswith(current):
                    if not '/' in i['path'][len(os.path.relpath(f, ap)):]:
                        p = os.path.basename(i['path'])
                        if i['type'] == 'tree':
                            p = p + "/"
                        x.append(p)

        return x

    def ensure_file(self, f):
        if os.path.exists(f):
            return

        ap = None
        d = f
        for i in range(30):
            if (d == '/'):
                break
            if d in self.assetPackFolders:
                ap = d
                break
            d = os.path.dirname(d)

        if ap:
            if not os.path.exists(os.path.dirname(f)):
                os.makedirs(os.path.dirname(f), exist_ok=True)

            current = os.path.relpath(f, ap)
            fetch_file(self.assetPackFolders[ap][0],
                       self.assetPackFolders[ap][1], ap, current)


def fetch_meta(owner, repo, folder, cachetime=30 * 24 * 3600):
    fn = os.path.join(folder, "github_api_repo.json")
    if os.path.exists(fn):
        t = os.stat(fn).st_mtime
        if t > (time.time() - cachetime):
            with open(fn) as f:
                return json.loads(f.read())

    url = "https://api.github.com/repos/" + owner + "/" + repo

    d = requests.get(url)
    d.raise_for_status()

    with open(fn, 'w') as f:
        f.write(d.text)

    return json.loads(d.text)


def fetch_list(owner, repo, folder, cachetime=30 * 24 * 3600):
    fn = os.path.join(folder, "github_api_listing.json")
    if os.path.exists(fn):
        t = os.stat(fn).st_mtime
        if t > (time.time() - cachetime):
            with open(fn) as f:
                return json.loads(f.read())

    branch = fetch_meta(owner, repo, folder)['default_branch']

    url = "https://api.github.com/repos/" + owner + "/" + \
        repo + "/git/trees/" + branch + "?recursive=1"

    d = requests.get(url)
    d.raise_for_status()

    with open(fn, 'w') as f:
        f.write(d.text)

    return json.loads(d.text)


def fetch_file(owner, repo, folder, path):
    fn = os.path.join(folder, path)
    if os.path.exists(fn):
        return

    branch = fetch_meta(owner, repo, folder)['default_branch']
    url = "https://raw.githubusercontent.com/" + \
        owner + "/" + repo + "/" + branch + "/" + path

    d = requests.get(url)
    d.raise_for_status()

    with open(fn, 'wb') as f:
        f.write(d.content)


