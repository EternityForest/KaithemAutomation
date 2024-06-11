import getpass
import os
import socket

from datasette import hookimpl
from datasette.app import Datasette

from kaithem.api import web as webapi
from kaithem.src import directories

dbs = []

logdir = directories.logdir

historyFilemame = socket.gethostname() + "-" + getpass.getuser() + "-taghistory.sqlite"

newHistoryDBFile = os.path.join(logdir, historyFilemame)

if os.path.exists(newHistoryDBFile):
    dbs.append(newHistoryDBFile)


db_objects = {}


class ConfiguredDB:
    def __init__(self, resource):
        self.read_perms = resource["read_perms"]
        self.write_perms = resource["write_perms"]


@hookimpl
def actor_from_request(datasette, request):
    async def inner():
        try:
            return {"id": webapi.user(request.scope)}
        except Exception:
            return None

    return inner


@hookimpl
def permission_allowed(datasette, actor, action, resource):
    async def inner():
        read = {
            "view-database",
            "view-instance",
            "view-table",
            "view-query",
        }
        write = {
            "insert-row",
            "delete-row",
            "update-row",
        }

    return inner


datasette_application = Datasette(
    dbs,
    settings={
        "base_url": "/datasette/",
    },
).app()
webapi.add_asgi_app("/datasette", datasette_application)
