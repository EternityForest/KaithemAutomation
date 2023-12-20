import json


class DataPacket:
    def __init__(self, msg):
        self.data = msg.get('data')
        resize = msg.get('resize')
        if resize is not None:
            resize = (int(resize.get('width', 80)), int(resize.get('height', 24)))
        self.resize = resize


class WebsocketBinding:
    def __init__(self, ws):
        self.websocket = ws

    def send(self, data_str):
        self.websocket.send(json.dumps({'data': str(data_str)}))

    def send_error(self, error_str):
        self.websocket.send(json.dumps({'error': str(error_str)}))

    def receive(self):
        data = self.websocket.wait()
        if data is None:
            return None
        return DataPacket(json.loads(data))

    def close(self):
        self.websocket.close()
