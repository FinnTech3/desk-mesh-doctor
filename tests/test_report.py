import io
import json

import pytest

import mesh_report as mr


def local(label, *ifaces, findings=(), hostname=None):
    """A minimal mesh_local document. Each iface is (name, kind, [(address, prefix), ...])."""
    out = []
    for name, kind, addrs in ifaces:
        items = []
        for addr, prefix in addrs:
            import ipaddress

            net = str(ipaddress.ip_network(f"{addr}/{prefix}", strict=False))
            items.append({"family": "IPv6" if ":" in addr else "IPv4", "address": addr, "prefix": prefix, "subnet": net,
                          "scope": "loopback" if addr.startswith("127.") else "private"})
        out.append({"name": name, "up": True, "kind": kind, "addresses": items})
    return {"tool": "mesh_local", "kind": "local", "label": label, "hostname": hostname or label, "os": "Test OS 1",
            "interfaces": out, "findings": list(findings)}


def lan(label, last, prefix=24, net="192.168.1"):
    return local(label, ("eth0", "physical", [(f"{net}.{last}", prefix)]), ("lo", "loopback", [("127.0.0.1", 8)]))


def peer(src, host, status, addresses=(), ports=None):
    return {"tool": "mesh_link", "kind": "peer", "from": {"label": src, "hostname": src},
            "target": {"host": host, "addresses": list(addresses) or [host]},
            "summary": {"status": status, "open": [], "explicit_ports": True}, "ports": ports or []}


def build(*docs):
    return mr.build(list(docs))


def pair_levels(rep):
    return [(f["level"]) for p in rep["pairs"] for f in p["findings"]]


def text_of(rep):
    return " ".join(f["message"] for p in rep["pairs"] for f in p["findings"])


def test_both_directions_ok_is_clean():
    rep = build(lan("laptop", 10), lan("desk", 20), peer("laptop", "192.168.1.20", "ok"), peer("desk", "192.168.1.10", "ok"))
    assert rep["matrix"] == {"laptop": {"laptop": "-", "desk": "ok"}, "desk": {"laptop": "ok", "desk": "-"}}
    assert rep["problem"] is False and rep["pairs"][0]["same_subnet"] is True
    assert rep["pairs"][0]["subnet"] == "192.168.1.0/24" and rep["pairs"][0]["findings"] == []


def test_a_peer_target_is_matched_to_a_device_by_its_address():
    rep = build(lan("laptop", 10), lan("desk", 20), peer("laptop", "192.168.1.20", "ok"))
    assert rep["matrix"]["laptop"]["desk"] == "ok" and set(rep["matrix"]) == {"laptop", "desk"}


def test_a_peer_target_is_matched_by_name_ignoring_dot_local_and_case():
    rep = build(lan("laptop", 10), lan("Desk", 20), peer("laptop", "desk.local", "ok", addresses=["10.9.9.9"]))
    assert rep["matrix"]["laptop"]["Desk"] == "ok"


def test_asymmetry_blames_the_target_of_the_failing_direction():
    rep = build(lan("laptop", 10), lan("desk", 20), peer("laptop", "192.168.1.20", "filtered"),
                peer("desk", "192.168.1.10", "ok"))
    assert rep["matrix"]["laptop"]["desk"] == "filtered" and rep["matrix"]["desk"]["laptop"] == "ok"
    msg = rep["pairs"][0]["findings"][0]["message"]
    assert rep["problem"] is True and msg.startswith("laptop->desk is filtered") and "points at desk" in msg


def test_both_filtered_on_one_subnet_points_at_the_router_first():
    rep = build(lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "filtered"), peer("b", "192.168.1.10", "filtered"))
    assert "client or AP isolation" in text_of(rep) and "router first" in text_of(rep)


def test_both_filtered_on_different_subnets_points_at_routing():
    rep = build(lan("a", 10), lan("b", 20, net="192.168.2"), peer("a", "192.168.2.20", "filtered"),
                peer("b", "192.168.1.10", "filtered"))
    assert "Different subnets" in text_of(rep) and rep["pairs"][0]["same_subnet"] is False


def test_both_filtered_with_no_local_data_asks_for_it():
    rep = build(peer("a", "b", "filtered", ["10.0.0.2"]), peer("b", "a", "filtered", ["10.0.0.1"]))
    assert "Run mesh_local.py" in text_of(rep) and rep["pairs"][0]["same_subnet"] is None


def test_both_refused_means_the_path_works_and_nothing_listens():
    rep = build(lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "refused"), peer("b", "192.168.1.10", "refused"))
    assert "battery optimiser" in text_of(rep) and rep["problem"] is True


