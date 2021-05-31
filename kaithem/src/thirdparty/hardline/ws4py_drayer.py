
#This file is only used for embedding as a libraru
from ws4py.websocket import WebSocket
import threading
import time
from hardline import drayerdb
import cherrypy

class WebInterface():
    @cherrypy.expose
    def ws(self):
       pass

    @cherrypy.expose
    def index(self):
       pass

class DrayerAPIWebSocket(WebSocket):
    def __init__(self, *args, **kwargs):
        self.widget_wslock = threading.Lock()

        # We don't know what DB they are connected to
        self.db = None
        self.session = drayerdb.Session(isClientSide=True)
        WebSocket.__init__(self, *args, **kwargs)

    def send(self, *a, **k):
        with self.widget_wslock:
            WebSocket.send(self, *a, **k, binary=isinstance(a[0], bytes))

    def closed(self, code, reason):
        pass

    def received_message(self, message):
        message = message.data
        if not self.db:
            if message[1:17] in drayerdb.databaseBySyncKeyHash:
                db = drayerdb.databaseBySyncKeyHash[message[1:17]]

                def f(x):
                    self.send(x)

                self.session.send = f
                db.subscribers[time.time(
                )] = self.session
                self.db = db


        x = self.db.handleBinaryAPICall(message, self.session)
        if x:
            self.send(x)
