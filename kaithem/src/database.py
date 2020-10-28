

# This file manages kaithem's native SQLite document database.

# There is one table called Document

# uuid PRIMARY KEY:  UUID of the document in canonical text form
# name: Renamable name for the document
# type: The type of this document. Type names not starting with app. are reserved
# parent: The UUID of the parent document, used for links and properties. Can be empty.
# link: The UUID of another document, used for graph links. Can be empty.
# timestamp: Last time the record was changed
# local_timestamp: When this node's copy of the document changed(For remote sync)
# document: A JSON document. Keys starting with "." are reserved. Always an object.
# blob: generic blob storage for embedded files.
# signature: Either empty, or reserved for digitally signing the message.


# The document must always be a dict, and keys other than app. are reserved.

# Every value must be a 2-element list called a cell, where the first item is data
# and the second item is the cell properties.


# The cell properties field may contain a "type" key which may be "table",
# in which case there will be a "query" item.

# Having a table as a cell means that viewer pages should embed a table
# of documents which is to be created from the given query.
#
# The query will be a genuine SQL statement, using AS to name the columns.


# Any type beginning with . is reserved.

# .template types have names that match the types of other records. The other records inherit all unset properties.
# .prop types have a parent that matches a UUID of another record. They override any keys that are set in their document.
# Only one .prop may exist per name for any given record, adding a new with the saem name deletes the old.

# Note that you can't update just one key of a document without replacing it totally, prop overrides
# are used to let you set different props of the same node from different servers without conflict.

# .link types are used to link documents, the name is the type of relation, but they are otherwise normal documents.
# .elink is the same, but they are exclusive, adding one deletes the old one of the same name.

# .log types are used to associate a log entry with a specific node. They have no special meaning, but they an be truly deleted instead of set to NULL
# after a certain time without manual intervention
# and as such there is no guarantee they stay deleted, but they usually will.

import sqlite3
import time
import json
import uuid as uuidModule
import random
import configparser
import os
import libnacl
import base64
import struct

from scullery import messagebus

# class DocumentView():
#     def __init__(self,database,uuid):
#         self.database = database
#         self.uuid = uuid

#     def __getitem__(self,key):

#         #Look for a prop record first, then look for an actual key in that document's table
#         cur = self.database.conn.cursor()
#         cur.execute("SELECT document FROM document WHERE parent=? AND type=? AND name=?", (self.uuid,".prop",key))
#         x= curr.fetchone()
#         if x:
#             return x[0]


#         cur = self.database.conn.cursor()
#         cur.execute("SELECT (document,type) FROM document WHERE uuid=?", (self.uuid,))
#         x= curr.fetchone()
#         if x:
#             if key in x[0]:
#                 return x[0][key]

