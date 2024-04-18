import os
import sqlite3
import threading
import time

from scullery.ratelimits import RateLimiter

from kaithem.src import directories

fn = os.path.expanduser("~/.local/kaithem/chandler_state.db")

if "/dev/shm" in directories.vardir:
    fn = os.path.join(directories.vardir, "test_chandler_state.db")

os.makedirs(os.path.dirname(fn), exist_ok=True)

con = sqlite3.connect(fn)
cur = con.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS checkpoint(sceneid, cuename, timestamp)")
con.commit()

connections = threading.local()


def get_con():
    if not hasattr(connections, "con"):
        connections.con = sqlite3.connect(fn)
        connections.con.row_factory = sqlite3.Row

    return connections.con


rl = RateLimiter(hz=1 / 20, burst=300)


def set_checkpoint(sceneid: str, cuename: str):
    if not rl.limit():
        raise RuntimeError("Rate limit exceeded for entering checkpoint scenes")

    c = get_con()
    c.execute("DELETE FROM checkpoint WHERE sceneid=?", (sceneid,))
    c.execute("INSERT INTO checkpoint VALUES (?,?,?)", (sceneid, cuename, time.time()))
    c.commit()


def get_checkpoint(sceneid: str):
    if not rl.limit():
        raise RuntimeError("Rate limit exceeded for entering checkpoint scenes")

    c = get_con()
    c2 = c.cursor()
    for i in c2.execute("SELECT * FROM checkpoint WHERE sceneid=?", (sceneid,)):
        return (i[1], i[2])
