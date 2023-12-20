from .BaseTerminal import BaseTerminal


class SocketTerminal(BaseTerminal):
    def __init__(self, socket):
        super().__init__()
        self.socket = socket

    def send(self, data):
        return self.socket.sendall(data)

    def recv(self, count=None):
        return self.socket.recv(count)
