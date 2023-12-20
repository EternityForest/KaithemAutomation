from .BaseTerminal import BaseTerminal
from eventlet.queue import Queue


class EchoTerminal(BaseTerminal):
    def __init__(self):
        super().__init__()
        self._queue = Queue()

    def send(self, data):
        self._queue.put(data)

    def recv(self, count=None):
        return self._queue.get()
