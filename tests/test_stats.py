import argparse
import contextlib
import errno
import socket
import sys

import pytest

import mesh_link as ml
from conftest import Clock, FakeSocket, os_error


def test_stats_of_five_known_samples():
    s = ml.stats([1, 2, 3, 4, 5])
    assert (s["min"], s["median"], s["max"], s["p95"], s["jitter"]) == (1, 3, 5, 5, 1)


def test_median_of_an_even_count_is_the_midpoint():
    assert ml.stats(list(range(1, 21)))["median"] == 10.5


def test_p95_uses_nearest_rank():
    assert ml.stats(list(range(1, 21)))["p95"] == 19  # ceil(0.95 * 20) = 19th value
    assert ml.stats(list(range(1, 101)))["p95"] == 95


def test_one_spike_in_twenty_does_not_move_p95_but_shows_in_max():
    s = ml.stats([1.0] * 19 + [100.0])
    assert s["p95"] == 1.0 and s["max"] == 100.0


def test_six_spikes_in_a_hundred_do_move_p95():
    assert ml.stats([1.0] * 94 + [100.0] * 6)["p95"] == 100.0


def test_jitter_is_the_mean_step_in_arrival_order():
    assert ml.stats([5, 1, 5, 1])["jitter"] == 4
    assert ml.stats([2, 2, 2, 2])["jitter"] == 0
    assert ml.stats([1, 2, 4])["jitter"] == 1.5


def test_a_single_sample_has_zero_jitter():
    s = ml.stats([7.5])
    assert s["median"] == s["p95"] == s["max"] == 7.5 and s["jitter"] == 0


def test_stats_round_to_two_places():
    assert ml.stats([1.23456, 1.23456])["median"] == 1.23


@pytest.mark.parametrize(
    ("median", "p95", "jitter", "grade"),
    [(2, 5, 1, "good"), (10, 30, 8, "good"), (5, 20, 15, "ok"), (20, 50, 5, "ok"), (40, 100, 5, "laggy"),
     (80, 200, 5, "poor"), (26, 70, 2, "laggy"), (51, 90, 2, "poor")],
)
def test_feel_grades_follow_the_stated_rules_of_thumb(median, p95, jitter, grade):
    assert ml.feel({"median": median, "p95": p95, "jitter": jitter}, 20, 0)["grade"] == grade


def test_feel_says_it_is_a_rule_of_thumb():
    assert "rule of thumb" in ml.feel({"median": 2, "p95": 5, "jitter": 1}, 20, 0)["text"]


def test_loss_over_five_percent_is_poor_whatever_the_latency():
    assert ml.feel({"median": 1, "p95": 2, "jitter": 0}, 20, 2)["grade"] == "poor"
    assert ml.feel({"median": 1, "p95": 2, "jitter": 0}, 20, 1)["grade"] == "good"


def test_sample_rtt_counts_answers_and_losses():
    outcomes = iter([("open", 1.0, ""), ("timeout", 1000.0, "x"), ("refused", 3.0, ""), ("open", 2.0, "")])
    got, sent, lost = ml.sample_rtt("x", 1, 4, 1.0, connect=lambda *_: next(outcomes), sleep=lambda _: None)
    assert (got, sent, lost) == ([1.0, 3.0, 2.0], 4, 1)


def test_sample_rtt_sends_exactly_n_with_a_gap_between():
    gaps = []
    got, sent, _ = ml.sample_rtt("x", 1, 5, 1.0, connect=lambda *_: ("open", 1.0, ""), sleep=gaps.append)
    assert sent == 5 and len(got) == 5 and gaps == [0.01] * 5


def test_sample_rtt_stops_when_the_time_budget_is_spent():
    ticks = iter(range(0, 1000, 10))  # the fake clock advances 10 s per reading
    got, sent, lost = ml.sample_rtt(
        "x", 1, 50, 1.0, connect=lambda *_: ("timeout", 1.0, ""), clock=lambda: next(ticks), sleep=lambda _: None,
        budget=25,
    )
    assert sent == 2 and lost == 2 and got == []


def test_tcp_connect_measures_with_the_clock_it_is_given(monkeypatch):
    monkeypatch.setattr(ml.socket, "socket", FakeSocket)
    FakeSocket.outcome = None
    assert ml.tcp_connect("127.0.0.1", 80, 1.0, clock=Clock(10.0, 10.0123)) == ("open", pytest.approx(12.3), "")


@pytest.mark.parametrize(
    ("raised", "status"),
    [
        (ConnectionRefusedError(errno.ECONNREFUSED, "refused"), "refused"),
        (TimeoutError("timed out"), "timeout"),
        (os_error(errno.ETIMEDOUT), "timeout"),
        (os_error(errno.ENETUNREACH), "unreachable_network"),
        (os_error(errno.EHOSTUNREACH), "unreachable_host"),
        (os_error(errno.ECONNRESET), "reset"),
        (os_error(errno.EACCES), "blocked_local"),
        (os_error(errno.EPERM), "blocked_local"),
        (OSError(errno.EIO, "odd failure"), "error"),
    ],
)
def test_every_failure_gets_a_plain_status(monkeypatch, raised, status):
    monkeypatch.setattr(ml.socket, "socket", FakeSocket)
    FakeSocket.outcome = raised
    got, ms, why = ml.tcp_connect("127.0.0.1", 80, 0.5, clock=Clock(0.0, 0.25))
    FakeSocket.outcome = None
    assert got == status and ms == 250.0 and why