class DocumentDatabase():
    def __init__(self, filename, publicKey=None):

        self.mbname = "/drayerDB/db/"+os.path.abspath(filename)

        self.conn = sqlite3.connect(filename)
        self.config = configparser.ConfigParser()

        if os.path.exists(filename+".conf"):
            self.config.read(filename+".conf")

        self.conn.row_factory = sqlite3.Row
        #self.conn.execute("PRAGMA wal_checkpoint=FULL")
        self.conn.execute("PRAGMA schema.secure_delete = off")

        self.conn.execute('''CREATE TABLE IF NOT EXISTS document
             (_uuid text PRIMARY KEY,_time integer, _arrival integer, _parent text, _link text, _type text, _name text, 
              document text, data blob, signature blob)''')

        self.conn.execute('''CREATE TABLE IF NOT EXISTS meta
             (key text, value  text)''')

        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_parent ON document(_parent) WHERE _parent IS NOT "" ''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_link ON document(_link) WHERE _link IS NOT "" ''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_name ON document(_name)''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_timestamp ON document(_uuid)''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_type ON document(_type)''')

        self.keys = configparser.ConfigParser()
        secretKey=None

        if os.path.exists(filename+".keys"):
            self.keys.read(filename+".keys")

        if publicKey:
            if self.keys.get('key', 'public', fallback=None):
                pk = base64.b64decode(self.keys.get('key', 'public'))
                if not pk == publicKey:
                    raise ValueError("Supplied key does not match keyfile")
            else:
                self.keys.set('key', 'public',
                              base64.b64encode(publicKey).decode())
        else:
            publicKey = self.keys.get('key', 'public', fallback=None)
            if not publicKey:
                publicKey = self.getMeta("publicKey")
            if not publicKey:
                publicKey, secretKey = libnacl.crypto_keypair()

        if not self.keys.get('key', 'public', fallback=None):
            try:
                self.keys.addSection('key')
            except:
                pass
            self.keys.set('key', 'public',
                          base64.b64encode(publicKey).decode())
            self.saveConfig()

        if secretKey and not self.keys.get('key', 'private', fallback=None):
            try:
                self.keys.addSection('key')
            except:
                pass
            self.keys.set('key', 'private',
                          base64.b64encode(secretKey).decode())
            self.saveConfig()

        if not self.getMeta('publicKey'):
            self.setMeta("publicKey", base64.b64encode(pk).decode())

        
        self.publicKey = publicKey
        self.secretKey = secretKey

    def getMeta(self, key):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT value FROM meta WHERE key=?", (key,))
        x = cur.fetchone()
        if x:
            return x[0]

    def setMeta(self, key, value):
        self.conn.execute(
            "INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))

    def setConfig(self, section, key, value):
        try:
            self.config.addSection(section)
        except:
            pass
        self.config.set(section, key, value)

    def saveConfig(self):
        with open(self.filename+".conf", 'w') as configfile:
            self.config.write(configfile)
        with open(self.filename+".keys", 'w') as configfile:
            self.keys.write(configfile)


    def updateDocument(self, uuid, type, name, document, parent, link, ts_int, blob, localts_int):
        self.conn.execute("UPDATE document  SET _parent=?, _link=?, _type=?, _name=?, _time=?, _arrival=?, document=?, data=?, signature=? WHERE _uuid=?",
                          (parent, link, type, name, ts_int, localts_int, json.dumps(document), blob, b'', uuid))

    def __enter__(self):
        self.conn.__enter__
        return self

    def __exit__(self, *a):
        self.conn.__exit__

    def recordToSigningBytes(self, type, name, document, parent='', link='', uuid=None, timestamp=None, arrival=None, blob=b''):
        # Hash everything, put it together, then sign it.
        return (libnacl.crypto_generichash(uuid)+libnacl.crypto_generichash(type)+libnacl.crypto_generichash(name) +
                struct.pack("<Q", timestamp)+struct.pack("<Q", arrival) + libnacl.crypto_generichash(document)+libnacl.crypto_generichash(blob))

    def deleteDocument(self, uuid):
        ts = int((time.time())*10**6)

        # Clear everything, but keep the parent field, we can use that to let us fully GC it when the parent is deleted.
        self.conn.execute("UPDATE document  SET link=?, type=?, name=?,timestamp=?, local_timestamp=?, document=?, data=?, signature=? WHERE uuid=?",
                          ("", ".null", "", ts, ts, "{}", b'', b'', uuid))
        self.conn.execute("DELETE FROM document WHERE parent=?", (uuid,))

    def insertDocument(self, type, name, document, parent='', link='', uuid=None, timestamp=None, blob=b'', signature=b''):
        if not signature and not self.secretKey:
            raise ValueError("Cannot sign any new documents, you do not have the keys")
        ts = int((timestamp or time.time())*10**6)
        localts = int((timestamp or time.time())*10**6)

        # If a UUID has been supplied, we want to erase any old record bearing that name.
        if uuid:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT _time FROM document WHERE _uuid=?", (uuid,))
            x = cur.fetchone()

            if x:
                # Check that record we are trying to insert is newer, else ignore
                if x[0] < ts:
                    self.updateDocument(uuid, type=type, name=name, document=document,
                                        parent=parent,  link=link, ts_int=ts, localts_int=localts, blob=blob)

                    # If we are marking this as deleted, we can ditch everything that depends on it.
                    # We don't even have to just set them as deleted, we can relly delete them, the deleted parent record
                    # is enough for other nodes to know this shouldn't exist anymore.
                    if type == ".null":
                        self.conn.execute(
                            "DELETE FROM document WHERE _parent=?", (uuid,))

                    return uuid
                else:
                    return uuid

        if type in (".prop", ".elink"):
            cur = self.conn.cursor()
            cur.execute(
                "SELECT _time,_uuid FROM document WHERE _parent=? AND _name=? AND _type=?", (parent, name, type))
            x = cur.fetchone()
            if x:
                # If a uuid was explicitly specified we can't update some other record, we have
                # To make the DB state include exactly the record they gave us so nodes can sync.
                if x[0] > ts and (not uuid or uuid == x[1]):
                    # Now we have the UUID, just update that one
                    self.updateDocument(x[1], type=type, name=name, document=document,
                                        parent=parent,  link=link, ts_int=ts, localts_int=localts, blob=blob)
                    return x[1]
                else:
                    # If we have to just insert a new record then we just clear out the old records, they have been obsoleted.
                    cur.execute(
                        "DELETE FROM document WHERE _parent=? AND _name=? AND _type=?", (parent, name, type))

        uuid = uuid or str(uuidModule.uuid4())

        self.conn.execute("INSERT INTO document VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (uuid, ts, localts, parent, link, type, name,  json.dumps(document), blob, b''))
        return uuid


d = DocumentDatabase("test.db")

with d:
    for i in range(1):
        id = d.insertDocument("Butt", "buttname", {"v": random.random()})
        d.insertDocument(".prop", "fartsmell", {'smell': 'farty'}, parent=id)
        d.insertDocument(".prop", "poosmell", {'poosmell': 'nasty'}, parent=id)
        d.insertDocument(".prop", "fartsmell", {'smell': 'farty2'}, parent=id)
        torm = d.insertDocument(".prop", "fartsmell2", {
                                'att': 'deletethis'}, parent=id)

        d.deleteDocument(torm)
        print(d.getMergedDocument(id))

d.conn.commit()
