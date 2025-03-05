import os
import shutil
import sqlite3
import threading
import time

import structlog
from scullery.ratelimits import RateLimiter

from kaithem.src import directories

logger = structlog.get_logger(__name__)


fn = os.path.expanduser("~/.local/kaithem/chandler_state.db")

if "/dev/shm" in directories.vardir:
    fn = os.path.join(directories.vardir, "test_chandler_state.db")


def init_db():
    os.makedirs(os.path.dirname(fn), exist_ok=True)

    con = sqlite3.connect(fn)
    cur = con.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS checkpoint(groupid, cuename, timestamp)"
    )
    con.commit()

    # Self test line to be sure it works
    con.execute("SELECT * FROM checkpoint LIMIT 1")


try:
    init_db()
except sqlite3.OperationalError:
    logger.exception("Chandler state DB likely corrupt, starting over")
    shutil.move(fn, fn + ".corrupt")
    try:
        init_db()
    except Exception:
        logger.exception("Could not remake chandler state DB")


connections = threading.local()

# Only try remaking file once per boot
try_remake_limit = 0


def get_con():
    global try_remake_limit

    if not hasattr(connections, "con"):
        connections.con = sqlite3.connect(fn)
        connections.con.row_factory = sqlite3.Row

    try:
        connections.con.execute("SELECT * FROM checkpoint LIMIT 1")
    except sqlite3.OperationalError:
        if try_remake_limit == 0:
            try_remake_limit = 1
            logger.error(
                "Chandler state file is corrupt, starting over", exc_info=True
            )
            shutil.move(fn, fn + ".corrupt")
            init_db()
            return get_con()
        else:
            raise
    return connections.con


rl = RateLimiter(hz=1 / 20, burst=300)


def del_checkpoint(groupid: str):
    c = get_con()
    c.execute("DELETE FROM checkpoint WHERE groupid=?", (groupid,))
    c.commit()


def set_checkpoint(groupid: str, cuename: str):
    if not rl.limit():
        raise RuntimeError("Rate limit exceeded for entering checkpoint groups")

    c = get_con()
    c.execute("DELETE FROM checkpoint WHERE groupid=?", (groupid,))
    c.execute(
        "INSERT INTO checkpoint VALUES (?,?,?)", (groupid, cuename, time.time())
    )
    c.commit()


def get_checkpoint(groupid: str):
    if not rl.limit():
        raise RuntimeError("Rate limit exceeded for entering checkpoint groups")

    c = get_con()
    c2 = c.cursor()
    for i in c2.execute("SELECT * FROM checkpoint WHERE groupid=?", (groupid,)):
        return (i[1], i[2])
