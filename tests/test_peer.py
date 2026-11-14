import socket

import pytest

import mesh_link as ml


def listed(doc):
    return {p["port"]: p["status"] for p in doc["ports"]}


def test_open_and_refused_ports_on_loopback(run_json, open_port, closed_port):
    code, doc, _ = run_json(ml, "peer", "127.0.0.1", "--ports", f"{open_port},{closed_port}", "--samples", "3")
    assert listed(doc) == {open_port: "open", closed_port: "refused"}
    assert doc["summary"]["status"] == "partial" and doc["summary"]["open"] == [open_port]
    assert code == 1
    assert [f["code"] for f in doc["findings"]] == ["port_refused"]


def test_all_requested_ports_open_is_clean(run_json, open_port):
    code, doc, _ = run_json(ml, "peer", "127.0.0.1", "--ports", str(open_port), "--samples", "5")
    assert code == 0 and doc["findings"] == [] and doc["summary"]["status"] == "ok"
    lt = doc["latency"]
    assert lt["port"] == open_port and lt["answered"] == lt["sent"] == 5 and lt["lost"] == 0
    assert lt["min"] <= lt["median"] <= lt["p95"] <= lt["max"]
    assert doc["feel"]["grade"] in {"good", "ok", "laggy", "poor"}


def test_a_requested_port_that_refuses_is_a_problem_but_still_measures_latency(run_json, closed_port):
    code, doc, _ = run_json(ml, "peer", "127.0.0.1", "--ports", str(closed_port), "--samples", "4")
    assert code == 1 and doc["summary"]["status"] == "refused"
    assert doc["findings"][0]["level"] == "problem" and "battery optimiser" in doc["findings"][0]["message"]
    assert doc["latency"]["answered"] == 4


def test_default_ports_that_all_refuse_are_information_not_a_fault(run_json, monkeypatch):
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("refused", 0.4, "x"))
    code, doc, _ = run_json(ml, "peer", "127.0.0.1", "--samples", "2")
    assert code == 0 and [f["level"] for f in doc["findings"]] == ["info"]
    assert [p["port"] for p in doc["ports"]] == list(ml.PEER_PORTS)


def test_every_port_timing_out_is_filtered(run_json, monkeypatch):
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("timeout", 1000.0, "no reply"))
    code, doc, _ = run_json(ml, "peer", "192.168.1.50", "--ports", "7001,7002")
    assert code == 1 and doc["summary"]["status"] == "filtered"
    assert doc["latency"] is None and doc["feel"] is None
    assert [f["code"] for f in doc["findings"]] == ["filtered"]
    assert "client isolation" in doc["findings"][0]["message"]


def test_no_route_is_reported_as_unreachable(run_json, monkeypatch):
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("unreachable_network", 0.1, "no route"))
    code, doc, _ = run_json(ml, "peer", "10.99.0.1", "--ports", "7001")
    assert code == 1 and doc["summary"]["status"] == "unreachable"
    assert "No route" in doc["findings"][0]["message"]


def test_an_unresolvable_name_stops_early_and_says_how_to_separate_the_cause(run_json, monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(ml.socket, "getaddrinfo", boom)
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: pytest.fail("must not connect without an address"))
    code, doc, _ = run_json(ml, "peer", "desk.example")
    assert code == 1 and doc["summary"]["status"] == "unresolved" and doc["ports"] == []
    msg = doc["findings"][0]["message"]
    assert "IP address" in msg and "multicast" not in msg


def test_a_dot_local_name_gets_the_multicast_hint(run_json, monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(ml.socket, "getaddrinfo", boom)
    _, doc, _ = run_json(ml, "peer", "Desk.LOCAL")
    assert "multicast DNS" in doc["findings"][0]["message"]


def test_a_name_that_resolves_is_used(run_json, monkeypatch, open_port):
    real = socket.getaddrinfo

    def fake(host, *a, **k):
        return real("127.0.0.1", *a, **k) if host == "desk.example" else real(host, *a, **k)

    monkeypatch.setattr(ml.socket, "getaddrinfo", fake)
    code, doc, _ = run_json(ml, "peer", "desk.example", "--ports", str(open_port), "--samples", "2")
    assert code == 0 and doc["target"]["addresses"] == ["127.0.0.1"] and doc["target"]["host"] == "desk.example"


def test_different_subnets_are_flagged_and_discovery_is_explained(run_json, monkeypatch):
    monkeypatch.setattr(ml, "source_address", lambda ip: "192.168.1.10")
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("open", 2.0, ""))
    code, doc, _ = run_json(ml, "peer", "192.168.2.20", "--ports", "7001", "--local-prefix", "24", "--samples", "2")
    assert doc["subnet"]["same"] is False and doc["subnet"]["local_net"] == "192.168.1.0/24"
    assert code == 0 and doc["findings"][0]["level"] == "info" and "IP address" in doc["findings"][0]["message"]


def test_different_subnets_and_silence_is_a_warning_on_top_of_the_problem(run_json, monkeypatch):
    monkeypatch.setattr(ml, "source_address", lambda ip: "192.168.1.10")
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("timeout", 1000.0, "x"))
    _, doc, _ = run_json(ml, "peer", "192.168.2.20", "--ports", "7001", "--local-prefix", "24")
    assert {f["code"]: f["level"] for f in doc["findings"]} == {"filtered": "problem", "different_subnet": "warn"}