def test_one_way_refused_with_the_other_ok_is_only_information():
    rep = build(lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "ok"), peer("b", "192.168.1.10", "refused"))
    assert pair_levels(rep) == ["info"] and rep["problem"] is False and "only one device listens" in text_of(rep)


def test_partial_is_a_warning():
    rep = build(lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "partial"), peer("b", "192.168.1.10", "ok"))
    assert pair_levels(rep) == ["warn"] and rep["problem"] is True


def test_unresolved_and_unreachable_are_explained():
    rep = build(lan("a", 10), lan("b", 20), peer("a", "b.local", "unresolved", ["192.168.1.20"]),
                peer("b", "a.local", "unresolved", ["192.168.1.10"]))
    assert "does not resolve from either side" in text_of(rep)
    rep = build(lan("a", 10), lan("b", 20, net="10.5.5"), peer("a", "10.5.5.20", "unreachable"),
                peer("b", "192.168.1.10", "unreachable"))
    assert "no route either way" in text_of(rep)
    rep = build(lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "unresolved"), peer("b", "192.168.1.10", "ok"))
    assert "did not resolve from a" in text_of(rep)


def test_a_pair_with_no_tests_says_what_to_run():
    rep = build(lan("a", 10), lan("b", 20))
    assert rep["matrix"]["a"]["b"] == "untested" and "no peer test yet" in text_of(rep)
    assert rep["problem"] is False


def test_one_direction_tested_asks_for_the_other():
    rep = build(lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "ok"))
    assert "b->a not tested" in text_of(rep) and rep["matrix"]["b"]["a"] == "untested"


def test_ok_across_subnets_explains_that_discovery_will_not_cross():
    rep = build(lan("a", 10), lan("b", 20, net="192.168.2"), peer("a", "192.168.2.20", "ok"), peer("b", "192.168.1.10", "ok"))
    assert "different subnets" in text_of(rep) and "broadcast or multicast" in text_of(rep) and rep["problem"] is False


def test_a_listener_that_saw_a_device_proves_that_direction():
    listen = {"tool": "mesh_link", "kind": "listen", "label": "desk", "hostname": "desk", "unique_sources": ["192.168.1.10"]}
    rep = build(lan("laptop", 10), lan("desk", 20), listen)
    assert rep["matrix"]["laptop"]["desk"] == "ok" and rep["matrix"]["desk"]["laptop"] == "untested"


def test_a_listener_does_not_override_a_direct_test():
    listen = {"tool": "mesh_link", "kind": "listen", "label": "desk", "hostname": "desk", "unique_sources": ["192.168.1.10"]}
    rep = build(lan("laptop", 10), lan("desk", 20), peer("laptop", "192.168.1.20", "filtered"), listen)
    assert rep["matrix"]["laptop"]["desk"] == "filtered"


def test_a_device_with_no_local_json_still_appears():
    rep = build(lan("laptop", 10), peer("laptop", "phone", "filtered", ["192.168.1.55"]))
    assert rep["matrix"]["laptop"]["phone"] == "filtered"
    assert [d["profiled"] for d in rep["devices"]] == [True, False]


def test_device_warnings_are_surfaced_and_make_the_report_a_problem():
    warn = {"level": "warn", "code": "windows_public_profile", "message": "Ethernet is on the Public network profile"}
    noise = {"level": "info", "code": "mdns_unresolved", "message": "x"}
    rep = build(lan("a", 10), local("b", ("Ethernet", "physical", [("192.168.1.20", 24)]), findings=[warn, noise]))
    assert rep["problem"] is True and rep["devices"][1]["findings"] == [warn]


def test_virtual_bridges_do_not_fake_a_shared_subnet():
    a = local("a", ("eth0", "physical", [("192.168.1.10", 24)]), ("docker0", "virtual", [("172.17.0.1", 16)]))
    b = local("b", ("eth0", "physical", [("192.168.2.10", 24)]), ("docker0", "virtual", [("172.17.0.1", 16)]))
    assert mr.same_subnet(a, b) == (False, None)


def test_loopback_and_down_interfaces_are_ignored_for_subnets():
    a, b = lan("a", 10), lan("b", 20)
    assert mr.same_subnet(a, b) == (True, "192.168.1.0/24")
    b["interfaces"][0]["up"] = False
    assert mr.same_subnet(a, b) == (None, None)


def test_a_vpn_interface_counts_for_subnets():
    a = local("a", ("wg0", "vpn", [("10.6.0.2", 24)]))
    b = local("b", ("wg0", "vpn", [("10.6.0.3", 24)]))
    assert mr.same_subnet(a, b) == (True, "10.6.0.0/24")


