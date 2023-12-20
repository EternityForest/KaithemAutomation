import eventlet
import eventlet.event

import logging
logger = logging.getLogger(__name__)


class GreenletRace:
    def __init__(self, tasks):
        self._event = eventlet.event.Event()
        self._tasks = [eventlet.spawn(self._wrap, fn) for fn in tasks]

    def _resolve(self, value=None):
        if not self._event.ready():
            self._event.send(value)

    def _reject(self, reason):
        if not self._event.ready():
            self._event.send_exception(reason)

    def _wrap(self, fn):
        try:
            self._resolve(fn())
        except BaseException as e:
            self._reject(e)

    def wait(self):
        self._event.wait()

    def kill_all(self):
        for greenthread in self._tasks:
            greenthread.kill()


class TerminalPipe:
    def __init__(self, ws_binding, terminal):
        self.ws_binding = ws_binding
        self.terminal = terminal
        self._tasks = None

    def pipe(self):
        try:
            self._tasks = GreenletRace([
                self._pty_to_ws,
                self._ws_to_pty
            ])
            self._tasks.wait()
        finally:
            self.close()

    def _pty_to_ws(self):
        while True:
            data = self.terminal.read()
            if not data:
                break
            self.ws_binding.send(data)

    def _ws_to_pty(self):
        while True:
            msg = self.ws_binding.receive()
            if not msg:
                break
            if msg.resize is not None:
                self.terminal.resize(*msg.resize)
            if msg.data is not None:
                self.terminal.write(msg.data)

    def close(self):
        if self._tasks is not None:
            self._tasks.kill_all()


def pipe(ws_binding, terminal):
    TerminalPipe(ws_binding, terminal).pipe()
