import codecs


class EncodedTerminal:
    def __init__(self, terminal, encoding='utf8', chunk_size=4096):
        self.terminal = terminal
        self.encoder = codecs.getincrementalencoder(encoding)()
        self.decoder = codecs.getincrementaldecoder(encoding)()
        self.encoding = encoding
        self.chunk_size = chunk_size

    def write(self, data_str):
        return self.terminal.send(self.encoder.encode(data_str))

    def resize(self, cols, rows):
        return self.terminal.resize(cols, rows)

    def read(self):
        return self.decoder.decode(self.terminal.recv(self.chunk_size))

    def close(self):
        return self.terminal.close()
