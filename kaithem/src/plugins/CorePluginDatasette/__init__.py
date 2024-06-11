import getpass
import os
import socket

from datasette.app import Datasette

from kaithem.api import web as webapi
from kaithem.src import directories

dbs = []

logdir = directories.logdir

historyFilemame = socket.gethostname() + "-" + getpass.getuser() + "-taghistory.sqlite"

newHistoryDBFile = os.path.join(logdir, historyFilemame)

if os.path.exists(newHistoryDBFile):
    dbs.append(newHistoryDBFile)

datasette_application = Datasette(
    dbs,
    settings={
        "base_url": "/datasette/",
    },
).app()
webapi.add_asgi_app("/datasette", datasette_application)
