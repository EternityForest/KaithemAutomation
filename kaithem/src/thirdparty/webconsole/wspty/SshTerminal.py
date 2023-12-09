import paramiko
from .BaseTerminal import BaseTerminal


class SshTerminal(BaseTerminal):
    def __init__(self, hostname='localhost', port=22, username=None, password=None, term=None):
        if term is None:
            term = 'xterm'
        super().__init__()
        self._term = term
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(
            paramiko.AutoAddPolicy())
        self._channel = None
        self._hostname = hostname
        self._port = port
        self._username = username
        self._password = password
        self._open()

    def _open(self):
        self._ssh.connect(
            hostname=self._hostname,
            port=self._port,
            username=self._username,
            password=self._password,
            look_for_keys=False
        )
        self._channel = self._ssh.invoke_shell(self._term)

    def send(self, data):
        return self._channel.send(data)

    def recv(self, count=None):
        return self._channel.recv(count)

    def close(self):
        return self._ssh.close()

    def resize(self, cols, rows):
        return self._channel.resize_pty(cols, rows)