def test_a_timeout_says_how_long_it_waited_and_what_to_suspect(monkeypatch):
    monkeypatch.setattr(ml.socket, "socket", FakeSocket)
    FakeSocket.outcome = TimeoutError()
    _, _, why = ml.tcp_connect("127.0.0.1", 80, 0.5)
    FakeSocket.outcome = None
    waited = "2.5 s" if sys.platform == "win32" else "0.5 s"  # Windows is given at least 2.5 s: it reports a refusal after about 2
    assert waited in why and "firewall" in why


def test_a_refused_connect_is_explained_as_reachable(monkeypatch):
    monkeypatch.setattr(ml.socket, "socket", FakeSocket)
    FakeSocket.outcome = ConnectionRefusedError(errno.ECONNREFUSED, "refused")
    _, _, why = ml.tcp_connect("127.0.0.1", 80, 0.5)
    FakeSocket.outcome = None
    assert "answered" in why


def test_real_refused_and_open_on_loopback(open_port, closed_port):
    assert ml.tcp_connect("127.0.0.1", open_port, 1.0)[0] == "open"
    status, ms, _ = ml.tcp_connect("127.0.0.1", closed_port, 1.0)
    assert status == "refused" and ms < (4000 if sys.platform == "win32" else 1000)  # Windows retries the SYN first


def test_a_malformed_address_is_an_error_not_a_crash():
    assert ml.tcp_connect("not an address", 80, 0.2)[0] == "error"


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="relies on Linux accept-queue behaviour")
def test_a_real_timeout_from_a_full_accept_queue():
    """Fill a listener's accept queue: the kernel then drops new SYNs and the client sees silence."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(0)
    port = srv.getsockname()[1]
    held = []
    try:
        for _ in range(4):
            c = socket.socket()
            c.settimeout(0.3)
            with contextlib.suppress(OSError):
                c.connect(("127.0.0.1", port))
            held.append(c)
        status = ml.tcp_connect("127.0.0.1", port, 0.3)[0]
    finally:
        for c in held:
            c.close()
        srv.close()
    assert status == "timeout"


def test_summarise_covers_every_mix():
    s = ml.summarise
    row = lambda *st: [{"status": x} for x in st]  # noqa: E731
    assert s(row("open", "open")) == "ok"
    assert s(row("open", "refused")) == "partial"
    assert s(row("refused", "timeout")) == "refused"
    assert s(row("timeout", "timeout")) == "filtered"
    assert s(row("unreachable_network", "unreachable_host")) == "unreachable"
    assert s(row("timeout", "unreachable_host")) == "error"


def test_resolve_skips_the_resolver_for_ip_literals(monkeypatch):
    monkeypatch.setattr(ml.socket, "getaddrinfo", lambda *a, **k: pytest.fail("resolver was called"))
    assert ml.resolve("192.168.1.5") == (["192.168.1.5"], 0.0, None)
    assert ml.resolve("::1")[0] == ["::1"]


def test_resolve_reports_failure_in_words(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(ml.socket, "getaddrinfo", boom)
    addrs, _, err = ml.resolve("laptop.local")
    assert addrs == [] and err == "Name or service not known"


def test_resolve_gives_up_on_a_stuck_resolver(monkeypatch):
    import time

    monkeypatch.setattr(ml.socket, "getaddrinfo", lambda *a, **k: time.sleep(2))
    t0 = time.perf_counter()
    addrs, _, err = ml.resolve("slow.local", 0.1)
    assert addrs == [] and "within 0.1 s" in err and time.perf_counter() - t0 < 1.0


def test_resolve_deduplicates_answers(monkeypatch):
    answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))] * 3
    monkeypatch.setattr(ml.socket, "getaddrinfo", lambda *a, **k: answer)
    assert ml.resolve("desk.local")[0] == ["10.0.0.5"]


@pytest.mark.parametrize(
    ("median", "p95", "jitter", "grade"),
    [(10.1, 30, 8, "ok"), (10, 30.1, 8, "ok"), (10, 30, 8.1, "ok"), (25, 60, 99, "ok"), (25.1, 60, 1, "laggy"),
     (25, 60.1, 1, "laggy"), (50, 120, 1, "laggy"), (50.1, 120, 1, "poor"), (50, 120.1, 1, "poor")],
)
def test_feel_thresholds_are_inclusive_at_the_stated_numbers(median, p95, jitter, grade):
    assert ml.feel({"median": median, "p95": p95, "jitter": jitter}, 20, 0)["grade"] == grade


def test_feel_calls_more_than_five_percent_loss_poor():
    assert ml.feel({"median": 1, "p95": 2, "jitter": 0}, 50, 3)["grade"] == "poor"
    assert ml.feel({"median": 1, "p95": 2, "jitter": 0}, 100, 5)["grade"] == "good"


def test_sample_rtt_default_budget_is_thirty_seconds():
    ticks = iter(range(0, 10000))
    _, sent, _ = ml.sample_rtt("x", 1, 50, 1.0, connect=lambda *_: ("open", 1.0, ""), clock=lambda: next(ticks),
                               sleep=lambda _: None)
    assert sent == 30  # one reading per second: the check at 30 s passes, 31 s does not


def test_port_and_host_limits_are_exact():
    assert ml.ports_arg("65535") == [65535]
    with pytest.raises(argparse.ArgumentTypeError):
        ml.ports_arg("65536")
    assert ml.host_arg("a" * 253) == "a" * 253
    with pytest.raises(argparse.ArgumentTypeError):
        ml.host_arg("a" * 254)
