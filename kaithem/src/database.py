

# This file manages kaithem's native SQLite document database.

# There is one table called Document

# uuid PRIMARY KEY:  UUID of the document in canonical text form
# name: Renamable name for the document
# type: The type of this document. Type names not starting with app. are reserved
# timestamp: Last time the record was changed
# local_timestamp: When this node's copy of the document changed(For remote sync)
# document: A JSON document
# blob: generic blob storage for embedded files.


# The document must always be a dict, and keys other than app. are reserved.

# Every value must be a 2-element list called a cell, where the first item is data
# and the second item is the cell properties.


# The cell properties field may contain a "type" key which may be "table",
# in which case there will be a "query" item.

# Having a table as a cell means that viewer pages should embed a table
# of documents which is to be created from the given query.
#
# The query will be a genuine SQL statement, using AS to name the columns.

import sqlite3
import time
import json
import uuid
import random

class DocumentDatabase():
    def __init__(self, filename):
        self.conn = sqlite3.connect(filename)

        self.conn.execute('''CREATE TABLE IF NOT EXISTS document
             (uuid text PRIMARY KEY,parent text, type text, name text, timestamp integer, local_timestamp integer, document text, data blob)''')
        self.conn.execute('''CREATE INDEX document_parent ON document(parent)''')

        for i in range(1000000):
            self.insertDocument(str(uuid.uuid4()), "log", "hum", {"humidity":random.random()},str(uuid.uuid4()))
        self.conn.commit()

    def insertDocument(self, uuid, type, name, document,parent=''):
        ts = int(time.time()*10**6)
        self.conn.execute("INSERT INTO document VALUES (?,?,?,?,?,?,?,?)",
                          (uuid, parent, type, name, ts, ts, json.dumps(document), b''))


d = DocumentDatabase("test.db")

