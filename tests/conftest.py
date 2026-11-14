"""Shared helpers. Every test is offline: sockets only ever touch 127.0.0.1 or ::1, or are faked."""

import errno
import json
import socket
import threading

import pytest


def free_port() -> int:
    """A TCP port nothing listens on (bound and released a moment ago)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeSocket:
    """Stands in for socket.socket. 'outcome' is None (connect works) or an exception to raise."""

    outcome = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, value):
        self.timeout = value

    def connect(self, address):
        if FakeSocket.outcome is not None:
            raise FakeSocket.outcome

    def close(self):
        pass


def os_error(code: int) -> OSError:
    return OSError(code, errno.errorcode.get(code, "error"))


class Clock:
    """A fake clock: each call returns the next value."""

    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        return self.values.pop(0)


@pytest.fixture
def open_port():
    """A real listener on 127.0.0.1 that accepts and closes every connection."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(64)
    srv.settimeout(0.1)
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                continue

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    yield srv.getsockname()[1]
    stop.set()
    t.join(2)
    srv.close()


@pytest.fixture
def closed_port():
    return free_port()


@pytest.fixture
def run(capsys):
    """run(module, *argv) -> (exit code, stdout, stderr). Argument errors exit 2 without a traceback."""

    def go(module, *argv):
        try:
            code = module.main(list(argv))
        except SystemExit as exc:
            code = exc.code
        out = capsys.readouterr()
        return code, out.out, out.err

    return go


@pytest.fixture
def run_json(run):
    def go(module, *argv):
        code, out, err = run(module, *argv, "--json")
        return code, json.loads(out), err

    return go
