import os
import sqlite3
import threading
import time

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


class RateLimiter:
    def __init__(self, rate: float, accum_limit=250) -> None:
        self.rate = rate
        self.accum_limit = accum_limit
        self.current_limit = accum_limit
        self.timestamp = time.monotonic()

    def limit(self):
        """If it hasn't been called too often, reeturn
        number of credits remaining.  Othewise return 0.
        Credits refill at "rate" per second up to a max of accum_limit
        """
        elapsed = time.monotonic() - self.timestamp
        self.current_limit = self.rate + elapsed
        self.current_limit = min(self.current_limit, self.accum_limit)
        if self.current_limit >= 1:
            self.current_limit -= 1
            return self.current_limit

        return 0


rl = RateLimiter(1 / 20)


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
