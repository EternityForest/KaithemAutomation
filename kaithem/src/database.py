

# This file manages kaithem's native SQLite document database.

# There is one table called Document

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
import uuid

# from scullery import messagebus

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


def jsonEncode(d):
    return json.dumps(d, sort_keys=True, indent=4, separators=(',', ': '))


class DocumentDatabase():
    def __init__(self, filename, publicKey=None):

        self.filename = os.path.abspath(filename)

        self.conn = sqlite3.connect(filename)
        self.config = configparser.ConfigParser()

        if os.path.exists(filename+".conf"):
            self.config.read(filename+".conf")

        self.conn.row_factory = sqlite3.Row
        # Self.conn.execute("PRAGMA wal_checkpoint=FULL")
        self.conn.execute("PRAGMA secure_delete = off")

        # Yep, we're really just gonna use it as a document store like this.
        self.conn.execute(
            '''CREATE TABLE IF NOT EXISTS document (rowid integer primary key, json text, signature text, localinfo text)''')

        self.conn.execute('''CREATE TABLE IF NOT EXISTS meta
             (key text primary key, value  text)''')

        # To keep indexing simple and universal, it only works on three properties.  _tags, _description and _body.
        self.conn.execute('''
             CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(tags, description, body, content='')''')

        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_parent ON document(json_extract(json,"$._parent")) WHERE json_extract(json,"$._parent") IS NOT null ''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_link ON document(json_extract(json,"$._link")) WHERE json_extract(json,"$._link") IS NOT null''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_name ON document(json_extract(json,"$._name"))''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_id ON document(json_extract(json,"$._id"))''')
        self.conn.execute(
            '''CREATE INDEX IF NOT EXISTS document_type ON document(json_extract(json,"$._type"))''')

        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS search_index AFTER INSERT ON document BEGIN
            INSERT INTO search(rowid, tags, description, body) VALUES (new.rowid, IFNULL(json_extract(new.json,"$._tags"), ""), IFNULL(json_extract(new.json,"$._description"), ""), IFNULL(json_extract(new.json,"$._body"), ""));
            END;
            """)

        self.conn.execute(
            """   CREATE TRIGGER IF NOT EXISTS search_delete AFTER DELETE ON document BEGIN
            INSERT INTO search(search, rowid, tags, description, body) VALUES ('delete', old.rowid, IFNULL(json_extract(old.json,"$._tags"), ""), IFNULL(json_extract(old.json,"$._description"), ""), IFNULL(json_extract(old.json,"$._body"), ""));
            END;""")

        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS search_update AFTER UPDATE ON document BEGIN
            INSERT INTO search(search, rowid, tags, description, body) VALUES ('delete', old.rowid, IFNULL(json_extract(old.json,"$._tags"), ""), IFNULL(json_extract(old.json,"$._description"), ""), IFNULL(json_extract(old.json,"$._body"), ""));
            INSERT INTO search(rowid, tags, description, body) VALUES (new.rowid, IFNULL(json_extract(new.json,"$._tags"), ""), IFNULL(json_extract(new.json,"$._description"), ""), IFNULL(json_extract(new.json,"$._body"), ""));
            END;
            """
        )

        self.keys = configparser.ConfigParser()
        secretKey = None

        if os.path.exists(filename+".keys"):
            self.keys.read(filename+".keys")

        try:
            publicKey = base64.b64decode(publicKey)
        except:
            pass

        #Have a pubkey directly specified, ensure match
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
                publicKey, secretKey = libnacl.crypto_sign_keypair()
            else:
                publicKey = base64.b64decode(publicKey)

        if not self.keys.get('key', 'public', fallback=None):
            try:
                self.keys.add_section('key')
            except:
                pass
            self.keys.set('key', 'public',
                          base64.b64encode(publicKey).decode())
            self.saveConfig()

        sk =  self.keys.get('key', 'private', fallback=None)
        if sk:
            secretKey = secretKey or base64.b64decode(sk)

        if secretKey and not self.keys.get('key', 'private', fallback=None):
            try:
                self.keys.add_section('key')
            except:
                pass

            self.keys.set('key', 'private',
                          base64.b64encode(secretKey).decode())
            self.saveConfig()

        if not self.getMeta('publicKey'):
            self.setMeta("publicKey", base64.b64encode(publicKey).decode())

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

    def __enter__(self):
        self.conn.__enter__
        return self

    def __exit__(self, *a):
        self.conn.__exit__

        ts = int((time.time())*10**6)

    def setDocument(self, doc, signature=b''):
        if not signature and not self.secretKey:
            raise ValueError(
                "Cannot sign any new documents, you do not have the keys")

        doc['_time'] = doc.get('_time', time.time()*1000000)
        doc['_arrival'] = doc.get('_arrival', time.time()*1000000)
        doc['_id'] = doc.get('_id', str(uuid.uuid4()))
        doc['_name'] = doc.get('_name', doc['_id'])
        doc['_type'] = doc.get('_type', '')

        # If a UUID has been supplied, we want to erase any old record bearing that name.
        cur = self.conn.cursor()
        cur.execute(
            'SELECT json_extract(json,"$._time") FROM document WHERE  json_extract(json,"$._id")=?', (doc['_id'],))
        x = cur.fetchone()

        if x:
            # Check that record we are trying to insert is newer, else ignore
            if x[0] < ts:
                self.conn.execute("UPDATE document SET json=?, signature=? WHERE json_extract(json,'$._id')=?", (jsonEncode(
                    doc), signature,  doc['_id']))

                # If we are marking this as deleted, we can ditch everything that depends on it.
                # We don't even have to just set them as deleted, we can relly delete them, the deleted parent record
                # is enough for other nodes to know this shouldn't exist anymore.
                if doc['_type'] == "_null":
                    self.conn.execute(
                        "DELETE FROM document WHERE json_extract(json,'$._id')=?", (doc['_id'],))

                return doc['_id']
            else:
                return doc['_id']

        # If we are generating a new message, sign it automatically.
        if not signature:
            print(self.secretKey)
            signature = libnacl.crypto_sign(jsonEncode(doc).encode('utf8'), self.secretKey)

        self.conn.execute(
            "INSERT INTO document VALUES (null,?,?,?)", (jsonEncode(doc), signature,''))

        return doc['_id']


d = DocumentDatabase("test.db")

with d:
    for i in range(1):

        #Parent document
        id = d.setDocument({
                'someUserData': 9908            
            })
        
        #Child document
        d.setDocument({
            '_parent': id
        })
    


d.conn.commit()
