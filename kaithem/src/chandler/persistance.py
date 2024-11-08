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

cur.execute(
    "CREATE TABLE IF NOT EXISTS checkpoint(groupid, cuename, timestamp)"
)
con.commit()


def get_table_schema(table_name, conn):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()

    schema = []
    for column in columns:
        column_name = column[1]
        data_type = column[2]
        nullable = "NOT NULL" if column[4] == 0 else "NULL"
        schema.append(f"{column_name} {data_type} {nullable}")

    return ", ".join(schema)


if "sceneid" in get_table_schema("checkpoint", con):
    renamer = [
        """
    CREATE TABLE checkpoint_new AS
    SELECT sceneid AS groupid, cuename, timestamp
    FROM checkpoint;
               """,
        "DROP TABLE checkpoint;",
        "ALTER TABLE checkpoint_new RENAME TO checkpoint;",
    ]
    for i in renamer:
        con.execute(i)
    con.commit()

connections = threading.local()


def get_con():
    if not hasattr(connections, "con"):
        connections.con = sqlite3.connect(fn)
        connections.con.row_factory = sqlite3.Row

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
