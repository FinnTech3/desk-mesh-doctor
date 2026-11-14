#!/usr/bin/env python3
"""mesh_local.py - this machine's network view, for working out why devices will not connect.

Prints the hostname, interfaces with IPv4/IPv6 addresses and prefix lengths, the default route, VPN-looking and
virtual interfaces, whether .local names resolve, and which TCP ports this machine can bind. Python 3.10+,
standard library only. It sends no traffic to other devices, reads no local files and writes none; the only
side effects are a brief bind to each port you ask about and the read-only OS tools named in SKILL.md.

Usage: python3 mesh_local.py [--ports 80,5353] [--label laptop] [--json]
Exit codes: 0 nothing wrong found, 1 findings, 2 bad input.
"""

from __future__ import annotations

import argparse
import errno
import ipaddress
import json
import platform
import re
import socket
import subprocess
import sys
import threading
import time

VERSION = "1.0.0"
LOCAL_PORTS = (80, 443, 445, 3389, 5900, 8080)
PORT_NAMES = {22: "SSH", 53: "DNS", 80: "HTTP", 123: "NTP", 443: "HTTPS", 445: "SMB", 548: "AFP", 631: "IPP",
              1900: "SSDP", 3389: "RDP", 5353: "mDNS", 5900: "VNC", 8080: "HTTP alternate"}
VPN_RE = re.compile(r"vpn|(?<![a-z])(tun|tap|utun|wg|ppp|ipsec|wintun|zt)(?![a-z])", re.I)
VIRT_RE = re.compile(
    r"^(docker|br-|veth|virbr|vboxnet|vmnet|lxcbr|lxdbr|podman|cni|flannel|cali|kube|awdl|llw|anpi|gif|stf|bridge)"
    r"|vethernet|virtualbox|vmware|hyper-v|bluetooth|wsl",
    re.I,
)
SHARED = ipaddress.ip_network("100.64.0.0/10")
IN_USE = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)}
NO_ACCESS = {errno.EACCES, errno.EPERM, getattr(errno, "WSAEACCES", -1)}
PS_SCRIPT = (
    "$a=@(Get-NetIPAddress|Select-Object InterfaceAlias,IPAddress,PrefixLength);"
    "$p=@(Get-NetConnectionProfile|Select-Object InterfaceAlias,NetworkCategory);"
    "@{addresses=$a;profiles=$p}|ConvertTo-Json -Depth 3 -Compress"
)


def scope(addr: str) -> str:
    """loopback, link_local, multicast, shared (100.64.0.0/10), private, ula or public."""
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return "unknown"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.is_multicast:
        return "multicast"
    if ip.version == 6:
        return "ula" if ip in ipaddress.ip_network("fc00::/7") else "public"
    return "shared" if ip in SHARED else ("private" if ip.is_private else "public")


def kind_of(name: str, address: str) -> str:
    if scope(address) == "loopback":
        return "loopback"
    return "vpn" if VPN_RE.search(name) else "virtual" if VIRT_RE.search(name) else "physical"


def linux_ifaddrs() -> list[dict]:
    """Rows of name, up, address, prefix from getifaddrs (Linux only: the struct layout is fixed there)."""
    import ctypes

    class IfAddrs(ctypes.Structure):
        pass

    IfAddrs._fields_ = [
        ("next", ctypes.POINTER(IfAddrs)), ("name", ctypes.c_char_p), ("flags", ctypes.c_uint),
        ("addr", ctypes.c_void_p), ("mask", ctypes.c_void_p), ("dst", ctypes.c_void_p), ("data", ctypes.c_void_p),
    ]
    libc = ctypes.CDLL(None)
    libc.getifaddrs.argtypes = [ctypes.POINTER(ctypes.POINTER(IfAddrs))]
    head = ctypes.POINTER(IfAddrs)()
    if libc.getifaddrs(ctypes.byref(head)) != 0:
        raise OSError("getifaddrs failed")
    rows = []
    try:
        node = head
        while node:
            ifa = node.contents
            fam = int.from_bytes(ctypes.string_at(ifa.addr, 2), sys.byteorder) if ifa.addr and ifa.mask else 0
            if fam in (socket.AF_INET, socket.AF_INET6):
                off, size = (4, 4) if fam == socket.AF_INET else (8, 16)
                addr = ctypes.string_at(ifa.addr, off + size)[off:]
                mask = ctypes.string_at(ifa.mask, off + size)[off:]
                up = bool(ifa.flags & 0x1 and ifa.flags & 0x40)
                rows.append({"name": ifa.name.decode(errors="replace"), "up": up,
                             "address": str(ipaddress.ip_address(addr)),
                             "prefix": bin(int.from_bytes(mask, "big")).count("1")})
            node = ifa.next
    finally:
        libc.freeifaddrs(head)
    return rows


