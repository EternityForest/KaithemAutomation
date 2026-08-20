import queue

from kaithem.src import quart_app


async def make_client():
    client = quart_app.app.test_client(use_cookies=True)
    x = await client.post(
        "/login/login",
        follow_redirects=True,
        form={
            "username": "admin",  # pragma: allowlist secret
            "password": "test-admin-password",  # pragma: allowlist secret
        },  # pragma: allowlist secret
    )  # pragma: allowlist secret

    assert x.status_code == 200
    return client


class JackMidiSender:
    """Tiny test helper that opens a JACK MIDI output port and lets
    the caller push MIDI events through it.

    This replaces the rtmidi2 ``MidiOut`` helper used previously by the
    MIDI tests so the tests no longer depend on python-rtmidi.

    Events are queued and written from inside JACK's process callback,
    which is the only safe place to call ``OwnMidiPort.write_midi_event``.
    """

    def __init__(self, client_name: str, port_name: str):
        import queue

        import jack

        self._queue: queue.Queue[bytes] = queue.Queue()
        self._client = jack.Client(client_name)
        p = self._client.midi_outports.register(port_name)
        assert isinstance(p, jack.OwnMidiPort)
        self._port = p
        self._client.set_process_callback(self._process)
        self._client.activate()

    def _process(self, _frames):
        self._port.clear_buffer()
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            self._port.write_midi_event(0, event)

    def send_message(self, data: bytes | list[int]):
        """Queue a MIDI event for the next JACK process cycle.

        ``data`` may be a ``bytes`` object or any iterable of ints.
        """
        self._queue.put(bytes(data))

    def close(self):
        try:
            self._client.deactivate()
        except Exception:
            pass
        try:
            self._client.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
