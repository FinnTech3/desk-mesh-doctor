import errno
import json
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import mesh_link as ml
from conftest import free_port

SCRIPT = Path(ml.__file__)


def dial(port, payload=b"", delay=0.15, times=1, reply=None):
    """Connect from a thread after a short delay, optionally sending a payload and keeping the reply."""

    def go():
        time.sleep(delay)
        for _ in range(times):
            with socket.create_connection(("127.0.0.1", port), timeout=2) as c:
                if payload:
                    c.sendall(payload)
                if reply is not None:
                    c.settimeout(2)
                    reply.append(c.recv(4096))

    t = threading.Thread(target=go)
    t.start()
    return t


def test_a_connection_is_recorded_and_the_exit_code_is_zero(run_json):
    port = free_port()
    t = dial(port)
    code, doc, _ = run_json(ml, "listen", str(port), "--seconds", "0.7")
    t.join()
    assert code == 0 and doc["connections_total"] == 1 and doc["unique_sources"] == ["127.0.0.1"]
    assert doc["connections"][0]["from"] == "127.0.0.1" and doc["findings"] == []
    assert doc["kind"] == "listen" and doc["port"] == port


def test_silence_is_a_warning_and_the_listener_stops_on_time(run_json):
    port = free_port()
    t0 = time.monotonic()
    code, doc, _ = run_json(ml, "listen", str(port), "--seconds", "0.5")
    assert 0.45 <= time.monotonic() - t0 < 3
    assert code == 1 and doc["connections_total"] == 0
    assert doc["findings"][0]["code"] == "nothing_connected" and "client isolation" in doc["findings"][0]["message"]


def test_many_connections_are_counted_but_the_list_is_capped(run_json):
    port = free_port()
    t = dial(port, payload=b"hello\n", times=55)
    code, doc, _ = run_json(ml, "listen", str(port), "--seconds", "1.2")
    t.join()
    assert code == 0 and doc["connections_total"] == 55 and len(doc["connections"]) == 50
    assert doc["unique_sources"] == ["127.0.0.1"]


def test_a_web_browser_gets_a_one_line_answer(run_json):
    port, reply = free_port(), []
    t = dial(port, payload=b"GET / HTTP/1.1\r\nHost: x\r\n\r\n", reply=reply)
    run_json(ml, "listen", str(port), "--seconds", "0.7")
    t.join()
    assert reply[0].startswith(b"HTTP/1.0 200 OK") and b"reachable" in reply[0]


def test_a_plain_tcp_client_is_just_closed(run_json):
    port, reply = free_port(), []
    t = dial(port, payload=b"\x00\x01binary", reply=reply)
    run_json(ml, "listen", str(port), "--seconds", "0.7")
    t.join()
    assert reply == [b""]


def test_a_port_already_in_use_is_reported_not_raised(run_json):
    with socket.socket() as holder:
        holder.bind(("0.0.0.0", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        code, doc, _ = run_json(ml, "listen", str(port), "--seconds", "0.3")
    assert code == 1 and doc["findings"][0]["code"] == "bind_failed"
    assert "already listens" in doc["findings"][0]["message"]


def test_the_port_is_free_again_after_listen_returns(run_json):
    port = free_port()
    run_json(ml, "listen", str(port), "--seconds", "0.3")
    with socket.socket() as s:
        s.bind(("0.0.0.0", port))


def test_text_mode_announces_and_summarises(run):
    port = free_port()
    t = dial(port)
    code, out, _ = run(ml, "listen", str(port), "--seconds", "0.7")
    t.join()
    assert code == 0 and f"listening on TCP port {port}" in out and "connection from 127.0.0.1" in out
    assert "1 connection(s) from 127.0.0.1" in out


def test_text_mode_lists_only_the_first_few_connections_but_counts_them_all(run):
    port = free_port()
    t = dial(port, payload=b"hi\n", times=9)
    _, out, _ = run(ml, "listen", str(port), "--seconds", "1")
    t.join()
    assert out.count("connection from 127.0.0.1 at") == 5 and "9 connection(s) from 127.0.0.1" in out


def test_the_label_is_kept(run_json):
    _, doc, _ = run_json(ml, "listen", str(free_port()), "--seconds", "0.2", "--label", "desk")
    assert doc["label"] == "desk"


def test_ctrl_c_ends_the_listener_cleanly(run_json, monkeypatch):
    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(ml, "serve", interrupted)
    port = free_port()
    code, doc, _ = run_json(ml, "listen", str(port), "--seconds", "5")
    assert doc["interrupted"] is True and code == 1
    with socket.socket() as s:
        s.bind(("0.0.0.0", port))


def test_ipv4_only_machines_still_get_a_listener(monkeypatch):
    real = socket.socket

    def no_ipv6(family=socket.AF_INET, *a, **k):
        if family == socket.AF_INET6:
            raise OSError(errno.EAFNOSUPPORT, "Address family not supported by protocol")
        return real(family, *a, **k)

    monkeypatch.setattr(ml.socket, "socket", no_ipv6)
    srv = ml.bind_listener(free_port())
    try:
        assert srv.family == socket.AF_INET
    finally:
        srv.close()


def test_greet_survives_a_client_that_vanishes():
    class Gone:
        closed = False

        def settimeout(self, _):
            pass

        def recv(self, _):
            raise ConnectionResetError

        def sendall(self, _):
            raise BrokenPipeError

        def close(self):
            self.closed = True

    conn = Gone()
    ml.greet(conn)
    assert conn.closed


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM handling is POSIX")
def test_sigterm_shuts_down_cleanly_and_still_prints_the_result(tmp_path):
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "listen", str(port), "--seconds", "30", "--json"],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        time.sleep(0.3)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=5)
    finally:
        proc.kill()
    doc = json.loads(out)
    assert proc.returncode == 0 and doc["interrupted"] is True and doc["connections_total"] >= 1 and "Traceback" not in err
