import builtins
import errno
import json
import socket
import subprocess
import sys
import time

import pytest

import mesh_local as mlo
from conftest import free_port

MACOS_IFCONFIG = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\toptions=1203<RXCSUM,TXCSUM,TXSTATUS,SW_TIMESTAMP>
\tinet 127.0.0.1 netmask 0xff000000
\tinet6 ::1 prefixlen 128
\tinet6 fe80::1%lo0 prefixlen 64 scopeid 0x1
\tnd6 options=201<PERFORMNUD,DAD>
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tether aa:bb:cc:dd:ee:ff
\tinet6 fe80::1c2b:3d4e:5f60:7182%en0 prefixlen 64 secured scopeid 0xb
\tinet 192.168.1.23 netmask 0xffffff00 broadcast 192.168.1.255
\tnd6 options=201<PERFORMNUD,DAD>
\tmedia: autoselect
\tstatus: active
utun3: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
\tinet 10.8.0.2 --> 10.8.0.2 netmask 0xffffffff
en5: flags=8822<BROADCAST,SMART,SIMPLEX,MULTICAST> mtu 1500
\tinet 10.0.0.9 netmask 0xffff0000 broadcast 10.0.255.255
"""

NET_TOOLS = """eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.1.5  netmask 255.255.255.0  broadcast 192.168.1.255
        inet6 fe80::a00:27ff:fe4e:66a1  prefixlen 64  scopeid 0x20<link>
