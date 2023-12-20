import subprocess
import sys

import eventlet.queue
import eventlet.tpool
import eventlet.green.subprocess
from eventlet import green
from eventlet.greenpool import GreenPool

from .BaseTerminal import BaseTerminal

import logging
logger = logging.getLogger(__name__)


class SubprocessTerminal(BaseTerminal):
    def __init__(self, cmd):
        self.process = make_simple_process(cmd)
        self.queue = eventlet.queue.Queue()
        self.greenpool = self._start_consume()

    def _start_consume(self):
        greenpool = GreenPool(5)
        greenpool.spawn_n(self._consume_stream, self.process.stdout)
        greenpool.spawn_n(self._consume_stream, self.process.stderr)
        return greenpool

    def _consume_stream(self, stream):
        while True:
            data = stream.read()
            if not data:
                break
            self._send_to_slave(data)

    def recv(self, count=None):
        return self.master_to_slave(self.queue.get())

    def _send_to_slave(self, data):
        self.queue.put(data)

    def send(self, data):
        data = self.slave_to_master(data)
        self.process.stdin.write(data)

    def slave_to_master(self, x):
        return x

    def master_to_slave(self, x):
        return x

    def close(self):
        self.process.kill()


class LinuxTerminal(SubprocessTerminal):
    def __init__(self, cmd=None):
        if cmd is None:
            cmd = ['bash']
        import shlex
        cmd = " ".join(map(shlex.quote, cmd))
        cmd = ['script', '-qfc', cmd, '/dev/null']
        super().__init__(cmd)


class WindowsTerminal(SubprocessTerminal):
    def __init__(self, cmd=None):
        if cmd is None:
            cmd = ['cmd']
        super().__init__(cmd)

    def slave_to_master(self, data):
        data = data.replace(b'\r', b'\r\n')
        self._send_to_slave(data)
        return data

    def master_to_slave(self, x):
        return x.replace(b'\n', b'\r\n')


class NonBlockingSimplePipe:
    def __init__(self, stream):
        logger.debug("NonBlockingSimplePipe.__init__ type(stream) == {}".format(type(stream)))
        logger.debug("NonBlockingSimplePipe.__init__ type(stream).__name__ == {!r}".format(type(stream).__name__))
        self.needs_thread = not is_greenpipe(stream)
        self.stream = stream

    def read(self):
        if self.needs_thread:
            return eventlet.tpool.execute(self._read)
        return self._read()

    def write(self, data):
        if self.needs_thread:
            return eventlet.tpool.execute(self._write, data)
        return self._write(data)

    def _read(self):
        return self.stream.read(2048)

    def _write(self, data):
        self.stream.write(data)
        self.stream.flush()


class NonBlockingSimpleProcess:
    def __init__(self, cmd):
        self.proc = make_subprocess(cmd)
        self.stdin = NonBlockingSimplePipe(self.proc.stdin)
        self.stdout = NonBlockingSimplePipe(self.proc.stdout)
        self.stderr = NonBlockingSimplePipe(self.proc.stderr)

    def kill(self):
        self.proc.kill()


def is_greenpipe(obj):
    # GreenFileIO is not exposed and GreenPipe is not a class, so checking by name
    return type(obj).__name__ == "GreenFileIO"


def os_terminal():
    return OS_TERMINALS[sys.platform]()


def make_subprocess(obj):
    def green_popen(cmd):
        p = subprocess.PIPE
        return green.subprocess.Popen(cmd, stdin=p, stdout=p, stderr=p, bufsize=0)
    if isinstance(obj, str):
        return green_popen([obj])
    if isinstance(obj, list):
        return green_popen(obj)
    if isinstance(obj, subprocess.Popen):
        return obj
    if isinstance(obj, green.subprocess.Popen):
        return obj
    raise Exception("Invalid argument to make_subprocess: {}".format(type(obj)))


def make_simple_process(obj):
    if isinstance(obj, NonBlockingSimpleProcess):
        return obj
    proc = make_subprocess(obj)
    return NonBlockingSimpleProcess(proc)


OS_TERMINALS = {
    'linux': LinuxTerminal,
    'win32': WindowsTerminal
}