def test_same_subnet_when_both_prefixes_are_given(run_json, monkeypatch):
    monkeypatch.setattr(ml, "source_address", lambda ip: "10.0.0.5")
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("open", 1.0, ""))
    _, doc, _ = run_json(ml, "peer", "10.0.0.6", "--ports", "7001", "--local-prefix", "30", "--peer-prefix", "30")
    assert doc["subnet"]["same"] is True


def test_missing_local_prefix_is_flagged_in_the_output(run_json, monkeypatch):
    monkeypatch.setattr(ml, "source_address", lambda ip: "10.0.0.5")
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("open", 1.0, ""))
    _, doc, _ = run_json(ml, "peer", "10.0.0.9", "--ports", "7001")
    assert doc["subnet"]["same"] is None and "--local-prefix" in doc["subnet"]["note"]


def test_a_slow_link_raises_a_latency_warning(run_json, monkeypatch):
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("open", 80.0, ""))
    monkeypatch.setattr(ml.time, "sleep", lambda _: None)
    code, doc, _ = run_json(ml, "peer", "10.0.0.9", "--ports", "7001", "--samples", "5")
    assert code == 1 and doc["feel"]["grade"] == "poor" and doc["findings"][-1]["code"] == "latency"


def test_lossy_samples_are_counted(run_json, monkeypatch):
    answers = iter([("open", 2.0, "")] + [("open", 2.0, ""), ("timeout", 1000.0, "x")] * 10)
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: next(answers))
    monkeypatch.setattr(ml.time, "sleep", lambda _: None)
    _, doc, _ = run_json(ml, "peer", "10.0.0.9", "--ports", "7001", "--samples", "10")
    assert doc["latency"]["lost"] == 5 and doc["latency"]["answered"] == 5 and doc["feel"]["grade"] == "poor"


def test_the_label_travels_in_the_output(run_json, open_port):
    _, doc, _ = run_json(ml, "peer", "127.0.0.1", "--ports", str(open_port), "--samples", "1", "--label", "laptop")
    assert doc["from"]["label"] == "laptop" and doc["tool"] == "mesh_link" and doc["kind"] == "peer"


def test_text_output_is_readable(run, open_port, closed_port):
    code, out, _ = run(ml, "peer", "127.0.0.1", "--ports", f"{open_port},{closed_port}", "--samples", "2")
    assert code == 1 and f"port {open_port}" in out and "refused" in out and "latency on port" in out
    assert "findings:" in out and "Traceback" not in out


def test_ipv6_loopback(run_json):
    if not socket.has_ipv6:
        pytest.skip("no IPv6")
    try:
        srv = socket.socket(socket.AF_INET6)
        srv.bind(("::1", 0))
        srv.listen(4)
    except OSError:
        pytest.skip("no IPv6 loopback")
    with srv:
        port = srv.getsockname()[1]
        code, doc, _ = run_json(ml, "peer", "::1", "--ports", str(port), "--samples", "2")
    assert code == 0 and doc["subnet"]["same"] is True


def test_duplicate_ports_are_tested_once(run_json, monkeypatch):
    monkeypatch.setattr(ml, "tcp_connect", lambda *a, **k: ("refused", 1.0, "x"))
    _, doc, _ = run_json(ml, "peer", "127.0.0.1", "--ports", "7001,7001,7002", "--samples", "1")
    assert [p["port"] for p in doc["ports"]] == [7001, 7002]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["peer"],
        ["peer", ""],
        ["peer", "a b"],
        ["peer", "host;rm"],
        ["peer", "$(id)"],
        ["peer", "x" * 300],
        ["peer", "10.0.0.1", "--ports", "0"],
        ["peer", "10.0.0.1", "--ports", "70000"],
        ["peer", "10.0.0.1", "--ports", "22,abc"],
        ["peer", "10.0.0.1", "--ports", ""],
        ["peer", "10.0.0.1", "--ports", ",".join(str(p) for p in range(1, 34))],
        ["peer", "10.0.0.1", "--samples", "0"],
        ["peer", "10.0.0.1", "--samples", "201"],
        ["peer", "10.0.0.1", "--samples", "x"],
        ["peer", "10.0.0.1", "--timeout", "0"],
        ["peer", "10.0.0.1", "--timeout", "11"],
        ["peer", "10.0.0.1", "--local-prefix", "129"],
        ["peer", "10.0.0.1", "--bogus"],
        ["bogus"],
        ["listen"],
        ["listen", "0"],
        ["listen", "65536"],
        ["listen", "abc"],
        ["listen", "8080", "--seconds", "0"],
        ["listen", "8080", "--seconds", "601"],
    ],
)
def test_bad_arguments_exit_2_with_a_message_and_no_traceback(run, argv):
    code, out, err = run(ml, *argv)
    assert code == 2 and out == "" and err and "Traceback" not in err


def test_the_help_text_works(run):
    code, out, _ = run(ml, "peer", "--help")
    assert code == 0 and "--ports" in out
