

# This file manages kaithem's native SQLite document database.

# There is one table called Document

import collections
from os import environ, write
from enum import auto
import logging
from os.path import islink
import shutil
from . import websockets
import asyncio
import sqlite3
import time
import json
import uuid as uuidModule
import random
import configparser
import os


from . import libnacl
import base64
import struct
import uuid
import traceback

import socket
import re
import threading
import weakref
import uuid
import time
import struct

from .websockets import server

from .cidict import CaseInsensitiveDict

databaseBySyncKeyHash = weakref.WeakValueDictionary()


def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Resolve host and port into list of address info entries.

    Translate the host/port argument into a sequence of 5-tuples that contain
    all the necessary arguments for creating a socket connected to that service.
    host is a domain name, a string representation of an IPv4/v6 address or
    None. port is a string service name such as 'http', a numeric port number or
    None. By passing None as the value of host and port, you can pass NULL to
    the underlying C API.

    The family, type and proto arguments can be optionally specified in order to
    narrow the list of addresses returned. Passing zero as a value for each of
    these arguments selects the full range of results.
    """
    # We override this function since we want to translate the numeric family
    # and socket type values to enum constants.
    addrlist = []

    # Horrific HACC over android's inability to resolve anything!!!!!
    # Assume that all localhost and subdomainst share an address, best we can do for now
    if 'ANDROID_STORAGE' in environ and (host.endswith(".localhost") or host.endswith("127.0.0.1") or host.endswith("::1")):
        for res in socket._socket.getaddrinfo('localhost', port, family, type, proto, flags):
            af, socktype, proto, canonname, sa = res
            addrlist.append((socket._intenum_converter(af, socket.AddressFamily),
                             socket._intenum_converter(
                                 socktype, socket.SocketKind),
                             proto, canonname, ('127.0.0.1' if af == socket.AF_INET6 else "::1", port)))

    else:
        try:
            for res in socket._socket.getaddrinfo(host, port, family, type, proto, flags):
                af, socktype, proto, canonname, sa = res
                addrlist.append((socket._intenum_converter(af, socket.AddressFamily),
                                 socket._intenum_converter(
                                     socktype, socket.SocketKind),
                                 proto, canonname, sa))
        except:
            print(host)
            raise
    return addrlist


socket.getaddrinfo = getaddrinfo


class Session():
    def __init__(self, isClientSide):
        self.alreadyDidInitialSync = False
        self.isClientSide = isClientSide
        # When you send the client all new changes
        # Set this flag to say what the most recent messaage is, so you can then
        # Get all more recent messages than that.
        self.lastResyncFlushTime = 0

        # We don't actually know who the other end is till we get a message.
        self.remoteNodeID = None

        # Just used as a match flag for the DB to avoid loops
        self.b64RemoteNodeID = 'UNKNOWN'

        self.location = 'unknown'


async def DBAPI(websocket, path):
    session = Session(False)
    kaTimestamp = 0

    try:
        a = await websocket.recv()

        databaseBySyncKeyHash[a[1:17]].dbConnect()
        logging.info("incoming connection to DB! ")
        x = databaseBySyncKeyHash[a[1:17]].handleBinaryAPICall(
            a, session, forceResponse=True)
        if x:
            await websocket.send(x)

        def f(x):
            asyncio.run_coroutine_threadsafe(websocket.send(x), wsloop)

        session.send = f
        databaseBySyncKeyHash[a[1:17]].subscribers[time.time()] = session

        db = databaseBySyncKeyHash[a[1:17]]

        while not websocket.closed:
            try:
                a = await asyncio.wait_for(websocket.recv(), timeout=5)
                x = databaseBySyncKeyHash[a[1:17]
                                          ].handleBinaryAPICall(a, session)
                if x:
                    await websocket.send(x)

            except (TimeoutError, asyncio.TimeoutError):
                pass

            if db.lastChange > session.lastResyncFlushTime:
                pass
            
            if kaTimestamp < (time.time()-(240 if (not (session.remoteNodeID == db.localNodeVK)) else 30)):
                kaTimestamp = time.time()
                if session.remoteNodeID == db.localNodeVK:
                    r = {'connectedServers': db.connectedServers}
                else:
                    r={}
                await websocket.send(db.encodeMessage(r))


    except websockets.exceptions.ConnectionClosedOK:
        print("Connection closed with client!!")
    except:
        logging.exception("Error in DDB server")
        raise


start_server = None

serverLocalPorts = [0]

slock = threading.RLock()


def stopServer():
    global start_server
    if start_server:
        try:
            start_server.close()
        except:
            logging.exception()
        start_server = None


wsloop = None

# Mutable container
wsloopc = [0]

wsloop = asyncio.new_event_loop()
wsloopc[0] = wsloop


def startServer(port, bindTo='localhost'):
    if not port:
        port = int((random.random()*10000)+10000)
    global start_server, wsloop
    stopServer()

    # Icky hack, detect and restore the current event loop.
    # We want to make a custom loop just for the server so we have to set it as the main one.
    try:
        l = asyncio.get_event_loop()
    except:
        l = None

    asyncio.set_event_loop(wsloop)
    s = websockets.serve(DBAPI, bindTo, port)
    serverLocalPorts[0] = port

    async def f():
        with slock:
            global start_server
            with slock:
                start_server = await s
            await start_server.wait_closed()
            # Stop when the server is closed.
            asyncio.get_event_loop().stop()

    def f2():
        # Pass off the loop to the new thread, we won't touch it after this
        asyncio.set_event_loop(wsloop)
        asyncio.get_event_loop().run_until_complete(f())

    # DB will eventually handle consistency by itself.
    t = threading.Thread(
        target=f2, daemon=True)
    t.start()

    for i in range(1000):
        if not start_server:
            time.sleep(0.01)
        else:
            break

    if l:
        asyncio.set_event_loop(l)

    if not start_server.sockets:
        raise RuntimeError("Server not running")
    # Terrible stuff here. We are going to try to restore the event loop.

    time.sleep(3)


def jsonEncode(d):
    return json.dumps(d, sort_keys=True, indent=0, separators=(',', ':'))


nodeIDSecretPath = "~/.drayerdb/config/nodeid-secret"


def readNodeID():
    # # Using challenge response, nodes can identify
    if not os.path.exists(os.path.expanduser(nodeIDSecretPath)):
        os.makedirs(os.path.dirname(os.path.expanduser(
            nodeIDSecretPath)), 0o700, exist_ok=True)
        with open(os.path.expanduser(nodeIDSecretPath), 'w') as f:
            f.write(base64.b64encode(os.urandom(32)).decode("utf8"))

    with open(os.path.expanduser(nodeIDSecretPath)) as f:
        return base64.b64decode(f.read().strip())


class DocumentDatabase():
    def __init__(self, filename, keypair=None, servable=True, forceProxy=None):
        "We can open TOML files as if they were databases, we just can't sync them"

        self.filename = os.path.abspath(filename)
        self.threadLocal = threading.local()

        # Track pending null records so we know to also null out any child records when we commit.
        self.uncommittedNullRecordsIDs = {}

        # A hint to know when to do real rescan
        self.lastChange = 0

        self.documentCache = collections.OrderedDict()

        # Android apparently doesbn't accept multiple cursors doimf stuff so we have to be ultra careful about that
        self.lock = threading.RLock()

        # Websockets that are subscribing to us.
        self.subscribers = weakref.WeakValueDictionary()

        self.dbConnect()

        # Track connection timestamps of when the last time we got a message from every server was
        self.connectedServers = {}

        self.inTransaction = 0

        # When we have uncommitted recprds this should be the arrival time of the first one
        self.earliestUncommittedRecord = 0

        self.config = configparser.ConfigParser(dict_type=CaseInsensitiveDict)

        if os.path.exists(filename+".ini"):
            self.config.read(filename+".ini")

        self.threadLocal.conn.row_factory = sqlite3.Row
        with self:
            with self.lock:
                # self.threadLocal.conn.execute("PRAGMA wal_checkpoint=FULL")
                self.threadLocal.conn.execute("PRAGMA secure_delete = off")
                self.threadLocal.conn.execute("PRAGMA journal_mode=WAL;")

                # Yep, we're really just gonna use it as a document store like this.
                self.threadLocal.conn.execute(
                    '''CREATE TABLE IF NOT EXISTS document (rowid integer primary key, json text, signature text, arrival integer, receivedFrom text, localinfo text)''')

                self.threadLocal.conn.execute('''CREATE TABLE IF NOT EXISTS meta
                    (key text primary key, value  text)''')

                self.threadLocal.conn.execute('''CREATE TABLE IF NOT EXISTS peers
                    (peerID text primary key, lastArrival integer, horizon integer, info text)''')

                # Preferentially use documentTime, if htat is not available use the low level data timestamp.
                # documentTime is a user-settable field that can go backwards, wheras time must be the raw record creation time
                self.threadLocal.conn.execute(
                    '''CREATE INDEX IF NOT EXISTS document_parent_type_time ON document(IFNULL(json_extract(json,"$.parent"),"")  ,json_extract(json,"$.type"), IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))) ''')

                self.threadLocal.conn.execute(
                    '''CREATE INDEX IF NOT EXISTS document_parent_pinrank ON document(IFNULL(json_extract(json,"$.parent"),"") ,IFNULL(json_extract(json,"$.pinRank"),0)) WHERE json_extract(json,"$.pinRank") IS NOT null''')

                self.threadLocal.conn.execute(
                    '''CREATE INDEX IF NOT EXISTS document_link ON document(json_extract(json,"$.link")) WHERE json_extract(json,"$.link") IS NOT null''')
                self.threadLocal.conn.execute(
                    '''CREATE INDEX IF NOT EXISTS document_name ON document(json_extract(json,"$.name"))''')
                self.threadLocal.conn.execute(
                    '''CREATE INDEX IF NOT EXISTS document_id ON document(json_extract(json,"$.id"))''')

                self.threadLocal.conn.execute(
                    '''CREATE INDEX IF NOT EXISTS document_arrival ON document(arrival)''')

                self.threadLocal.conn.execute("""
                    CREATE VIEW IF NOT EXISTS fts_index_target
                    AS 
                    SELECT
                        rowid AS rowid,
                        IFNULL(json_extract(json,"$.tags"), "") AS tags,
                        IFNULL(json_extract(json,"$.title"), "") AS title,
                        IFNULL(json_extract(json,"$.description"), "") AS description,
                        IFNULL(json_extract(json,"$.body"), "") AS body
                    FROM document
                """)
                # To keep indexing simple and universal, it only works on four standard properties. tags, title, descripion, body
                self.threadLocal.conn.execute('''
                    CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts4(content='fts_index_target', tags, title, description, body, )''')

                self.threadLocal.conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS search_index_bu BEFORE UPDATE ON document BEGIN
                    DELETE FROM search WHERE docid=old.rowid;
                    END;''')
                self.threadLocal.conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS search_index_bd BEFORE DELETE ON document BEGIN
                    DELETE FROM search WHERE docid=old.rowid;
                    END;''')
                self.threadLocal.conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS search_index_au AFTER UPDATE ON document BEGIN
                    INSERT INTO search(docid, tags,title, description, body) VALUES (new.rowid, IFNULL(json_extract(new.json,"$.tags"), ""), IFNULL(json_extract(new.json,"$.title"), ""), IFNULL(json_extract(new.json,"$.description"), "") , IFNULL(json_extract(new.json,"$.body"),""));
                    END;''')
                self.threadLocal.conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS search_index_ai AFTER INSERT ON document BEGIN
                    INSERT INTO search(docid, tags,title, description, body) VALUES (new.rowid, IFNULL(json_extract(new.json,"$.tags"), ""), IFNULL(json_extract(new.json,"$.title"), ""), IFNULL(json_extract(new.json,"$.description"), "") , IFNULL(json_extract(new.json,"$.body"),""));
                    END;
                '''
                                              )

            # old fts5 stuff, don't use, android doesn't like
            # self.threadLocal.conn.execute(
            #     """
            #     CREATE TRIGGER IF NOT EXISTS search_index AFTER INSERT ON document BEGIN
            #     INSERT INTO search(rowid, tags,title, description, body) VALUES (new.rowid, IFNULL(json_extract(new.json,"$.tags"), ""), IFNULL(json_extract(new.json,"$.title"), ""), IFNULL(json_extract(new.json,"$.description"), "") , IFNULL(json_extract(new.json,"$.body"), ""));
            #     END;
            #     """)

            # self.threadLocal.conn.execute(
            #     """   CREATE TRIGGER IF NOT EXISTS search_delete AFTER DELETE ON document BEGIN
            #     INSERT INTO search(search, rowid, tags, title,description, body) VALUES ('delete', old.rowid, IFNULL(json_extract(old.json,"$.tags"), ""), IFNULL(json_extract(old.json,"$.title"), ""), IFNULL(json_extract(old.json,"$.description"), ""), IFNULL(json_extract(old.json,"$.body"), ""));
            #     END;""")

            # self.threadLocal.conn.execute(
            #     """
            #     CREATE TRIGGER IF NOT EXISTS search_update AFTER UPDATE ON document BEGIN
            #     INSERT INTO search(search, rowid, tags, title,description, body) VALUES ('delete', old.rowid, IFNULL(json_extract(old.json,"$.tags"), ""),IFNULL(json_extract(old.json,"$.title"), ""), IFNULL(json_extract(old.json,"$.description"), ""), IFNULL(json_extract(old.json,"$.body"), ""));
            #     INSERT INTO search(rowid, tags, title,description, body) VALUES (new.rowid, IFNULL(json_extract(new.json,"$.tags"), ""), IFNULL(json_extract(new.json,"$.title"), ""), IFNULL(json_extract(new.json,"$.description"), ""), IFNULL(json_extract(new.json,"$.body"), ""));
            #     END;
            #     """
            # )

        # If a db is deleted and recreated at the same file path, this means we have a chance of
        # detecting that in the remote node by making the localNodeVK different.

        # The point of this is to uniquiely identify a DB instance so that we always know what records we have or don't have.
        self.nodeIDSeed = self.getMeta("nodeIDSeed")
        if not self.nodeIDSeed:
            self.nodeIDSeed = os.urandom(24).hex()
            self.setMeta("nodeIDSeed", self.nodeIDSeed)

        if 'Database' not in self.config:
            self.config.add_section('Database')

        # How many days to keep records that are marked as temporary
        self.autocleanDays = float(
            self.config['Database'].get('autocleanDays', '0'))

        self.syncKey = self.writePassword = None

        if (not filename.endswith('.toml')):
            if not keypair:
                if 'Sync' not in self.config:
                    vk, sk = libnacl.crypto_sign_keypair()
                    self.config.add_section('Sync')
                    self.config.set('Sync', 'syncKey',
                                    base64.b64encode(vk).decode('utf8'))
                    self.config.set('Sync', 'writePassword',
                                    base64.b64encode(sk).decode('utf8'))
                    self.saveConfig()

                self.syncKey = self.config.get(
                    'Sync', 'syncKey', fallback=None)
                self.writePassword = self.config.get(
                    'Sync', 'writePassword', fallback='')

            else:
                self.syncKey = base64.b64encode(keypair[0]).decode()
                self.writePassword = base64.b64encode(keypair[1]).decode()

            # Deterministically generate a keypair that we will use to sign all correspondance
            # writePassword has to be a part of it because nodes that have it are special and we want it
            # to be harder to fake one, plus adding one should effectively make it a new node so we know
            # to check things we couldn't trust before.
            self.localNodeVK, self.localNodeSK = libnacl.crypto_sign_seed_keypair(
                libnacl.crypto_generichash((os.path.basename(filename)+self.nodeIDSeed+self.writePassword).encode("utf8"), readNodeID()))
        else:
            self.localNodeVK, self.localNodeSK = libnacl.crypto_sign_keypair()
            self.syncKey, self.writePassword = libnacl.crypto_sign_keypair()
            self.syncKey = base64.b64encode(self.syncKey).decode('utf8')
            self.writePassword = base64.b64encode(
                self.writePassword).decode('utf8')

        if (not filename.endswith('.toml')):
            if self.config['Sync'].get("serve", '').strip():
                servable = self.config['Sync'].get(
                    "serve").lower() in ("true", 'yes', 'on', 'enable')

            if self.syncKey and servable:
                databaseBySyncKeyHash[libnacl.crypto_generichash(
                    libnacl.crypto_generichash(base64.b64decode(self.syncKey)))[:16]] = self

        self.serverURL = None
        self.syncFailBackoff = 1

        self.onRecordChangeLock = threading.RLock()

        # Get the most recently arrived message, so we are able to rescan for any direct changes
        cur = self.threadLocal.conn.cursor()
        # Avoid dumping way too much at once
        cur.execute(
            "SELECT arrival FROM document ORDER BY arrival DESC LIMIT 1")
        x = cur.fetchone()
        if x:
            self.lastDidOnRecordChange = x[0]
        else:
            self.lastDidOnRecordChange = 0
        cur.close()

        # #Legacy Fixup!!!

        # for j in ('row','post','row.template'):
        #     for i in self.getDocumentsByType(j):
        #         if 'parent' in i:
        #             i['time']+=1
        #             i['parent']=i['parent'].split("/")[-1].replace('.$','')
        #             self.setDocument(i)
        # self.commit()

        if (filename.endswith('.toml')):
            with open(filename) as f:
                self.importFromToml(f.read())
            # Lock it
            self.writePassword = None

        if (not filename.endswith('.toml')):
            self.useSyncServer(forceProxy or self.config.get(
                'Sync', 'server', fallback=None))

        if self.writePassword:
            with self:
                # Set the database ID if it is not already set.
                # Because of how sync works this really can't be a stable thing.
                # I don't know what it is good for actually.  But it's as good as anything to be sure we always
                # Have at least one record in case that is every important.
                x = self.getDocumentByID(
                    'b82e3647-4411-4107-b78a-b8256cee7a65')
                if not x:
                    self.setDocument({
                        'type': 'meta',
                        # Timestamps are negative numbers here so that older ones win.
                        # We want this to be a stable ID.  But we can't rely on this alone
                        # Because we might not have a good clock.  So it is important that we check for an existing record.
                        'time': -(time.time()*10**6),
                        'id': 'b82e3647-4411-4107-b78a-b8256cee7a65',
                        'name': 'databaseID',
                        'value': str(uuid.uuid4())
                    })
            self.commit()

    def close(self):
        self.useSyncServer("")
        try:
            self.threadlocal.conn.close()
        except:
            pass
        try:
            if self.syncKey:
                del databaseBySyncKeyHash[libnacl.crypto_generichash(
                    libnacl.crypto_generichash(base64.b64decode(self.syncKey)))[:16]]
        except KeyError:
            pass

    def scanForDirectChanges(self):
        "Check the DB for any records that have been changed, but which "
        with self.lock:
            cur = self.threadLocal.conn.cursor()
            # Avoid dumping way too much at once
            cur.execute(
                "SELECT json,signature,arrival FROM document WHERE arrival>?", (self.lastDidOnRecordChange,))
            for i in cur:
                r = json.loads(i[0])
                try:
                    del self.documentCache[r['id']]
                except KeyError:
                    pass

                self._onRecordChange(r, i[1], i[2])
            cur.close()

    def useSyncServer(self, server, permanent=False):
        with self.lock:
            if server == self.serverURL:
                return
            if permanent:
                self.config.set('Sync', 'serverURL', server)

            self.serverURL = server
            if not server:
                return

            t = threading.Thread(target=self.serverManagerThread, daemon=True)
            t.start()

    def cleanOldEphemeralData(self, horizon):
        k = {}
        torm = []

        with self.lock:
            for i in self.threadLocal.conn.execute('SELECT json FROM document ORDER BY json_extract(json,"$.time") DESC'):
                i = json.loads(i)
                if 'autoclean' in i:
                    if not i:
                        if i.get('time', horizon) < horizon:
                            torm.append(i['id'])
                    else:
                        # If autoclean specifies a channel, we want to retain the
                        if (i['autoclean'] and i.get('parent', '')) in k:
                            torm.append(i['id'])
                        else:
                            k[(i['autoclean'] and i.get('parent', ''))] = True

                # If we are trying to track more than 100k different keys we may fill all RAM.
                if len(k) > 100000:
                    for i in k:
                        x = i
                    del x[x]
                if len(torm) > 100000:
                    break

    def serverManagerThread(self):
        oldServerURL = self.serverURL
        loop = asyncio.new_event_loop()

        logging.info("Server Manager Target is:"+oldServerURL)
        while oldServerURL == self.serverURL:
            try:
                if loop.run_until_complete(self.openSessionAsClient(loop)):
                    self.syncFailBackoff = 1
            except:
                logging.exception("Error in DB Client")

            self.syncFailBackoff *= 2
            self.syncFailBackoff = min(self.syncFailBackoff, 5*60)

            # Small increments so we can interrupt it
            for i in range(5*60):
                if i > self.syncFailBackoff:
                    break
                time.sleep(1)

        loop.stop()
        loop.close()

    async def openSessionAsClient(self, loop):
        global wsloop

        if not self.serverURL:
            return 1

        session = Session(True)
        session.location = self.serverURL

        oldServerURL = self.serverURL

        # Allow directly copy and pasting http urls, we know what they mean and this
        # makes it easier for nontechnical users
        x = self.serverURL.split("://")[-1]
        if self.serverURL.split("://")[0] in ('wss', 'https'):
            x = 'wss://'+x
        else:
            x = 'ws://'+x


        #Sites should have one and only one drayer api
        x = x.split("/")[0] + '/drayer_api'


        port = x.split(":")[-1]
        try:
            # Move port off to own thing
            port = int(port)
            x = x[:-(len(str(port))+1)]
        except:
            port = 80 if x.startswith("ws://") else 443

        logging.info("Connecting to "+x+" on port "+str(port))
        async with websockets.connect(uri=x, port=port) as websocket:
            logging.info("Connected to "+x)

            try:
                self.dbConnect()

                # Empty message so they know who we are
                await websocket.send(self.encodeMessage({}))

                def f(x):
                    asyncio.run_coroutine_threadsafe(websocket.send(x), loop)

                session.send = f
                self.subscribers[time.time()] = session

                while not websocket.closed:
                    try:
                        a = await asyncio.wait_for(websocket.recv(), timeout=5)
                        r = self.handleBinaryAPICall(a, session)
                        if r:
                            await websocket.send(r)

                        self.connectedServers[x+':'+str(port)] = time.time()

                        # The initial request happens after we know who they are
                        if session.remoteNodeID and not session.alreadyDidInitialSync:
                            r = {}
                            with self.lock:
                                # Don't request from ourself and thereby waste time
                                if not session.remoteNodeID == self.localNodeVK:
                                    cur = self.threadLocal.conn.cursor()
                                    cur.execute(
                                        "SELECT lastArrival FROM peers WHERE peerID=?", (base64.b64encode(session.remoteNodeID),))

                                    c = cur.fetchone()
                                    if c:
                                        c = c[0]
                                    else:
                                        c = 0
                                    # No falsy value allowed, that would mean don't get new arrivals
                                    r['getNewArrivals'] = c or 1
                                    cur.close()

                            session.alreadyDidInitialSync = True
                            await websocket.send(self.encodeMessage(r))

                    except (TimeoutError, asyncio.TimeoutError):
                        pass

                    if self.lastChange > session.lastResyncFlushTime:
                        pass

                    if not oldServerURL == self.serverURL:
                        return

            except websockets.exceptions.ConnectionClosedOK:
                logging.info("Connection Closed to "+x)
            except:
                logging.exception("Error in DDB WS client")
                return 0
            finally:
                try:
                    # Mark disconnected.
                    self.connectedServers[x+':'+str(port)] = -1
                except:
                    pass

    def dbConnect(self):
        if not hasattr(self.threadLocal, 'conn'):

            filename = self.filename
            if filename.endswith('.toml'):
                import urllib
                filename = 'file:' + \
                    urllib.parse.quote(self.filename, safe='') + \
                    '?mode=memory&cache=shared'

            if not os.path.exists(filename):
                print("Creating new DB file at:"+filename)
            self.threadLocal.conn = sqlite3.connect(filename)

            # Lets make our own crappy fake copy of JSON1, so we can use it on
            # Sqlite versions without that extension loaded.

            def json_valid(x):
                try:
                    json.loads(x)
                    return 1
                except:
                    return 0

            self.threadLocal.conn.create_function(
                "json_valid", 1, json_valid, deterministic=True)

            def json_extract(x, path):
                try:
                    j = json.loads(x)

                    # Remove the $., this is just a limited version that only supports top level index getting
                    path = path[2:]
                    j = j[path]
                    if isinstance(j, (dict, list)):
                        return json.dumps(j)
                    else:
                        return j

                except:
                    return None

            self.threadLocal.conn.create_function(
                "json_extract", 2, json_extract, deterministic=True)

    def _checkIfNeedsResign(self, i):
        "Check if we need to redo the sig on a record,sig pair because the key has changed.  Return sig, old sig if no correction needed"
        kdg = libnacl.crypto_generichash(base64.b64decode(self.syncKey))[:8]
        if not base64.b64decode(i[1])[24:].startswith(kdg):
            if self.writePassword:
                mdg = libnacl.crypto_generichash(i[0].encode())[:24]
                sig = libnacl.crypto_sign_detached(
                    mdg, base64.b64decode(self.writePassword))
                signature = base64.b64encode(mdg+kdg+sig).decode()
                id = json.loads(i[0])['id']
                with self.lock:
                    c2 = self.threadLocal.conn.execute(
                        'UPDATE document SET signature=? WHERE json_extract(json,"$.id")=?', (signature, id))

                return signature
            else:
                raise RuntimeError(
                    "Record needs resign but no key to do so is present")

        return i[1]

    def handleBinaryAPICall(self, a, sessionObject=None, forceResponse=False):
        # Process one incoming binary API message.  If part of a sesson, using a sesson objert enables certain features.
        logging.info("i got a msg")

        # Message type byte is reserved for a future use
        if not a[0] == 1:
            return
        a = a[1:]

        # Get the key hint
        k = a[:16]
        a = a[16:]
        binTimestamp = a[:8]

        protectedData = a[8:]

        # The "public key" in this protocol is actually secret which means signed messages have to be
        # encrypted with an outer layer symmetric key derived from the public key,
        openingKey = libnacl.crypto_generichash(base64.b64decode(self.syncKey))
        keyHint = libnacl.crypto_generichash(openingKey)[:16]

        if k == keyHint:
            pass
        else:
            raise RuntimeError("Bad Key Hint")

        # First we decrypt the outer layer symmetric coding
        # Pad the timestamp to get the bytes.
        d = libnacl.crypto_secretbox_open(
            protectedData, binTimestamp+b'\0'*16, openingKey)

        remoteNodeID = d[:32]
        if sessionObject and sessionObject.remoteNodeID:
            if not remoteNodeID == sessionObject.remoteNodeID:
                raise RuntimeError("Remote ID changed in same session")

        sessionObject.remoteNodeID = remoteNodeID
        sessionObject.b64RemoteNodeID = base64.b64encode(remoteNodeID).decode()

        d = d[32:]

        # Verify that it is from who it claims to be from
        a = libnacl.crypto_sign_open(d, remoteNodeID)

        # Timestamp bytes are repeated within the signed portion,
        # So we know when they generated the message
        tbytes = a[:8]
        t = struct.unpack("<Q", tbytes)[0]

        # reject very old stuff
        if t < (time.time()-3600)*1000000:
            logging.info("Ancient Message")
            return {}

        # Get the data
        d = a[8:]

        if sessionObject:
            sessionObject.remoteNodeID = remoteNodeID

        d = json.loads(d)

        r = {'records': []}

        if sessionObject and not sessionObject.isClientSide and remoteNodeID == self.localNodeVK:
            # When talking to ourselves, let ourself know what servers we are connected to.
            # Don't spread this to anyone but ourselves, that would cause a big increase in the size
            # This is meant for when you are talking to yourself as an IPC mechanism and the frontend needs to
            # display what the backend is connected to.

            # Only from server to client. No L00Ps allowed!!
            r['connectedServers'] = self.connectedServers

        b64RemoteNodeID = base64.b64encode(remoteNodeID).decode()
        logging.info("msg was from:" + b64RemoteNodeID)
        logging.info("we are:" + base64.b64encode(self.localNodeVK).decode())

        # It is an explicitly supported use case to have both the client and the server of a connection share the same database, for use in IPC.
        # In this scenario, it is useless to send ir request old records, as the can't get out of sync, there is only one DB.
        if not remoteNodeID == self.localNodeVK:
            with self.lock:
                cur = self.threadLocal.conn.cursor()
                cur.execute(
                    "SELECT lastArrival,horizon FROM peers WHERE peerID=?", (b64RemoteNodeID,))

                peerinfo = cur.fetchone()
                # How far back do we have knowledge of ther peer's records
                peerHorizon = time.time()*1000000
                isNewPeer = False
                if peerinfo:
                    c = peerinfo[0]
                    peerHorizon = peerinfo[1]
                else:
                    isNewPeer = True
                    c = 0
                cur.close()

            if sessionObject and not sessionObject.alreadyDidInitialSync:

                # No falsy value allowed, that would mean don't get new arrivals
                r['getNewArrivals'] = c or 1
                sessionObject.alreadyDidInitialSync = True

            if "getNewArrivals" in d:
                # Mark it as ok to send newer recordas than this immediatelty when we get them
                sessionObject.lastResyncFlushTime = max(
                    sessionObject.lastResyncFlushTime, d['getNewArrivals'])

                kdg = libnacl.crypto_generichash(
                    base64.b64decode(self.syncKey))[:8]
                with self.lock:
                    cur = self.threadLocal.conn.cursor()
                    # Avoid dumping way too much at once
                    cur.execute(
                        "SELECT json,signature,arrival FROM document WHERE arrival>? AND receivedFrom!=? LIMIT 100", (d['getNewArrivals'], b64RemoteNodeID))

                    # Declares that there are no records left out in between this time and the first time we actually send
                    r['recordsStartFrom'] = d['getNewArrivals']

                    needCommit = False

                    for i in cur:
                        sig = i[1]
                        # Detect if the record was signed with an old key and needs to be resigned
                        if not base64.b64decode(i[1])[24:].startswith(kdg):
                            if self.writePassword:
                                sig = self._checkIfNeedsResign(i)
                                needCommit = True
                            else:
                                # Can't send stuff sent with old keys if we can't re sign, they will have to get from a source that can.
                                continue
                        else:
                            signature = i[1]

                        if not 'records' in r:
                            r['records'] = []
                        logging.info(i)
                        r['records'].append([i[0], sig, i[2]])

                        sessionObject.lastResyncFlushTime = max(
                            sessionObject.lastResyncFlushTime, i[2])
                    cur.close()
                    if needCommit:
                        self.commit()
        else:
            # If we are talking to ourselves in IPC mode and we are the client, assume that their set
            # of servers is actually ours because we are using them as a proxy.
            if 'connectedServers' in d and sessionObject.isClientSide:
                self.connectedServers.update(d['connectedServers'])

        needUpdatePeerTimestamp = False
        if "records" in d and d['records']:
            logging.info("Has records")
            # If we ARE the same database as the remote node, we already have the record they are telling us about, we just need to do the notification
            if not remoteNodeID == self.localNodeVK:
                with self:
                    try:
                        latest = 0
                        for i in d['records']:

                            self.setDocument(
                                i[0], i[1], receivedFrom=b64RemoteNodeID, remoteArrivalTime=i[2])
                            r['getNewArrivals'] = latest = max(latest, i[2])
                            needUpdatePeerTimestamp = True

                        if needUpdatePeerTimestamp:
                            # Set a flag saying that
                            with self.lock:
                                cur = self.threadLocal.conn.cursor()

                                if not isNewPeer:
                                    # If the recorded lastArrival is less than the incoming recordsStartFrom, it would mean that there is a gap in which records
                                    # That we don't know about could be hiding.   Don't update the timestamp in that case, as the chain is broken.
                                    # We can still accept new records, but we will need to request everything all over again starting at the breakpoint to fix this.
                                    cur.execute("UPDATE peers SET lastArrival=? WHERE peerID=? AND lastArrival !=? AND lastArrival>=?",
                                                (latest, base64.b64encode(remoteNodeID).decode(), latest, d["recordsStartFrom"]))

                                    # Now we do the same thing, but for the horizon.  If the tip of the new block pf records is later than or equal to the current
                                    # horizon, we have a complete chain and we can set the horizon to recordsStartFrom, knowing that we have all records up to that point.
                                    cur.execute("UPDATE peers SET horizon=? WHERE peerID=? AND horizon !=? AND horizon<=?",
                                                (d["recordsStartFrom"], base64.b64encode(remoteNodeID).decode(), d["recordsStartFrom"],  latest))
                                else:
                                    # If the recorded lastArrival is less than the incoming recordsStartFrom, it would mean that there is a gap in which records
                                    # That we don't know about could be hiding.   Don't update the timestamp in that case, as the chain is broken.
                                    # We can still accept new records, but we will need to request everything all over again starting at the breakpoint to fix this.
                                    cur.execute("INSERT INTO peers VALUES(?,?,?,?)",
                                                (base64.b64encode(remoteNodeID).decode(), latest, d["recordsStartFrom"], '{}'))
                                cur.close()
                    finally:
                        self.commit()
            else:

                rt = 0
                for i in d['records']:
                    # Get the earliest arrival time of all these records.  We already have the records in our shared db,
                    # we just need to look them up by time range and relay them to all other nodes.
                    if rt == 0:
                        rt = i[2]
                    else:
                        rt = min(rt, i[2])
                    docObj = json.loads(i[0])
                    try:
                        del self.documentCache[docObj['id']]
                    except KeyError:
                        pass
                    # onRecordChange is not guaranteed to be once and only once!!!
                    self._onRecordChange(docObj, i[1], i[2])

                try:
                    for i in self.subscribers:
                        try:
                            x = self.getUpdatesForSession(
                                self.subscribers[i], forceSendAfter=rt-1)
                            if x:
                                self.subscribers[i].send(x)
                        except:
                            logging.info(traceback.format_exc())
                except:
                    logging.info(traceback.format_exc())

        if 'records' in r and not r['records']:
            del r['records']
        if (not r) and (not forceResponse):
            return None
        return self.encodeMessage(r)

    def getUpdatesForSession(self, session, forceSendAfter=0):
        "ForceSendAfter will force sending of update records after that point."
        # Don't send anything till they have requested something, ohterwise we will just be sending nonsense they already have
        if session.lastResyncFlushTime or forceSendAfter:
            r = {}
            with self.lock:
                cur = self.threadLocal.conn.cursor()
                # Avoid dumping way too much at once
                cur.execute(
                    "SELECT json,signature,arrival,receivedFrom FROM document WHERE arrival>? AND receivedFrom!=? LIMIT 100", (session.lastResyncFlushTime or forceSendAfter, session.b64RemoteNodeID))

                # Let the client know that there are no records left out in between the start of this message and the end of what they have
                # We know nothing is left out because we just checked the DB
                r['recordsStartFrom'] = session.lastResyncFlushTime or forceSendAfter

                for i in cur:
                    # Don't loop records
                    if not i[3] == session.b64RemoteNodeID:
                        logging.info("Pushing Update Record!")
                        if not 'records' in r:
                            r['records'] = []
                        r['records'].append([i[0], i[1], i[2]])

                    session.lastResyncFlushTime = max(
                        session.lastResyncFlushTime, i[2])
                cur.close()

            # We can of course just send nothing if there are no changes to flush.
            if r:
                return self.encodeMessage(r)
        else:
            logging.info("Not fully connected yet")

    def getAllRelatedRecords(self, record, r=None, children=True):
        "Get all children of this record, and all ancestors, as (json, signature, arrival) indexed by ID.  Note that we want all the null records so we can export deletions."
        records = {}
        r = r or {}
        with self.lock:
            cur = self.threadLocal.conn.cursor()
            # Avoid dumping way too much at once
            cur.execute(
                'SELECT json,signature,arrival FROM document WHERE  json_extract(json,"$.id")=?', (record,))

            # Expect exactly one result here
            for i in cur:
                d = json.loads(i[0])

                id = d['id']
                r[id] = i

                if children:
                    cur2 = self.threadLocal.conn.cursor()
                    cur2.execute(
                        'SELECT json,signature,arrival FROM document WHERE  json_extract(json,"$.parent")=?', (d['id'],))

                    for j in cur2:
                        d2 = json.loads(j[0])
                        id = d2['id']
                        r[id] = j

                if d.get('parent', ''):
                    cur.close()
                    # Last element of the parent is the direct ID of the parent element
                    return self.getAllRelatedRecords(d['parent'], r, children=False)
                cur.close()
                return r
            cur.close()
        return r

    def createBinaryWriteCall(self, r, sig=None):
        "Creates a binary command representing a request to insert a record."
        p = self.config.get('Sync', 'writePassword', fallback=None)
        if not p:
            if not sig:
                raise RuntimeError(
                    "You do not have the writePassword and this record is unsigned")

        d = {
            "writePassword": libnacl.crypto_generichash(p),
            "insertDocuments": [r, sig]
        }

        return self.encodeMessage(d, True)

    def encodeMessage(self, d, needWritePassword=False):
        "Given a JSON message, encode it so as to be suitable to send to another node"
        if needWritePassword and not self.writePassword:
            raise RuntimeError("You don't have a write password")

        pk = self.syncKey
        pk = base64.b64decode(pk)
        symKey = libnacl.crypto_generichash(pk)
        keyHint = libnacl.crypto_generichash(symKey)[:16]

        r = jsonEncode(d).encode('utf8')

        timeAsBytes = struct.pack("<Q", int(time.time()*1000000))

        data = r

        signed = libnacl.crypto_sign(timeAsBytes+data, self.localNodeSK)
        data = self.localNodeVK+signed

        r = libnacl.crypto_secretbox(data, timeAsBytes+b'\0'*16, symKey)

        # Reserved first byte for the format
        return bytes([1]) + keyHint + timeAsBytes + r

    def createBinaryWriteCall(self, r, sig=None):
        "Creates a binary command representing arequest to insert a record."
        p = self.config.get('Sync', 'writePassword', fallback=None)
        if not p:
            if not sig:
                raise RuntimeError(
                    "You do not have the writePassword and this record is unsigned")

        d = {
            "writePassword": libnacl.crypto_generichash(p),
            "insertDocuments": [r, sig]
        }

        return self.encodeMessage(d)

    def getMeta(self, key):
        with self.lock:
            cur = self.threadLocal.conn.cursor()
            cur.execute(
                "SELECT value FROM meta WHERE key=?", (key,))
            x = cur.fetchone()
            cur.close()
            if x:
                return x[0]

    def setMeta(self, key, value):
        with self.lock:
            x = self.getMeta(key)
            if x == value:
                return

            if x is not None:
                self.threadLocal.conn.execute(
                    "DELETE FROM meta WHERE key=?", (key, ))

            self.threadLocal.conn.execute(
                "INSERT INTO meta VALUES (?,?)", (key, value))

            self.commit()

    def getPeerSyncTime(self, key):
        with self.lock:
            cur = self.threadLocal.conn.cursor()
            cur.execute(
                "SELECT lastArrival FROM peers WHERE peerID=?", (key,))
            x = cur.fetchone()
            cur.close()
            if x:
                return x[0]
            return 0

    def setConfig(self, section, key, value):
        try:
            self.config.addSection(section)
        except:
            pass
        self.config.set(section, key, value)

    def commit(self):
        with self.lock:
            self.dbConnect()
            for i in self.uncommittedNullRecordsIDs:
                self.propagateNulls(i, self.uncommittedNullRecordsIDs[i])
            self.uncommittedNullRecordsIDs = {}

            self.threadLocal.conn.commit()
        r = self.earliestUncommittedRecord
        self.earliestUncommittedRecord = 0

        try:
            for i in self.subscribers:
                try:
                    # Their arrival time is ours, because we are the same DB.  By using -1 we are sure to catch the record.
                    # In the case of same-database stuff, the record we are about

                    # Force only applies if they haven't made a request yet though, which usually only happens when we are doing
                    # two processes with the same DB file.
                    x = self.getUpdatesForSession(
                        self.subscribers[i], forceSendAfter=r-1)
                    if x:
                        self.subscribers[i].send(x)
                except:
                    logging.info(traceback.format_exc())
        except:
            logging.info(traceback.format_exc())

    def saveConfig(self):
        with open(self.filename+".ini", 'w') as configfile:
            self.config.write(configfile)
        self.syncFailBackoff = 1

    def __enter__(self):
        self.dbConnect()
        self.threadLocal.conn.__enter__()
        return self

    def __exit__(self, *a):
        self.threadLocal.conn.__exit__(*a)

        ts = int((time.time())*10**6)

    def exportRecordSetToJSON(self, docs):
        "Export all records in the list along with all the records in the list to VCable JSON format"
        data = {}
        for i in docs:
            data.update(self.getAllRelatedRecords(i))

        # Get the records as a list, sorted by id for consistency.
        l = []
        import json
        for i in data:
            d = json.loads(data[i][0])
            l.append((d['id'], d))
        l = sorted(l)

        l = [[i[1]] for i in l]
        return json.dumps(l, sort_keys=True, indent=2)

    def exportRecordSetToTOML(self, docs):
        """Export all records in the list along with all the records in the list to VCable TOML format,
        optimized for meaningful diffs
        """
        data = {}
        for i in docs:
            data.update(self.getAllRelatedRecords(i))

        # Get the records as a list, sorted by time for consistency.
        l = []
        import json
        for i in data:
            d = json.loads(data[i][0])
            # Dict copy ensuring keys are sorted
            d2 = {}
            for i in sorted(list(d.keys())):
                d2[i] = d[i]
            d = d2
            psk = ''
            if 'parent' in d:
                parent = self.getDocumentByID(d['parent'], allowOrphans=True)
                if parent:
                    psk = parent.get('title', parent.get('name', parent['id']))

            sk = d.get('title', d.get('name', d['id']))

            # Shorter path lengths closer to the root first.  Then we group by the title of the parent(Keep related together)
            # Then we sort by the title of the record itself, finally we sort by ID.
            l.append((len(self.getPath(d['id'])), psk, sk, d['id'], d))

        l = sorted(l)

        op = {}
        for i in l:
            k = i[4].get('title', '')

            # Headings can eith represent an ID or a title or niether.

            if k and (not k in op) and not k.startswith('#'):
                op[k] = i[4]
                del i[4]['title']
            else:
                if not k and not i[4]['id'] in op:
                    op['#'+i[4]['id']] = i[4]
                    del i[4]['id']
                else:
                    op['#'+str(uuid.uuid4())] = i[4]
        import toml

        # https://github.com/sanskrit-coders/sanskrit_data/blob/7074d0d63e86052d14181f86a4788fe09ceef2df/sanskrit_data/toml_helper.py#L6
        from toml.encoder import _dump_str, TomlEncoder, unicode

        def _dump_str_prefer_multiline(v):
            multilines = v.split('\n')
            if len(multilines) > 1:
                return unicode('"""\n' + v.strip().replace('"""', '\\"""') + '\n"""')
            else:
                return _dump_str(v)

        class MultilinePreferringTomlEncoder(toml.TomlEncoder):
            def __init__(self, _dict=dict, preserve=False):
                super(MultilinePreferringTomlEncoder, self).__init__(
                    _dict=dict, preserve=preserve)
                self.dump_funcs[str] = _dump_str_prefer_multiline
        return toml.dumps(op, MultilinePreferringTomlEncoder())

    def importFromToml(self, d):
        if isinstance(d, str):
            import toml
            l = toml.loads(d)

        for i in l:
            d = l[i]
            # Fish the info we stored in theheading back into the dict
            if i.startswith("#") and not 'id' in d:
                d['id'] = i[1:]
            else:
                if not 'title' in d:
                    d['title'] = i

            # Detect non-uuid seeds.  Preserve unhashed so we can write back, for human readability.
            if not ('id' in d and (len(d['id']) == 36 and d['id'].count('-') == 4)):
                d['id'] = uuid.uuid5(
                    uuid.UUID('44628338-56d5-4663-8a29-db98daba3a31'), d.get('id', i))
                d['uuid5Seed'] = d.get('id', i)

            # Do the same thing for parents
            if 'parent' in d and (not(len(d['parent']) == 36 and d['parent'].count('-') == 4)):
                d['parent'] = uuid.uuid5(
                    uuid.UUID('44628338-56d5-4663-8a29-db98daba3a31'), d['parent'][1:])
                d['uuid5ParentSeed'] = d['parent'][1:]

            self.setDocument(d)

    def getPath(self, record, path=None, useAttribute='id'):
        """Trace back record ancestry path and return list of uuids 
        Mostly used to sort toml exports.  Instead of IDs we can also try to get a certain attribute, but ID gets used if missing.
        Note 

        """
        path = path or []

        if isinstance(record, str):
            record = self.getDocumentByID(record)
        if not record:
            return path

        p2 = []
        if record.get('parent', ''):
            p2.extend(self.getPath(record['parent']))
            p2.extend(path)
        p2.append(str(record.get(useAttribute, record['id'])))

        return p2

    def makeNewArrivalTimestamp(self):
        # Have a bit of protection from a clock going backwards to keep things monotonic
        with self.lock:
            maxArrival = self.threadLocal.conn.execute(
                "SELECT arrival FROM document ORDER BY arrival DESC limit 1").fetchone()
            if maxArrival:
                return max(maxArrival[0]+1, time.time()*10**6)

            else:
                return time.time()*10**6

    def setDocument(self, doc, signature=None, receivedFrom='', remoteArrivalTime=0, parentIsNull=False):
        with self.lock:
            self._setDocument(doc, signature, receivedFrom,
                              remoteArrivalTime, parentIsNull)

    def _setDocument(self, doc, signature=None, receivedFrom='', remoteArrivalTime=0, parentIsNull=False):
        """Two modes: Locally generate a signature, or use the existing sig data.
            When the record is remotely recieved, you must specify what arrival time the remote node thinks it came in at.        
        """

        if isinstance(doc, str):
            docObj = json.loads(doc)
        else:
            docObj = doc

        logging.info("Setting record, recieved from: "+receivedFrom +
                     " and local ID is "+base64.b64encode(self.localNodeVK).decode())

        self.dbConnect()
        oldVersionData = {}
        if 'id' in docObj:
            uid = docObj['id']
            # Ensure corrrectness of UUID representation
            if isinstance(docObj['id'], (str, bytes)):
                uid = uuid.UUID(uid)
            # No sig means we are doing it ourselves and can clean up any incorrectly formatted UUIDs
            if not signature:
                docObj['id'] = str(uid)

            with self.lock:
                # If a UUID has been supplied, we want to erase any old record bearing that name.
                cur = self.threadLocal.conn.cursor()
                cur.execute(
                    'SELECT json, json_extract(json,"$.time") FROM document WHERE  json_extract(json,"$.id")=?', (docObj['id'],))
                x = cur.fetchone()
                if x:
                    oldVersionData, oldVersion = x
                    oldVersionData = json.loads(oldVersionData)
                else:
                    oldVersion = None
                cur.close()
        else:
            oldVersion = None

        docObj['time'] = docObj.get(
            'time', time.time()*1000000) or time.time()*1000000
        docObj['id'] = docObj.get('id', str(uuid.uuid4()))
        docObj['name'] = docObj.get('name', docObj['id'])
        docObj['type'] = docObj.get('type', '')

        # Location snapback.  The parent field has it's very own location tracker.
        if self.writePassword:
            if oldVersionData.get("moveTime", 0) > docObj.get("moveTime", 0):
                if not oldVersionData.get("parent", '') == docObj.get('parent', ''):
                    # Mark as locally generated, we aren't just doing what they ask anymore
                    signature = None
                    remoteArrivalTime = None
                    receivedFrom = None
                    docObj['parent'] = oldVersionData.get("parent", '')
                    docObj['moveTime'] = int(oldVersionData.get("moveTime", 0))

                else:
                    # For locally generated records we always want to keep the move time moving forwards.
                    # If they don't explicitly specify it, carry it forward.
                    # Leave it as 0 by default though, we can use the assumed never moved value.

                    # Only if not signature though.  Don't unnecessarily mess with signed records, assume that non-local
                    # records have the correct time.
                    if not signature:
                        if int(oldVersionData.get("moveTime", 0)):
                            signature = None
                            remoteArrivalTime = None
                            receivedFrom = None
                            docObj['moveTime'] = max(int(oldVersionData.get(
                                "moveTime", 0)), int(docObj.get("moveTime", 0)))

        # Null propagation happens after any parent correction.
        if 'parent' in docObj:
            if isinstance(docObj['parent'], dict):
                docObj['parent'] = docObj['parent']['id']

            # Detect if we have a deleted BURN ancestor newer than we are, and if so, insert a null instead of this record.

            # TODO: All descendants of a deleted node become orphans that just hang around forever if they happen to be newer than
            # The deleted ancestor. Bad news!
            # But we can only do this if we have the write password.

            # Another condition is that we cannot have just gotten moved more recently than the burn record,
            # As that would be unusual and more likely caused by an accidental move, bug. or race condition.
            # Keep it as an orphan in that case
            if 'id' in docObj:
                x = self.getDocumentByID(
                    docObj['parent'], returnAncestorNull=True)

                if x and isinstance(x, dict) and x['type'] == 'null':

                    # Only applies to burn records, they have unlimited propagation.
                    if x.get('burn', False) and x['time'] > docObj.get('time', time.time()*10**6) and x['time'] > docObj.get('moveTime', 0):
                        if self.writePassword:
                            # propagate burn
                            return self._setDocument({'type': 'null', 'id': docObj['id'], 'time': x['time'], 'burn': True})
                        else:
                            # We can't null it but we sure don't have to keep it around!
                            return

                    # Non-burned only propagates one level
                    # But we can still discard it
                    elif 'time' in docObj:
                        if x['id'] == docObj['parent'] and x['time'] > docObj['time']:
                            return

        # Adding this property could cause all kinds of sync confusion with records that don't actually get deleted on remote nodes.
        # Might be a bit of a problem.
        if 'autoclean' in docObj:
            if not 'autoclean' in oldVersionData:
                # Silently ignore this error record, it would mess everything up
                if receivedFrom:
                    return
                else:
                    raise ValueError(
                        "You can't add the autoclean property to an existing record")

            if not docObj['autoclean'] == oldVersionData['autoclean']:
                # Silently ignore this error record, it would mess everything up
                if receivedFrom:
                    return
                else:
                    raise ValueError(
                        "You can't change the autoclean value of an existing record.")

        if signature:
            libnacl.crypto_generichash(doc)[:24]
            kdg = libnacl.crypto_generichash(
                base64.b64decode(self.syncKey))[:8]
            sig = base64.b64decode(signature)
            mdg = sig[:24]
            sig = sig[24:]
            recievedKeyDigest = sig[:8]
            sig = sig[8:]

            recievedMessageDigest = libnacl.crypto_generichash(doc)[:24]
            if not recievedMessageDigest == mdg:
                raise ValueError("Bad message digest in supplied record")
            if not kdg == recievedKeyDigest:
                raise ValueError("This message was signed with the wrong key")

            libnacl.crypto_sign_verify_detached(
                sig, mdg, base64.b64decode(self.syncKey))
            d = doc

        else:
            if not self.writePassword:
                raise RuntimeError(
                    "Cannot modify records without the writePassword")
            # Handling a locally created document

            d = jsonEncode(docObj)

            # This is a bit of a tricky part here.  We want to allow repeaters that
            # do not have full write privilidges in the future. So We sign with the
            # write password.  However that key is not permanently linked to
            # the database.  It could change, which would mean that older signed records
            # would not be accepted.  However, this is unavoidable really.  If the key
            # is compromised, it is essential that we obviously don't accept new records that were signed
            # with it.
            mdg = libnacl.crypto_generichash(d)[:24]

            # Only 8 bytes because it's not meant to be cryptographically strong, just a hint
            # to aid lookup of the real key
            kdg = libnacl.crypto_generichash(
                base64.b64decode(self.syncKey))[:8]
            sig = libnacl.crypto_sign_detached(
                mdg, base64.b64decode(self.writePassword))
            signature = base64.b64encode(mdg+kdg+sig).decode()

        # Don't insert messages recieved from self that we already have
        if not receivedFrom == base64.b64encode(self.localNodeVK).decode():
            # Arrival
            if oldVersion:
                # Check that record we are trying to insert is newer, else ignore
                if oldVersion < docObj['time']:
                    try:
                        c = self.threadLocal.conn.execute(
                            "DELETE FROM document WHERE IFNULL(json_extract(json,'$.id'),'INVALID')=?;", (docObj['id'],))

                        try:
                            del self.documentCache[docObj['id']]
                        except KeyError:
                            pass

                    except sqlite3.Error as er:
                        import sys
                        print('SQLite error: %s' % (' '.join(er.args)))
                        print("Exception class is: ", er.__class__)
                        print('SQLite traceback: ')
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        print(traceback.format_exception(
                            exc_type, exc_value, exc_tb))
                        raise

                else:
                    return docObj['id']

            # If the previous document was marked as a leaf node, and we are deleting it, the parent tombstone is enough,
            # We have no children that we need to have a tombstone to make sure they stay orphans.
            # We already deleted the old record, so just don't insert the new one in that specific case.
            if not(parentIsNull and oldVersionData.get('leafNode', True) and docObj['type'] == 'null'):
                if docObj['type'] == 'null':
                    # Track recievedFrom because we have to limit propagation depth for externally recieved records, to stop malicious reorder
                    self.uncommittedNullRecordsIDs[docObj['id']] = receivedFrom
                else:
                    try:
                        del self.uncommittedNullRecordsIDs[docObj['id']]
                    except KeyError:
                        pass

                c = self.threadLocal.conn.execute(
                    "INSERT INTO document VALUES (null,?,?,?,?,?)", (d, signature, self.makeNewArrivalTimestamp(), receivedFrom, '{}'))

        # Delete the cache item right after we insert it.
        try:
            del self.documentCache[docObj['id']]
        except KeyError:
            pass

        # We don't have RETURNING yet, so we just read back the thing we just wrote to see what the DB set it's arrival to
        c = self.threadLocal.conn.execute(
            "SELECT json, signature, arrival FROM document WHERE json_extract(json,'$.id')=?", (docObj['id'],)).fetchone()
        if c:
            docObj = json.loads(c[0])
            self.earliestUncommittedRecord = c[2]
            self._onRecordChange(docObj, c[1], c[2])

        self.lastChange = time.time()

        if 'autoclean' in docObj:
            # Don't do it every time that would waste CPU
            if random.random() < 0.01:
                if self.autocleanHorizon:
                    # Clear any records sharing the same autoclean channel which are older than both this record and the horizon.
                    horizon = min(
                        docObj['time'], (time.time()-(self.autocleanDays*3600*24))*1000000)
                    c = self.threadLocal.conn.execute("DELETE FROM document WHERE json_extract(json,'$.autoclean')=? AND ifnull(json_extract(json,'$.parent'),'')=? AND json_extract(json,'$.time')<?", (
                        docObj['autoclean'], docObj.get('parent', ''), horizon)).fetchone()

                    # Delete the cache item right after we insert it.
                    try:
                        del self.documentCache[docObj['id']]
                    except KeyError:
                        pass

        return docObj['id']

    def propagateNulls(self, record, recievedFrom=None, propagateTime=0, parentNull=None, depth=1):
        """On getting a batch of records, null out the children of any records that are null:burn.  Don't do this for nulls sans burn.
            parentNull is the root record of the whole thing we are propagating from.
            propagateTime is the time we use for all the null records down the tree that we get from the parent null
        """

        # Locally generated records have unlimited propagation.  Externals are limited to 1.
        # Thid is because we could move B out of A than delete A.
        # An attacker could make the delete happen before the move.

        # With no propagation limit, children of B would be silent deleted.
        # We might still have them, but we would not know we needed to send them because they never changed.

        # With a limit of 1, if the move happens afterward, the move will restore B's existence in a new place,
        # Making all it's children that never got deleted to begin with no longer orphans.

        # Don't do this in this implementation!

        # We keep more than we have to for locally generated nulls so that the user who did the delete
        # sees the same set of unreachables as anyone else, to aid them in manually nulling out anything sensitive in
        # that set!!!!

        # if not recievedFrom:
        #     depth = 128

        depth -= 1
        if depth < 0:
            return

        with self.lock:
            # Heavy duty defensive programming for such a dangerous function.
            r = self.getDocumentByID(record, returnAncestorNull=True)
            if not r:
                return

            if not propagateTime:
                propagateTime = r['time']

            if not r['type'] == 'null' and not parentNull:
                return

            # Burn has unlimited depth.  Anythiung that ever was a child of a burned record is in danger, and we just accept that.
            if r.get('burn', False):
                depth = 128

            # If we are marking this as deleted, we can ditch everything that depends on it.
            # We don't even have to just set them as deleted, we can relly delete them, the deleted parent record
            # is enough for other nodes to know this shouldn't exist anymore.
            l = []
            lastround = {}

            # Do in rounds to limit memory usage.
            # Unfortunately this means we need to always do a second round to see if we got everything.  It is kinda sucky.
            for i in range(1000000):
                # Only children that are older than the deletion of the parent should be null propagated in this way.
                # The rest we consider blocked. They become an orphan record.
                thisround = {}
                c = self.threadLocal.conn.execute(
                    "SELECT json FROM document WHERE json_extract(json,'$.parent')=? AND json_extract(json,'$.time')<? LIMIT 1000", (record, r['time']))
                for i in c:
                    x = json.loads(i[0])
                    l.append((x['id'], x['time']))
                    thisround[x['id']] = True

                # Look to see if this query has anything last did not
                shouldbreak = True

                for i in l:
                    # Note that we propagate the timestamp of the null.
                    # But note the fact that we cannot set documents if we are not an authorized writer.
                    if self.writePassword and r.get('burn', '') or (parentNull and parentNull.get('burn', '')):

                        # Setdocument knows to ignore this if the time is newer than the burn time
                        self.setDocument(
                            {'type': 'null', 'id': i[0], 'time': propagateTime, 'burn': True}, parentIsNull=True)
                    else:
                        # Silent delete unreachable.
                        c = self.threadLocal.conn.execute(
                            "DELETE FROM document WHERE json_extract(json,'$.id')=? and json_extract(json,'$.time')<=?", (i[0], propagateTime))
                        # Delete the cache item right after we insert it.
                        try:
                            del self.documentCache[i[0]]
                        except KeyError:
                            pass

                    self.propagateNulls(
                        i[0], propagateTime=propagateTime, parentNull=parentNull, depth=depth)

                    if not i[0] in lastround:
                        shouldbreak = False

                if shouldbreak:
                    break
                lastround = thisround

    def _onRecordChange(self, record, signature, arrival):
        # Ensure once and only once, at least within a session.
        # Also lets us keep track of what we have already called the function for so that we can
        # scan the DB, in case we are using the DB itself as the sync engine.
        with self.onRecordChangeLock:
            if arrival > self.lastDidOnRecordChange:
                self.onRecordChange(record, signature)
            self.lastDidOnRecordChange = arrival

            try:
                if hasattr(self, "dataCallback"):
                    if self.dataCallback:
                        self.dataCallback(self, record, signature)
            except:
                logging.exception()

    def onRecordChange(self, record, signature):
        pass

    def getDocumentByID(self, key, recursionLimit=64, returnAncestorNull=False, returnAllAncestors=False, _ancestors=None, allowOrphans=False):
        """Returns null on orphan documents.  Uses a cache to check for that.  

        returnAncestorNull is a special mode that returns the actual node that made the key an orphan if possible,
        if it is an orphan.  It will return the first null up the whole chain.

        None is for "temp orphans" which might hjust have not had the parent record come in yet.  That is when
        eeither the record itself or one of the ancestors is missing.

        """

        if returnAllAncestors and returnAncestorNull:
            raise ValueError("Cannot combine those")
        if returnAllAncestors and allowOrphans:
            raise ValueError("Cannot combine those")

        if allowOrphans and returnAncestorNull:
            raise ValueError("Cannot combine those")

        _ancestors = _ancestors or {}

        with self.lock:
            x = None
            r = None
            # We have to check the whole entire chain of parent records right up to the very top.
            # If there is a garbage cycle we have a big problem.
            if recursionLimit < 0:
                raise RuntimeError(
                    "Reference cycle is likely in this document.")

            recursionLimit -= 1

            if key in self.documentCache:
                try:
                    x = self.documentCache[key]
                    # lru renew
                    self.documentCache[key] = x
                except KeyError:
                    pass

            if not x:
                "Return None or one document by exact ID match. ID may be string or UUID instance"
                key = str(key)
                self.dbConnect()
                cur = self.threadLocal.conn.cursor()
                cur.execute(
                    "SELECT json from document WHERE json_extract(json,'$.id')=?", (key,))
                x = cur.fetchone()
                cur.close()
                if x:
                    x = json.loads(x[0])
                    if allowOrphans:
                        return x
                self.documentCache[key] = x

            if x:
                r = x
                if x.get("type", '') == 'null':
                    if returnAncestorNull:
                        return x

                else:
                    # Record has a parent.  If it is False/deleted, so are we.
                    # If it is None/just plain not found, we are a(possibly temporary)
                    # orphan, so the status propagates
                    if 'parent' in x and x['parent']:
                        p = self.getDocumentByID(
                            x['parent'], recursionLimit=recursionLimit, _ancestors=_ancestors)

                        if not p:
                            r = p
                            x = p
                        else:
                            _ancestors[p['id']] = p

            while len(self.documentCache) > 64:
                try:
                    self.documentCache.pop(True)
                except:
                    logging.exception("cleanup error, ignoring")
            if returnAllAncestors:
                return r, _ancestors
            return r

    def getDocumentsByType(self, key, startTime=0, endTime=10**18, limit=100, parent=None, descending=True, orphansOnly=False, allowOrphans=False, orderBy=None, extraFilters=''):
        """Return documents meeting the filter criteria. Parent should by the full path of the parent record, to limit the results to children of that record.
            You can try to just use the direct parent ID but that is not a guarantee, it returns nothing if we don't have the parent record.

            $
        """
        if orphansOnly:
            limit = 10**18
            allowOrphans = True

        if not parent:
            parentPath = parent
        elif isinstance(parent, str):
            parentPath = parent
        else:
            parentPath = parent['id']

        orderBy = orderBy or "IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time')) "+(
            "desc" if descending else "asc")

        self.dbConnect()
        cur = self.threadLocal.conn.cursor()

        if extraFilters:
            extraFilters = extraFilters + " AND"

        if parent is None:
            cur.execute(
                "SELECT json from document WHERE "+extraFilters+" json_extract(json,'$.type')=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))>=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))<=? ORDER BY "+orderBy+" LIMIT ?", (key, startTime, endTime, limit))
        else:
            cur.execute(
                "SELECT json from document WHERE "+extraFilters+" json_extract(json,'$.type')=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))>=? AND ifnull(json_extract(json,'$.parent'),'')=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))<=? ORDER BY "+orderBy+" LIMIT ?", (key, startTime, parent, endTime, limit))

        l = 0
        for i in cur:
            # Have to do our own limiting for the orphans scanner which could be incredible slow
            l += 1
            if l > limit:
                return

            try:
                x = json.loads(i[0])
            except:
                continue

            if not x.get('type', '') == 'null':
                isOrphan = False
                # Look for orphan records that have been 'deleted'
                if parent is None and 'parent' in x:
                    if (not allowOrphans) or orphansOnly:
                        if not self.getDocumentByID(x['parent']):
                            isOrphan = True
                            if not (orphansOnly or allowOrphans):
                                continue

                if orphansOnly:
                    if not isOrphan:
                        continue
                yield x
        cur.close()

        # return list(reversed([i for i in [json.loads(i[0]) for i in cur] if not i.get('type','')=='null']))

    def searchDocuments(self, key, type, startTime=0,  endTime=10**18, limit=100, parent=None):

        if not parent:
            parentPath = parent
        elif isinstance(parent, str):
            parentPath = parent
        else:
            parentPath = parent['id']

        self.dbConnect()
        cur = self.threadLocal.conn.cursor()
        r = []
        with self:
            if parent is None:
                cur.execute(
                    "SELECT json from ((select rowid as id from search WHERE search MATCH ?) INNER JOIN document ON id=rowid)  WHERE json_extract(json,'$.type')=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))>=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))<=? ORDER BY IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time')) DESC LIMIT ?", (key, type, startTime, endTime, limit))
            else:
                cur.execute(
                    "SELECT json from ((select rowid as id from search WHERE search MATCH ?) INNER JOIN document ON id=rowid)  WHERE ifnull(json_extract(json,'$.parent'),'')=? AND json_extract(json,'$.type')=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))>=? AND IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time'))<=? ORDER BY IFNULL(json_extract(json,'$.documentTime'), json_extract(json,'$.time')) DESC LIMIT ?", (key, parentPath, type, startTime, endTime, limit))
            for i in cur:
                r.append(i[0])

        cur.close()
        return list(reversed([i for i in [json.loads(i) for i in r]]))


if __name__ == "__main__":

    kp = libnacl.crypto_sign_seed_keypair(b'TEST'*int(32/4))
    db1 = DocumentDatabase("test1.db", keypair=kp)
    db2 = DocumentDatabase("test2.db", keypair=kp, servable=False)

    startServer(7004)
    with db1:
        db1.setDocument({'body': "From Db1"})
    with db2:
        db2.setDocument({'body': "From Db2"})

    db2.useSyncServer("ws://localhost:7004")

    with db1:
        db1.setDocument({'body': "From Db1 after connect"})
    with db2:
        db2.setDocument({'body': "From Db2  after connect"})

    time.sleep(2)
    db1.commit()
    db2.commit()

    time.sleep(2000)
