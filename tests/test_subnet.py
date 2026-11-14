import pytest

import mesh_link as ml


def chk(local, prefix, peer, peer_prefix=None):
    return ml.subnet_check(local, prefix, peer, peer_prefix)


@pytest.mark.parametrize(
    ("local", "prefix", "peer", "same"),
    [
        ("192.168.1.10", 24, "192.168.1.200", True),
        ("192.168.1.10", 24, "192.168.2.10", False),
        ("192.168.1.10", 16, "192.168.200.1", True),
        ("10.0.0.10", 25, "10.0.0.100", True),
        ("10.0.0.10", 25, "10.0.0.200", False),
        ("10.0.0.5", 30, "10.0.0.6", True),
        ("10.0.0.5", 30, "10.0.0.8", False),
        ("10.0.0.0", 31, "10.0.0.1", True),
        ("10.0.0.1", 31, "10.0.0.2", False),
        ("10.0.0.1", 31, "10.0.0.0", True),
        ("10.0.0.1", 32, "10.0.0.1", True),
        ("10.0.0.1", 32, "10.0.0.2", False),
        ("10.0.0.1", 8, "10.255.255.254", True),
        ("10.0.0.1", 8, "11.0.0.1", False),
        ("10.0.0.1", 0, "203.0.113.9", True),
        ("2001:db8::1", 64, "2001:db8::abcd", True),
        ("2001:db8::1", 64, "2001:db8:0:1::1", False),
        ("2001:db8::1", 48, "2001:db8:0:1::1", True),
        ("2001:db8::1", 128, "2001:db8::1", True),
        ("2001:db8::1", 128, "2001:db8::2", False),
        ("2001:db8::2", 127, "2001:db8::3", True),
        ("2001:db8::2", 127, "2001:db8::4", False),
        ("fd00::1", 64, "fd00::2", True),
        ("fd00::1", 64, "fd00:0:0:1::2", False),
    ],
)
def test_subnet_membership(local, prefix, peer, same):
    assert chk(local, prefix, peer)["same"] is same


@pytest.mark.parametrize("prefix", range(0, 33))
def test_every_ipv4_prefix_length_agrees_with_plain_bit_arithmetic(prefix):
    a, b = "172.16.5.77", "172.16.133.4"
    ia, ib = (172 << 24) | (16 << 16) | (5 << 8) | 77, (172 << 24) | (16 << 16) | (133 << 8) | 4
    expected = prefix == 0 or (ia >> (32 - prefix)) == (ib >> (32 - prefix))
    assert chk(a, prefix, b)["same"] is expected


@pytest.mark.parametrize("prefix", [0, 1, 7, 8, 16, 31, 32, 48, 56, 63, 64, 65, 100, 127, 128])
def test_every_ipv6_prefix_length_agrees_with_plain_bit_arithmetic(prefix):
    a, b = "2001:db8:aaaa:bbbb::1", "2001:db8:aaaa:bbbc::1"
    ia = int.from_bytes(bytes.fromhex("20010db8aaaabbbb0000000000000001"), "big")
    ib = int.from_bytes(bytes.fromhex("20010db8aaaabbbc0000000000000001"), "big")
    expected = prefix == 0 or (ia >> (128 - prefix)) == (ib >> (128 - prefix))
    assert chk(a, prefix, b)["same"] is expected


def test_the_network_is_reported():
    assert chk("192.168.1.77", 24, "192.168.1.2")["local_net"] == "192.168.1.0/24"
    assert chk("2001:db8::7", 64, "2001:db8::8")["local_net"] == "2001:db8::/64"


def test_loopback_is_the_same_machine():
    out = chk("127.0.0.1", 8, "127.0.0.1")
    assert out["same"] is True and "same machine" in out["note"]
    assert chk("::1", 128, "::1")["same"] is True


def test_link_local_cannot_be_judged_by_prefix():
    assert chk("169.254.10.1", 16, "169.254.10.2")["same"] is None
    assert chk("fe80::1", 64, "fe80::2")["same"] is None
    assert chk("192.168.1.5", 24, "169.254.1.1")["same"] is None


def test_scope_ids_on_ipv6_addresses_are_ignored():
    assert chk("2001:db8::1%eth0", 64, "2001:db8::2%eth0")["same"] is True


def test_mixed_families_cannot_be_compared():
    out = chk("192.168.1.5", 24, "2001:db8::1")
    assert out["same"] is None and "IPv4" in out["note"]


def test_unknown_prefix_asks_for_it():
    out = chk("192.168.1.5", None, "192.168.1.9")
    assert out["same"] is None and "--local-prefix" in out["note"]


@pytest.mark.parametrize(("addr", "prefix"), [("10.0.0.1", 33), ("10.0.0.1", -1), ("2001:db8::1", 129)])
def test_impossible_prefix_lengths_are_rejected(addr, prefix):
    peer = "10.0.0.2" if "." in addr else "2001:db8::2"
    assert chk(addr, prefix, peer)["same"] is None


@pytest.mark.parametrize(("local", "peer"), [(None, "10.0.0.1"), ("", "10.0.0.1"), ("10.0.0.1", "not-an-ip")])
def test_bad_addresses_give_no_verdict(local, peer):
    assert chk(local, 24, peer)["same"] is None


def test_disagreeing_prefixes_are_called_out():
    out = chk("10.0.0.5", 8, "10.200.0.1", 24)
    assert out["same"] is False and "disagree" in out["note"]
    assert chk("10.0.0.5", 24, "10.0.0.9", 24)["same"] is True