def parse_ifconfig(text: str) -> list[dict]:
    """Parse BSD and macOS ifconfig output (netmask in hex or dotted form)."""
    rows, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(\S+?):\s+flags=\w+<([^>]*)>", line)
        if m:
            cur = (m[1], "UP" in m[2].split(",") and "RUNNING" in m[2].split(","))
            continue
        m = re.match(r"\s+inet (\S+)(?:\s+-->\s+\S+)?\s+netmask\s+(\S+)", line)
        if m and cur:
            mask = int(m[2], 16) if m[2].startswith("0x") else int(ipaddress.ip_address(m[2]))
            rows.append({"name": cur[0], "up": cur[1], "address": m[1], "prefix": bin(mask).count("1")})
        m = re.match(r"\s+inet6\s+([0-9a-fA-F:]+)(?:%\S+)?\s+prefixlen\s+(\d+)", line)
        if m and cur:
            rows.append({"name": cur[0], "up": cur[1], "address": m[1], "prefix": int(m[2])})
    return rows


def parse_powershell(text: str) -> tuple[list[dict], list[dict]]:
    """Parse the JSON PowerShell prints for PS_SCRIPT: address rows and Windows network profiles."""
    data = json.loads(text)

    def items(v):
        return [v] if isinstance(v, dict) else (v or [])

    rows = [{"name": r["InterfaceAlias"], "up": True, "address": str(r["IPAddress"]).split("%")[0],
             "prefix": int(r["PrefixLength"])} for r in items(data.get("addresses"))]
    cats = {0: "Public", 1: "Private", 2: "DomainAuthenticated"}
    profiles = [{"interface": r["InterfaceAlias"],
                 "category": cats.get(r["NetworkCategory"], str(r["NetworkCategory"]))}
                for r in items(data.get("profiles"))]
    return rows, profiles


def group(rows: list[dict]) -> list[dict]:
    """Group address rows by interface, adding subnet, scope and a kind guessed from the interface name."""
    by_name: dict[str, dict] = {}
    for r in rows:
        try:
            net = str(ipaddress.ip_network(f"{r['address']}/{r['prefix']}", strict=False))
        except ValueError:
            continue
        item = by_name.setdefault(
            r["name"], {"name": r["name"], "up": r["up"], "kind": kind_of(r["name"], r["address"]), "addresses": []}
        )
        item["addresses"].append({"family": "IPv6" if ":" in r["address"] else "IPv4", "address": r["address"],
                                  "prefix": r["prefix"], "subnet": net, "scope": scope(r["address"])})
    return list(by_name.values())


def os_output(cmd: list[str], timeout: int) -> str:
    """Run one read-only OS command and return its text. Raises with a short reason if it fails or prints nothing."""
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} exited with {r.returncode}: {(r.stderr or '').strip()[:120]}")
    if not (r.stdout or "").strip():
        raise RuntimeError(f"{cmd[0]} printed nothing")
    return r.stdout


def interfaces() -> tuple[list[dict], list[dict], str | None]:
    """Return (interfaces, Windows network profiles, error). Best effort: [] plus a reason on failure."""
    profiles: list[dict] = []
    try:
        if sys.platform.startswith("linux"):
            rows = linux_ifaddrs()
        else:
            if sys.platform == "win32":
                cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", PS_SCRIPT]
                rows, profiles = parse_powershell(os_output(cmd, 25))
            else:
                rows = parse_ifconfig(os_output(["ifconfig"], 15))
            if not rows:
                raise RuntimeError("the output held no addresses, so the parser may not match this OS version")
    except Exception as exc:  # best effort by design: report why and carry on
        return [], [], f"{type(exc).__name__}: {exc}"
    return group(rows), profiles, None


