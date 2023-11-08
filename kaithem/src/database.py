

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

import socket
import re
import threading
import weakref
import uuid
import time
import struct


import jaraco
import cherrypy


databaseBySyncKey = weakref.WeakValueDictionary()


def expose(f):
    f.exposed = True
    return f


class WebAPI():
    @expose
    def index(self, a):
        return json.dumps(databaseBySyncKey[a[8:40]].apiCall(a))


def makeLoopWorker(o):
    def f():
        while 1:
            x = o()
            if x:
                x.poll()
            else:
                return

            del x
    return f


class LPDPeer():
    def parseLPD(self, m):
        if not 'BT-SEARCH' in m:
            return {}
        d = {}
        for i in re.findall('^(.*)?: *(.*)\r+$', m, re.MULTILINE):
            d[i[0]] = i[1]
        print(d)
        return d

    def makeLPD(self, m):
        return "BT-SEARCH * HTTP/1.1\r\nHost:{Host}\r\nPort: {Port}\r\nInfohash: {Infohash}\r\ncookie: {cookie}>\r\n\r\n\r\n".format(**m).encode('utf8')

    def poll(self):
        try:
            d, addr = self.msock.recvfrom(4096)
        except socket.timeout:
            return

        msg = self.parseLPD(d.decode('utf-8', errors='ignore'))

        if msg:
            if not msg.get('cookie', '') == self.cookie:
                with self.lock:
                    if msg['Infohash'] in self.activeHashes:
                        self.discoveries.append(
                            (msg['Infohash'], addr[0], msg['Port'], time.time()))
                        if len(self.discoveries) > 1024*64:
                            self.discoveries.pop(False)
                        self.advertise(msg['Infohash'])

    def advertise(self, hash, port=None):
        if not hash in self.activeHashes:
            raise ValueError("Unknown hash, must specify port")

        if self.lastAdvertised.get(hash, 0) > time.time()+10:
            return
        self.msock.sendto(self.makeLPD(
            {'Infohash': hash, 'Port': self.activeHashes[hash], 'cookie': self.cookie, 'Host': '239.192.152.143'}), ("239.192.152.143", 6771))
        self.lastAdvertised[hash] = time.time()

    def getByHash(self, hash):
        with self.lock:
            return [i for i in self.discoveries if i[0] == hash]

    def __init__(self):
        self.msock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Bind to the server address
        self.msock.bind(("239.192.152.143", 6771))
        self.msock.settimeout(1)

        group = socket.inet_aton("239.192.152.143")
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        self.msock.setsockopt(
            socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        self.cookie = str(uuid.uuid4())

        self.lastAdvertised = {}

        # hash:port mapping
        self.activeHashes = {}
        self.discoveries = []

        self.lock = threading.Lock()

        self.thread = threading.Thread(
            target=makeLoopWorker(weakref.ref(self)))
        self.thread.start()


def jsonEncode(d):
    return json.dumps(d, sort_keys=True, indent=4, separators=(',', ': '))


class DocumentDatabase():
    def __init__(self, filename):

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

        if os.path.exists(filename+".keys"):
            self.keys.read(filename+".keys")

        pk = base64.b64decode(self.keys.get('key', 'public', fallback=''))
        sk = base64.b64decode(self.keys.get('key', 'secret', fallback=''))

        # Generate a keypair for this particular node.
        if not (pk and sk):
            pk, sk = libnacl.crypto_sign_keypair()
            try:
                self.keys.add_section("key")
            except:
                pass
            self.keys.set('key', 'public', base64.b64encode(pk).decode('utf8'))
            self.keys.set('key', 'secret', base64.b64encode(sk).decode('utf8'))

            # Add our new key to the approved list, for our local copy.
            if 'approved' not in self.config:
                self.config.add_section('approved')
                self.config.set('approved', 'autogenerated',
                                base64.b64encode(pk).decode())
            self.saveConfig()

        self.publicKey = pk
        self.secretKey = sk

        if 'sync' not in self.config:
            self.config.add_section('sync')
            self.config.set('sync', 'syncKey', str(uuid.uuid4()))
            self.config.set('sync', 'writePassword', str(uuid.uuid4()))
            self.saveConfig()

        self.syncKey = self.config.get('sync', 'syncKey', fallback=None)

        if self.syncKey:
            databaseBySyncKey[libnacl.crypto_generichash(self.syncKey)] = self

        self.approvedPublicKeys = {}

        if 'approved' in self.config:
            for i in self.config['approved']:
                # Reverse lookup
                self.approvedPublicKeys[self.config['approved'][i]] = i

    def apiCall(self, a):
        # Process one incoming binary API message

        # Get timestamp which is also the nonce
        t = a[:8]
        t = struct.unpack("<Q", t)
        # reject very old stuff
        if t < (time.time()-3600)*1000000:
            return {}

        # Get the key ID, which is just the hash of the key.
        k = a[8:40]

        # Get the data
        d = a[40:]

        if not k == libnacl.crypto_generichash(self.syncKey):
            return

        d = libnacl.crypto_secretbox_open(d, a[:8]+'\0'+16, self.secretKey)
        d = json.loads(d)

        writePassword = d.get("writePassword", '')

        if writePassword and not writePassword == self.config.get('sync', 'writePassword', fallback=None):
            raise RuntimeError("Bad Password")

        r = {'records': []}
        if "getNewArrivals" in d:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT json,signature FROM document WHERE json_extract(json,'$._time')>?", (d['getNewArrivals'],))

            for i in cur:
                r['records'].append([i])

        if "insertDocuments" in d:
            for i in 'insertDocuments':
                if writePassword:
                    self.setDocument(i[0], i[1])

        return r

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
                "Cannot sign any new documents, you do not have the keys:"+str(self.secretKey))

        if signature:
            if not isinstance(doc, str):
                raise ValueError(
                    "Doc ,ust be an exact JSON string when providing a signature")
            key = signature.split(":")
            if not key in self.approvedPublicKeys:
                raise RuntimeError("Message was signed with a bad key")

            libnacl.crypto_sign_verify_detached(base64.b64decode(
                signature.split(":")[1], doc.encode('utf8'), b64.b64decode(key)))

            doc = json.loads(doc)

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
            signature = libnacl.crypto_sign(
                jsonEncode(doc).encode('utf8'), self.secretKey)

        self.conn.execute(
            "INSERT INTO document VALUES (null,?,?,?)", (jsonEncode(doc), signature, ''))

        return doc['_id']

    def getDocumentByID(self, key):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT json from document WHERE json_extract(json,'$._id')=?", (key,))
        x = cur.fetchone()
        if x:
            return x[0]


d = DocumentDatabase("test.db")

with d:
    for i in range(1):

        # Parent document
        id = d.setDocument({
            'someUserData': 9908
        })

        # Child document
        d.setDocument({
            '_parent': id
        })

        print(d.getDocumentByID(id))


d.conn.commit()