"""

PS_51 = json.dumps({
    "addresses": [
        {"InterfaceAlias": "Wi-Fi", "IPAddress": "192.168.1.40", "PrefixLength": 24},
        {"InterfaceAlias": "Wi-Fi", "IPAddress": "fe80::abcd:1%12", "PrefixLength": 64},
        {"InterfaceAlias": "Loopback Pseudo-Interface 1", "IPAddress": "127.0.0.1", "PrefixLength": 8},
    ],
    "profiles": [{"InterfaceAlias": "Wi-Fi", "NetworkCategory": 0}],
})


def doc(**over):
    base = {
        "interfaces": [], "interfaces_error": None, "default_route": {"source_address": "10.0.0.5", "interface": "eth0"},
        "windows_profiles": [], "ports": [],
        "name_resolution": {"mdns_ok": True, "mdns_name": "x.local", "hostname_addresses": ["10.0.0.5"]},
    }
    base.update(over)
    return base


def iface(name, kind, *addrs, up=True):
    rows = [{"name": name, "up": up, "address": a, "prefix": p} for a, p in addrs]
    return mlo.group(rows)[0] | {"kind": kind, "up": up}


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("127.0.0.1", "loopback"), ("::1", "loopback"), ("169.254.3.4", "link_local"), ("fe80::1%en0", "link_local"),
        ("192.168.1.5", "private"), ("10.1.2.3", "private"), ("172.16.0.1", "private"), ("172.32.0.1", "public"),
        ("100.64.0.1", "shared"), ("100.127.255.255", "shared"), ("100.128.0.1", "public"), ("8.8.8.8", "public"),
        ("fd12:3456::1", "ula"), ("fc00::1", "ula"), ("2606:4700::1", "public"), ("224.0.0.251", "multicast"),
        ("ff02::fb", "multicast"), ("nonsense", "unknown"),
    ],
)
def test_scope_classification(addr, expected):
    assert mlo.scope(addr) == expected


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("tun0", "vpn"), ("tap0", "vpn"), ("utun3", "vpn"), ("wg0", "vpn"), ("ppp0", "vpn"), ("ipsec0", "vpn"),
        ("OpenVPN TAP-Windows Adapter", "vpn"), ("Corporate VPN", "vpn"), ("zt5u4abcd", "vpn"),
        ("docker0", "virtual"), ("br-1a2b3c", "virtual"), ("veth12ab", "virtual"), ("virbr0", "virtual"),
        ("vboxnet0", "virtual"), ("vEthernet (Default Switch)", "virtual"), ("awdl0", "virtual"),
        ("bridge100", "virtual"), ("Bluetooth Network Connection", "virtual"),
        ("eth0", "physical"), ("en0", "physical"), ("wlan0", "physical"), ("wlp3s0", "physical"),
        ("enp0s31f6", "physical"), ("Wi-Fi", "physical"), ("Ethernet", "physical"), ("Ethernet 2", "physical"),
    ],
)
def test_interface_kind_from_its_name(name, kind):
    assert mlo.kind_of(name, "192.168.1.5") == kind


def test_loopback_beats_the_name():
    assert mlo.kind_of("lo", "127.0.0.1") == "loopback" and mlo.kind_of("tun0", "127.0.0.1") == "loopback"


def test_macos_ifconfig_is_parsed_including_hex_masks_and_point_to_point_tunnels():
    rows = mlo.parse_ifconfig(MACOS_IFCONFIG)
    got = {(r["name"], r["address"]): (r["prefix"], r["up"]) for r in rows}
    assert got[("lo0", "127.0.0.1")] == (8, True)
    assert got[("lo0", "::1")] == (128, True)
    assert got[("lo0", "fe80::1")] == (64, True)
    assert got[("en0", "192.168.1.23")] == (24, True)
    assert got[("en0", "fe80::1c2b:3d4e:5f60:7182")] == (64, True)
    assert got[("utun3", "10.8.0.2")] == (32, True)
    assert got[("en5", "10.0.0.9")] == (16, False)  # no UP or RUNNING flag: down


def test_net_tools_ifconfig_with_dotted_masks_is_parsed_too():
    got = {r["address"]: r["prefix"] for r in mlo.parse_ifconfig(NET_TOOLS)}
    assert got == {"192.168.1.5": 24, "fe80::a00:27ff:fe4e:66a1": 64}


def test_ifconfig_garbage_gives_no_rows_and_no_crash():
    assert mlo.parse_ifconfig("") == [] and mlo.parse_ifconfig("\tinet 1.2.3.4 netmask 0xffffff00\n") == []


def test_powershell_json_is_parsed_with_profiles():
    rows, profiles = mlo.parse_powershell(PS_51)
    assert {(r["name"], r["address"], r["prefix"]) for r in rows} == {
        ("Wi-Fi", "192.168.1.40", 24), ("Wi-Fi", "fe80::abcd:1", 64), ("Loopback Pseudo-Interface 1", "127.0.0.1", 8)}
    assert profiles == [{"interface": "Wi-Fi", "category": "Public"}]


@pytest.mark.parametrize(("raw", "label"), [(0, "Public"), (1, "Private"), (2, "DomainAuthenticated"), ("Private", "Private")])
def test_network_categories_in_both_powershell_styles(raw, label):
    text = json.dumps({"addresses": [], "profiles": [{"InterfaceAlias": "Ethernet", "NetworkCategory": raw}]})
    assert mlo.parse_powershell(text)[1][0]["category"] == label


def test_powershell_single_objects_and_empty_lists_are_tolerated():
    one = {"addresses": {"InterfaceAlias": "Ethernet", "IPAddress": "10.0.0.2", "PrefixLength": "24"}, "profiles": None}
    rows, profiles = mlo.parse_powershell(json.dumps(one))
    assert rows[0]["prefix"] == 24 and profiles == []
    assert mlo.parse_powershell('{"addresses": [], "profiles": []}') == ([], [])


def test_group_adds_subnet_scope_family_and_skips_bad_rows():
    ifs = mlo.group([
        {"name": "eth0", "up": True, "address": "192.168.1.77", "prefix": 24},
        {"name": "eth0", "up": True, "address": "fe80::1", "prefix": 64},
        {"name": "eth0", "up": True, "address": "bogus", "prefix": 24},
        {"name": "lo", "up": True, "address": "127.0.0.1", "prefix": 8},
    ])
    eth0 = ifs[0]
    assert [i["name"] for i in ifs] == ["eth0", "lo"] and len(eth0["addresses"]) == 2
    assert eth0["addresses"][0] == {"family": "IPv4", "address": "192.168.1.77", "prefix": 24,
                                    "subnet": "192.168.1.0/24", "scope": "private"}
    assert eth0["addresses"][1]["family"] == "IPv6" and eth0["addresses"][1]["scope"] == "link_local"


def test_interfaces_dispatch_on_macos_and_windows(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        return subprocess.CompletedProcess(cmd, 0, stdout=MACOS_IFCONFIG if cmd[0] == "ifconfig" else PS_51)

    monkeypatch.setattr(mlo.subprocess, "run", fake_run)
    monkeypatch.setattr(mlo.sys, "platform", "darwin")
    ifs, profiles, err = mlo.interfaces()
    assert err is None and profiles == [] and {i["name"] for i in ifs} >= {"lo0", "en0", "utun3"}
    assert next(i for i in ifs if i["name"] == "utun3")["kind"] == "vpn"
    monkeypatch.setattr(mlo.sys, "platform", "win32")
    ifs, profiles, err = mlo.interfaces()
    assert calls == ["ifconfig", "powershell"] and profiles[0]["category"] == "Public" and err is None


def test_ifconfig_interface_is_up_only_when_up_and_running():
    text = "en5: flags=8822<UP,BROADCAST,SIMPLEX,MULTICAST> mtu 1500\n\tinet 10.1.1.1 netmask 0xffffff00\n"
    assert mlo.parse_ifconfig(text)[0]["up"] is False
    text = "en5: flags=8863<BROADCAST,RUNNING> mtu 1500\n\tinet 10.1.1.1 netmask 0xffffff00\n"
    assert mlo.parse_ifconfig(text)[0]["up"] is False


def test_interfaces_failure_is_reported_not_raised(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("ifconfig")

    monkeypatch.setattr(mlo.subprocess, "run", missing)
    monkeypatch.setattr(mlo.sys, "platform", "darwin")
    ifs, profiles, err = mlo.interfaces()
    assert ifs == [] and profiles == [] and "FileNotFoundError" in err


@pytest.mark.parametrize("platform,out,rc,reason", [
    ("darwin", "", 0, "printed nothing"),
    ("darwin", "lo0: something unexpected\n", 0, "no addresses"),
    ("darwin", "x", 1, "exited with 1"),
    ("win32", "not json", 0, "JSONDecodeError"),
    ("win32", '{"addresses": [], "profiles": []}', 0, "no addresses"),
])
def test_unparseable_os_output_degrades_with_a_reason(monkeypatch, platform, out, rc, reason):
    monkeypatch.setattr(mlo.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, rc, out, "boom"))
    monkeypatch.setattr(mlo.sys, "platform", platform)
    ifs, profiles, err = mlo.interfaces()
    assert ifs == [] and profiles == [] and reason in err
    msg = mlo.analyse(doc(interfaces_error=err), False)[0]["message"]
    assert "not been run on real machines" in msg and "no DHCP lease" not in msg


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads getifaddrs, which is the Linux path")
def test_real_interface_listing_on_linux_includes_loopback_with_its_prefix():
    ifs, _, err = mlo.interfaces()
    lo = next(i for i in ifs if i["kind"] == "loopback")
    assert err is None and any(x["address"] == "127.0.0.1" and x["prefix"] == 8 for x in lo["addresses"])


def test_route_source_asks_for_a_route_without_sending_anything():
    assert mlo.route_source("127.0.0.1") == "127.0.0.1"
    assert mlo.route_source("203.0.113.1") is None or isinstance(mlo.route_source("203.0.113.1"), str)


def test_route_source_is_none_when_there_is_no_route(monkeypatch):
    class NoRoute:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def connect(self, addr):
            raise OSError(errno.ENETUNREACH, "Network is unreachable")

    monkeypatch.setattr(mlo.socket, "socket", NoRoute)
    assert mlo.route_source("203.0.113.1") is None


def test_resolve_failure_and_timeout(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(mlo.socket, "getaddrinfo", boom)
    assert mlo.resolve("x.local", 1)[::2] == ([], "Name or service not known")
    monkeypatch.setattr(mlo.socket, "getaddrinfo", lambda *a, **k: time.sleep(2))
    t0 = time.perf_counter()
    assert "within 0.1 s" in mlo.resolve("x.local", 0.1)[2] and time.perf_counter() - t0 < 1


def test_port_states_free_in_use_and_denied(monkeypatch):
    with socket.socket() as holder:
        holder.bind(("0.0.0.0", 0))
        holder.listen(1)
        assert mlo.port_state(holder.getsockname()[1]) == "in_use"
    assert mlo.port_state(free_port()) == "free"

    class Denied:
        def __init__(self, code):
            self.code = code

        def __call__(self, *a):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def bind(self, addr):
            raise OSError(self.code, "x")

    monkeypatch.setattr(mlo.socket, "socket", Denied(errno.EACCES))
    assert mlo.port_state(80) == "no_access"
    monkeypatch.setattr(mlo.socket, "socket", Denied(errno.EIO))
    assert mlo.port_state(80) == "error"


def codes(findings):
    return {f["code"]: f["level"] for f in findings}


def test_a_healthy_machine_has_no_warnings():
    d = doc(interfaces=[iface("eth0", "physical", ("192.168.1.5", 24))])
    assert not [f for f in mlo.analyse(d, False) if f["level"] == "warn"]


def test_only_link_local_means_no_dhcp_lease():
    d = doc(interfaces=[iface("eth0", "physical", ("169.254.8.8", 16))])
    assert codes(mlo.analyse(d, False))["no_address"] == "warn"


def test_a_down_interface_does_not_count_as_an_address():
    d = doc(interfaces=[iface("eth0", "physical", ("192.168.1.5", 24), up=False)])
    assert "no_address" in codes(mlo.analyse(d, False))


def test_no_default_route_is_a_warning():
    d = doc(interfaces=[iface("eth0", "physical", ("192.168.1.5", 24))], default_route=None)
    assert codes(mlo.analyse(d, False))["no_default_route"] == "warn"


def test_a_default_route_through_a_vpn_is_a_warning():
    d = doc(interfaces=[iface("wg0", "vpn", ("10.6.0.2", 32)), iface("eth0", "physical", ("192.168.1.5", 24))],
            default_route={"source_address": "10.6.0.2", "interface": "wg0"})
    found = codes(mlo.analyse(d, False))
    assert found["vpn_default_route"] == "warn" and "vpn_present" not in found


def test_a_vpn_that_is_not_the_default_route_is_information():
    d = doc(interfaces=[iface("wg0", "vpn", ("10.6.0.2", 32)), iface("eth0", "physical", ("192.168.1.5", 24))])
    assert codes(mlo.analyse(d, False))["vpn_present"] == "info"


def test_a_tunnel_with_only_link_local_addresses_is_not_reported_as_a_vpn():
    d = doc(interfaces=[iface("utun0", "vpn", ("fe80::1", 64)), iface("en0", "physical", ("192.168.1.5", 24))])
    assert "vpn_present" not in codes(mlo.analyse(d, False))


def test_shared_address_space_and_many_subnets_are_information():
    d = doc(interfaces=[iface("tun0", "vpn", ("100.64.1.2", 10)), iface("eth0", "physical", ("192.168.1.5", 24)),
                        iface("docker0", "virtual", ("172.17.0.1", 16))])
    found = codes(mlo.analyse(d, False))
    assert found["shared_address_space"] == "info" and found["many_subnets"] == "info"


def test_mdns_failure_and_loopback_hostname_are_information_only():
    d = doc(interfaces=[iface("eth0", "physical", ("192.168.1.5", 24))],
            name_resolution={"mdns_ok": False, "mdns_name": "box.local", "hostname_addresses": ["127.0.1.1"]})
    found = codes(mlo.analyse(d, False))
    assert found["mdns_unresolved"] == "info" and found["hostname_is_loopback"] == "info"


def test_a_public_windows_profile_is_a_warning_and_a_private_one_is_not():
    d = doc(interfaces=[iface("Wi-Fi", "physical", ("192.168.1.5", 24))],
            windows_profiles=[{"interface": "Wi-Fi", "category": "Public"}])
    assert codes(mlo.analyse(d, False))["windows_public_profile"] == "warn"
    d["windows_profiles"][0]["category"] = "Private"
    assert "windows_public_profile" not in codes(mlo.analyse(d, False))


def test_ports_in_use_only_matter_when_you_asked_about_them():
    d = doc(interfaces=[iface("eth0", "physical", ("192.168.1.5", 24))], ports=[{"port": 445, "state": "in_use"}])
    assert "port_not_free" not in codes(mlo.analyse(d, False))
    assert codes(mlo.analyse(d, True))["port_not_free"] == "warn"


def test_missing_interface_data_asks_for_pasted_output():
    d = doc(interfaces_error="FileNotFoundError: ifconfig")
    assert "ipconfig or ifconfig" in mlo.analyse(d, False)[0]["message"]


def test_collect_assembles_the_document(monkeypatch):
    monkeypatch.setattr(mlo, "interfaces", lambda: ([iface("eth0", "physical", ("192.168.1.5", 24))], [], None))
    monkeypatch.setattr(mlo, "route_source", lambda ip: "192.168.1.5")
    monkeypatch.setattr(mlo, "resolve", lambda host, t: (["192.168.1.5"], 3.0, None))
    monkeypatch.setattr(mlo, "port_state", lambda p: "free")
    monkeypatch.setattr(mlo.socket, "gethostname", lambda: "laptop.home")
    d = mlo.collect("mine", [8080, 9000])
    assert d["label"] == "mine" and d["hostname"] == "laptop.home" and d["kind"] == "local"
    assert d["default_route"] == {"source_address": "192.168.1.5", "interface": "eth0", "prefix": 24, "family": "IPv4"}
    assert d["name_resolution"]["mdns_name"] == "laptop.local" and d["name_resolution"]["mdns_ok"] is True
    assert [p["port"] for p in d["ports"]] == [8080, 9000] and d["findings"] == []


def test_real_run_prints_valid_json_with_the_documented_keys(run_json):
    code, d, _ = run_json(mlo, "--label", "here")
    assert code in (0, 1) and d["tool"] == "mesh_local" and d["label"] == "here"
    for key in ("hostname", "os", "interfaces", "default_route", "name_resolution", "ports", "findings", "windows_profiles"):
        assert key in d
    assert [p["port"] for p in d["ports"]] == list(mlo.LOCAL_PORTS)


def test_a_port_in_use_is_reported_when_asked_about(run_json):
    with socket.socket() as holder:
        holder.bind(("0.0.0.0", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        code, d, _ = run_json(mlo, "--ports", str(port))
    assert d["ports"] == [{"port": port, "service": None, "state": "in_use"}]
    assert code == 1 and "port_not_free" in codes(d["findings"])


def test_text_output_is_readable(run):
    code, out, _ = run(mlo)
    assert code in (0, 1) and "default route:" in out and "ports:" in out and "findings" in out


def test_it_opens_none_of_your_files(run_json, monkeypatch):
    real_open = builtins.open

    def refuse(file, *a, **k):
        if str(file).startswith(("/System/", "/Library/", "/usr/", "/etc/", "/proc/", "/sys/")):  # the OS's own files
            return real_open(file, *a, **k)
        raise AssertionError(f"tried to read {file}")

    monkeypatch.setattr(builtins, "open", refuse)
    code, d, _ = run_json(mlo)
    assert d["kind"] == "local"


@pytest.mark.parametrize("argv", [["--ports", "0"], ["--ports", "80,x"], ["--ports", "70000"], ["--bogus"], ["extra"]])
def test_bad_arguments_exit_2(run, argv):
    code, out, err = run(mlo, *argv)
    assert code == 2 and out == "" and "Traceback" not in err
