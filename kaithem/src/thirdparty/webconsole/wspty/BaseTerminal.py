class BaseTerminal:
    def send(self, msg: bytes):
        raise NotImplementedError('send')

    def resize(self, cols: int, rows: int):
        pass

    def recv(self, count: int=None):
        raise NotImplementedError('recv')

    def close(self):
        pass