def test_both_addresses_must_fall_in_each_others_network():
    a = local("a", ("eth0", "physical", [("10.0.0.5", 8)]))
    b = local("b", ("eth0", "physical", [("10.200.0.1", 24)]))
    assert mr.same_subnet(a, b) == (False, None)


def test_ipv6_subnets_are_compared_within_the_same_family():
    a = local("a", ("eth0", "physical", [("fd00::5", 64)]))
    b = local("b", ("eth0", "physical", [("fd00::9", 64)]))
    assert mr.same_subnet(a, b) == (True, "fd00::/64")
    c = local("c", ("eth0", "physical", [("192.168.1.5", 24)]))
    assert mr.same_subnet(a, c) == (False, None)


def test_a_retest_replaces_the_earlier_result():
    rep = build(lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "filtered"), peer("b", "192.168.1.10", "ok"),
                peer("a", "192.168.1.20", "ok"))
    assert rep["matrix"]["a"]["b"] == "ok" and rep["problem"] is False


def test_documents_that_are_not_mesh_output_are_counted_and_ignored():
    rep = build(lan("a", 10), {"hello": "world"}, {"tool": "other", "kind": "local"}, "text", 5)
    assert rep["ignored_documents"] == 4 and len(rep["devices"]) == 1


def test_at_most_twelve_devices_are_shown():
    rep = build(*[lan(f"d{i}", i + 1) for i in range(20)])
    assert len(rep["matrix"]) == 12 and len(rep["devices"]) == 12


def test_read_docs_handles_streams_arrays_and_whitespace():
    stream = json.dumps({"a": 1}) + "\n\n  " + json.dumps([{"b": 2}, {"c": 3}]) + "\n" + json.dumps({"d": 4})
    assert mr.read_docs(stream) == [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}]
    assert mr.read_docs("") == [] and mr.read_docs("  \n ") == []


def test_read_docs_rejects_broken_json():
    with pytest.raises(ValueError):
        mr.read_docs('{"a": 1} {"b": ')


def stdin(monkeypatch, text):
    monkeypatch.setattr(mr.sys, "stdin", io.StringIO(text))


def test_main_text_report_has_a_markdown_matrix(run, monkeypatch):
    docs = [lan("laptop", 10), lan("desk", 20), peer("laptop", "192.168.1.20", "filtered"), peer("desk", "192.168.1.10", "ok")]
    stdin(monkeypatch, "\n".join(json.dumps(d) for d in docs))
    code, out, _ = run(mr)
    assert code == 1
    assert out.splitlines()[:4] == ["| from \\ to | laptop | desk |", "|---|---|---|", "| laptop | - | filtered |",
                                    "| desk | ok | - |"]
    assert "laptop <-> desk: same subnet (192.168.1.0/24)" in out


def test_main_json_report_and_exit_code_zero(run_json, monkeypatch):
    docs = [lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "ok"), peer("b", "192.168.1.10", "ok")]
    stdin(monkeypatch, json.dumps(docs))
    code, rep, _ = run_json(mr)
    assert code == 0 and rep["kind"] == "report" and rep["problem"] is False and rep["tool"] == "mesh_report"


@pytest.mark.parametrize(
    "text",
    ["", "not json", '{"tool": "mesh_local"', "[1, 2, 3]", '{"hello": 1}', "[" * 200000, '{"tool":"mesh_link","kind":"peer"}',
     '{"tool":"mesh_link","kind":"peer","from":5,"target":{}}', "x" * 2_100_000],
)
def test_bad_input_exits_2_with_a_message(run, monkeypatch, text):
    stdin(monkeypatch, text)
    code, out, err = run(mr)
    assert code == 2 and out == "" and err.startswith("error:") and "Traceback" not in err


def test_the_report_needs_no_network_and_no_files():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(mr.__file__).read_text())
    imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)}
    assert "socket" not in imported and "subprocess" not in imported
    assert "open(" not in Path(mr.__file__).read_text()


def test_input_limit_is_exact(run, monkeypatch):
    doc = json.dumps([lan("a", 10), lan("b", 20), peer("a", "192.168.1.20", "ok"), peer("b", "192.168.1.10", "ok")])
    stdin(monkeypatch, doc + " " * (2_000_000 - len(doc)))
    assert run(mr)[0] == 0
    stdin(monkeypatch, doc + " " * (2_000_001 - len(doc)))
    code, out, err = run(mr)
    assert code == 2 and "2,000,000" in err
