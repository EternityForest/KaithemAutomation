#!/usr/bin/python3

import tornado.web
import tornado.websocket

import kaithem

# This object is the same as the "kaithem" object in pages and events
api = kaithem.initialize_app()

# Here we add some custom pages to a deployment,
# In code, rather than going through the Web UI.
# The advantage here is that you can use your editor and debugger of choice,
# Making things much easier if you are building something large and complex.

# It also allows you to keep your app logic separate from Kaithem itself.

# Here we have a very basic Tornado handler.

class MainHandler(tornado.web.RequestHandler):

    async def get(self):
        components = [x for x in self.request.path.replace(".png", "").split("/") if x]

        self.write("URL Components" + str(components) + """
        <script>
            var ws_url = '/custom_app_ws'
            ws_url = window.location.protocol.replace("http", "ws") + "//" + window.location.host + ws_url
                   
            var ws = new WebSocket(ws_url);
            ws.onopen = function() {
            ws.send("Hello, world");
            };
            ws.onmessage = function (evt) {
            alert(evt.data);
            };
        </script>""")


class EchoWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        print("WebSocket opened")

    def on_message(self, message):
        self.write_message("You said: " + str(message))

    def on_close(self):
        print("WebSocket closed")


api.web.add_tornado_app("/custom_app_ws.*", EchoWebSocket, {}, '__guest__')
api.web.add_tornado_app("/custom_app_page.*", MainHandler, {}, '__guest__')


kaithem.start_server()