def route_source(ip: str) -> str | None:
    """The local address the OS would use to reach ip. A UDP connect sends nothing: it only asks for a route."""
    try:
        with socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((ip, 9))
            return s.getsockname()[0]
    except OSError:
        return None


def resolve(host: str, timeout: float) -> tuple[list[str], float, str | None]:
    """Resolve a name with a time limit (the system resolver has none). Returns (addresses, ms, error)."""
    box: dict = {}

    def work() -> None:
        try:
            box["ok"] = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            box["err"] = exc

    t0 = time.perf_counter()
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    ms = (time.perf_counter() - t0) * 1000
    if th.is_alive():
        return [], ms, f"no answer from the resolver within {timeout:g} s"
    if "err" in box:
        return [], ms, str(box["err"].strerror or box["err"])
    return list(dict.fromkeys(r[4][0] for r in box["ok"])), ms, None


def port_state(port: int) -> str:
    """Try to bind a TCP port on all addresses, then let go of it at once."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", port))
            return "free"
        except OSError as exc:
            return "in_use" if exc.errno in IN_USE else "no_access" if exc.errno in NO_ACCESS else "error"


def os_name() -> str:
    system = platform.system()
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0]}"
    if system == "Windows":
        return f"Windows {platform.release()} {platform.version()}"
    return f"{system} {platform.release()}"


def find(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


def analyse(doc: dict, explicit: bool) -> list[dict]:
    """Turn the collected facts into findings: warn means a likely cause, info means worth knowing."""
    out, ifs, route = [], doc["interfaces"], doc["default_route"]
    usable = [x for i in ifs if i["up"] for x in i["addresses"] if x["scope"] not in ("loopback", "multicast")]
    if doc["interfaces_error"]:
        out.append(find("warn", "no_interface_data", f"could not list interfaces ({doc['interfaces_error']}); "
                        "paste the output of ipconfig or ifconfig instead. The macOS and "
                        "Windows listing has not been run on real machines, so a parser miss is possible"))
    elif not [x for x in usable if x["scope"] != "link_local"]:
        out.append(find("warn", "no_address", "no usable address (none, or only 169.254.x.x or fe80::): the network "
                        "gave this machine no address, so there is no DHCP lease. Fix that first."))
    if not route:
        out.append(find("warn", "no_default_route", "no default route: nothing beyond this machine's own subnet is "
                        "reachable. Fine on a router-less cable link, a fault anywhere else."))
    elif any(i["name"] == route["interface"] and i["kind"] == "vpn" for i in ifs):
        out.append(find("warn", "vpn_default_route", f"traffic leaves through {route['interface']}, which looks like a "
                        "VPN or tunnel. A full-tunnel VPN can hide devices on the local network."))
    elif any(i["kind"] == "vpn" and i["up"] and any(x["scope"] != "link_local" for x in i["addresses"]) for i in ifs):
        out.append(find("info", "vpn_present", "a VPN-looking interface is up: if devices cannot see each other, "
                        "check the VPN's split-tunnel or local-network setting"))
    if any(x["scope"] == "shared" for x in usable):
        out.append(find("info", "shared_address_space", "an address in 100.64.0.0/10: carrier-grade NAT or an overlay "
                        "VPN hands these out"))
    nets = {x["subnet"] for i in ifs if i["up"] and i["kind"] in ("physical", "virtual") for x in i["addresses"]
            if x["family"] == "IPv4" and x["scope"] in ("private", "public")}
    if len(nets) > 1:
        out.append(find("info", "many_subnets", f"{len(nets)} IPv4 subnets here ({', '.join(sorted(nets))}): virtual "
                        "adapters can make a tool advertise the wrong address"))
    name = doc["name_resolution"]
    if not name["mdns_ok"]:
        out.append(find("info", "mdns_unresolved", f"{name['mdns_name']} does not resolve here. Matters only if your "
                        "tool finds devices by .local name: test by IP address as well."))
    host = name["hostname_addresses"]
    if host and all(scope(x) == "loopback" for x in host):
        out.append(find("info", "hostname_is_loopback", f"this machine's own name resolves only to {host[0]}: a peer "
                        "asking for it by name gets nothing useful"))
    for p in doc["windows_profiles"]:
        if p["category"] == "Public":
            out.append(find("warn", "windows_public_profile", f"{p['interface']} is on the Public network profile: "
                            "Windows blocks most inbound connections there. Private is for networks you trust."))
    for p in doc["ports"]:
        if explicit and p["state"] != "free":
            out.append(find("warn", "port_not_free", f"port {p['port']} is {p['state']}: this machine cannot bind it"))
    return out


def collect(label: str | None, ports: list[int] | None) -> dict:
    host = socket.gethostname()
    ifs, profiles, err = interfaces()
    src = route_source("203.0.113.1") or route_source("2001:db8::1")
    route = None
    if src:
        mine = [(i["name"], x["prefix"]) for i in ifs for x in i["addresses"] if x["address"] == src]
        owner = mine[0] if mine else (None, None)
        route = {"source_address": src, "interface": owner[0], "prefix": owner[1],
                 "family": "IPv6" if ":" in src else "IPv4"}
    mdns_name = host.split(".")[0] + ".local"
    m_addrs, m_ms, m_err = resolve(mdns_name, 2.0)
    h_addrs, _, _ = resolve(host, 2.0)
    doc = {
        "tool": "mesh_local", "version": VERSION, "kind": "local", "label": label, "hostname": host, "os": os_name(),
        "python": platform.python_version(), "ipv6_supported": socket.has_ipv6, "interfaces": ifs,
        "interfaces_error": err, "default_route": route, "windows_profiles": profiles,
        "name_resolution": {"hostname_addresses": h_addrs, "mdns_name": mdns_name, "mdns_ok": bool(m_addrs),
                            "mdns_addresses": m_addrs, "mdns_ms": round(m_ms, 1), "mdns_error": m_err},
        "ports": [{"port": p, "service": PORT_NAMES.get(p), "state": port_state(p)} for p in (ports or LOCAL_PORTS)],
    }
    doc["findings"] = analyse(doc, bool(ports))
    return doc


def render(d: dict) -> None:
    v6 = "yes" if d["ipv6_supported"] else "no"
    print(f"{d['label'] or d['hostname']}  ({d['os']}, python {d['python']}, IPv6 {v6})")
    r = d["default_route"]
    route = f"{r['source_address']}/{r['prefix']} on {r['interface'] or '?'}" if r else "none"
    print(f"default route: {route}")
    for i in d["interfaces"]:
        addrs = "  ".join(f"{x['address']}/{x['prefix']} ({x['scope']})" for x in i["addresses"])
        print(f"  {i['name']:<14} {'up  ' if i['up'] else 'down'} {i['kind']:<9} {addrs}")
    n = d["name_resolution"]
    mdns = f"resolves ({', '.join(n['mdns_addresses'])})" if n["mdns_ok"] else f"does not resolve ({n['mdns_error']})"
    print(f"{n['mdns_name']}: {mdns}")
    print("ports: " + ", ".join(f"{p['port']} {p['state']}" for p in d["ports"]))
    for p in d["windows_profiles"]:
        print(f"windows profile: {p['interface']} is {p['category']}")
    print("findings:" if d["findings"] else "findings: none")
    for x in d["findings"]:
        print(f"  [{x['level']}] {x['message']}")


def ports_arg(text: str) -> list[int]:
    out = []
    for part in text.split(","):
        if not part.strip().isdigit() or not 1 <= int(part) <= 65535:
            raise argparse.ArgumentTypeError(f"bad port {part!r}: use whole numbers from 1 to 65535, comma separated")
        out.append(int(part))
    if len(out) > 32:
        raise argparse.ArgumentTypeError("at most 32 ports")
    return list(dict.fromkeys(out))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mesh_local", description=__doc__.splitlines()[0])
    ap.add_argument("--ports", type=ports_arg, help="TCP ports to test for a free bind, comma separated")
    ap.add_argument("--label", help="a name for this device in reports, for example laptop")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    doc = collect(args.label, args.ports)
    if args.json:
        print(json.dumps(doc, indent=2))
    else:
        render(doc)
    return 1 if any(x["level"] == "warn" for x in doc["findings"]) else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
