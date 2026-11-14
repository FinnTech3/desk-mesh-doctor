#!/usr/bin/env python3
"""mesh_link.py - test the link between two devices. Python 3.10+, standard library only.

  peer HOST     can this machine reach HOST? name lookup, subnet check, TCP connect per port, round-trip stats
  listen PORT   listen on one TCP port for a while so another device can test reaching this one

Traffic goes only to the HOST you name (peer) or comes from whoever dials the port you listen on.
Reads no local files, writes none: results go to stdout. Exit codes: 0 fine, 1 findings, 2 bad input.
"""

from __future__ import annotations

import argparse
import errno
import ipaddress
import json
import math
import re
import signal
import socket
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

VERSION = "1.0.0"
PEER_PORTS = (22, 80, 443, 445, 3389, 5900)
IN_USE = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)}
NO_ACCESS = {errno.EACCES, errno.EPERM, getattr(errno, "WSAEACCES", -1)}
LOCAL_BLOCK = "this machine refused to send it: a local firewall or permission rule"
STATUS = {  # errno -> (status, what it means)
    errno.ECONNREFUSED: ("refused", "the device answered and nothing listens there (or its firewall rejects it)"),
    errno.ENETUNREACH: ("unreachable_network", "no route to that network: this machine cannot reach it"),
    errno.EHOSTUNREACH: ("unreachable_host", "no route to host: the local network cannot find the device"),
    errno.ECONNRESET: ("reset", "the connection was reset straight after it started"),
    errno.ETIMEDOUT: ("timeout", "no reply"),
    errno.EACCES: ("blocked_local", LOCAL_BLOCK),
    errno.EPERM: ("blocked_local", LOCAL_BLOCK),
}
NEXT = {
    "filtered": "Every port timed out: packets are dropped or never arrive. Check in order: same Wi-Fi and not a guest "
                "network (client isolation), a VPN capturing the route, the other device's firewall profile, "
                "and that it is awake.",
    "unreachable": "No route to this address. Check the address, any VPN, and that both devices share a network.",
    "refused": "The device answered and refused, so the path works but nothing listens on those ports. Check the "
               "port your tool uses, that the tool is running there, and that no battery optimiser killed it.",
}


def find(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


def subnet_check(
    local_addr: str | None, local_prefix: int | None, peer_addr: str, peer_prefix: int | None = None
) -> dict:
    """Same-subnet test from two addresses and prefix lengths. 'same' is True, False or None (cannot tell)."""
    try:
        a, b = ipaddress.ip_address((local_addr or "").split("%")[0]), ipaddress.ip_address(peer_addr.split("%")[0])
    except ValueError:
        return {"same": None, "note": "no usable local or peer address to compare"}
    if a.version != b.version:
        return {"same": None, "note": "one address is IPv4 and the other IPv6: compare one family"}
    if a.is_loopback and b.is_loopback:
        return {"same": True, "note": "both are loopback: this is the same machine"}
    if a.is_link_local or b.is_link_local:
        return {"same": None, "note": "link-local addresses only work on one link, which a prefix check cannot see"}
    for p in (local_prefix, peer_prefix):
        if p is not None and not 0 <= p <= a.max_prefixlen:
            return {"same": None, "note": f"prefix length {p} is not valid for IPv{a.version}"}
    if local_prefix is None:
        return {"same": None, "note": "prefix length unknown: pass --local-prefix (default_route prefix, local output)"}
    na = ipaddress.ip_network(f"{a}/{local_prefix}", strict=False)
    out = {"same": b in na, "local_net": str(na), "note": ""}
    if peer_prefix is not None:
        nb = ipaddress.ip_network(f"{b}/{peer_prefix}", strict=False)
        out.update(peer_net=str(nb), same=(b in na) and (a in nb))
        if (b in na) != (a in nb):
            out["note"] = "the prefix lengths disagree: each side draws the subnet edge differently"
    return out


def stats(samples: list[float]) -> dict:
    """min, median, p95 (nearest rank), max and jitter (mean change between consecutive samples), all in ms."""
    s = sorted(samples)
    steps = [abs(y - x) for x, y in zip(samples, samples[1:], strict=False)]
    jitter = statistics.fmean(steps) if steps else 0.0
    return {"min": round(s[0], 2), "median": round(statistics.median(s), 2), "max": round(s[-1], 2),
            "p95": round(s[max(0, math.ceil(0.95 * len(s)) - 1)], 2), "jitter": round(jitter, 2)}


def feel(st: dict, sent: int, lost: int) -> dict:
    """Rules of thumb for pointer feel, not a standard. The round trip is a TCP connect, so it includes the kernel."""
    med, p95, jit = st["median"], st["p95"], st["jitter"]
    if med <= 10 and p95 <= 30 and jit <= 8:
        grade, text = "good", "should feel instant"
    elif med <= 25 and p95 <= 60:
        grade, text = "ok", "usable, with slight lag on fast pointer movement"
    elif med <= 50 and p95 <= 120:
        grade, text = "laggy", "the pointer will trail your hand and typing will feel delayed"
    else:
        grade, text = "poor", "too slow for a shared pointer"
    if sent and lost / sent > 0.05:
        grade, text = "poor", f"{lost} of {sent} connects got no answer, so stalls and drops are likely"
    return {"grade": grade, "text": f"{text} (rule of thumb: median/p95 under 10/30 ms good, 25/60 ok, 50/120 laggy)"}


def resolve(host: str, timeout: float = 3.0) -> tuple[list[str], float, str | None]:
    """Resolve a name with a time limit (the system resolver has none). IP literals skip it. -> (addrs, ms, error)."""
    try:
        ipaddress.ip_address(host.split("%")[0])
        return [host], 0.0, None
    except ValueError:
        pass
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


def tcp_connect(ip: str, port: int, timeout: float, clock=time.perf_counter) -> tuple[str, float, str]:
    """One TCP connect. Returns (status, ms, reason). A refused connect still times the round trip."""
    if sys.platform == "win32":
        timeout = max(timeout, 2.5)  # Windows retries a refused SYN for about 2 s before it reports "refused"
    t0 = clock()
    try:
        fam, typ, proto, _, sockaddr = socket.getaddrinfo(ip, port, type=socket.SOCK_STREAM)[0]
        with socket.socket(fam, typ, proto) as s:
            s.settimeout(timeout)
            s.connect(sockaddr)
        return "open", (clock() - t0) * 1000, ""
    except TimeoutError:
        why = f"no reply in {timeout:g} s: a firewall drops it, the address is wrong, or the device is off or asleep"
        return "timeout", (clock() - t0) * 1000, why
    except OSError as exc:
        status, why = STATUS.get(exc.errno or 0, ("error", exc.strerror or str(exc)))
        return status, (clock() - t0) * 1000, why


def sample_rtt(ip, port, n, timeout, connect=tcp_connect, clock=time.perf_counter, sleep=time.sleep, budget=30.0):
    """Repeat connects to one port. Returns (round trips in ms, connects sent, connects that got no answer)."""
    start, got, sent = clock(), [], 0
    while sent < n and clock() - start <= budget:
        status, ms, _ = connect(ip, port, timeout)
        sent += 1
        if status in ("open", "refused"):
            got.append(ms)
        sleep(0.01)
    return got, sent, sent - len(got)


def summarise(ports: list[dict]) -> str:
    states = {p["status"] for p in ports}
    if "open" in states:
        return "ok" if states == {"open"} else "partial"
    if "refused" in states:
        return "refused"
    if states == {"timeout"}:
        return "filtered"
    return "unreachable" if states <= {"unreachable_network", "unreachable_host"} else "error"


def source_address(ip: str) -> str | None:
    """The local address the OS would use to reach ip. A UDP connect sends nothing: it only asks for a route."""
    try:
        with socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((ip, 9))
            return s.getsockname()[0]
    except OSError:
        return None


def cmd_peer(a) -> int:
    ports = a.ports or list(PEER_PORTS)
    addrs, res_ms, res_err = resolve(a.host)
    doc = {"tool": "mesh_link", "version": VERSION, "kind": "peer",
           "from": {"label": a.label, "hostname": socket.gethostname()},
           "target": {"host": a.host, "addresses": addrs, "resolve_ms": round(res_ms, 1), "resolve_error": res_err},
           "subnet": None, "ports": [], "latency": None, "feel": None, "findings": []}
    f = doc["findings"]
    if not addrs:
        doc["summary"] = {"status": "unresolved", "open": [], "explicit_ports": bool(a.ports)}
        local = a.host.lower().endswith(".local")
        hint = " A .local name needs multicast DNS working on both devices." if local else ""
        f.append(find("problem", "unresolved", f"{a.host} did not resolve ({res_err}).{hint} Retry with the device's "
                      "IP address: that separates a naming problem from a network problem."))
    else:
        ip = next((x for x in addrs if ":" not in x), addrs[0])
        src = source_address(ip)
        doc["from"].update(source_address=src, prefix=a.local_prefix)
        doc["subnet"] = sn = subnet_check(src, a.local_prefix, ip, a.peer_prefix)
        with ThreadPoolExecutor(max_workers=min(8, len(ports))) as pool:
            res = list(pool.map(lambda p: tcp_connect(ip, p, a.timeout), ports))
        doc["ports"] = [{"port": p, "status": s, "ms": round(ms, 2), "reason": why}
                        for p, (s, ms, why) in zip(ports, res, strict=True)]
        status = summarise(doc["ports"])
        opened = [p["port"] for p in doc["ports"] if p["status"] == "open"]
        doc["summary"] = {"status": status, "open": opened, "explicit_ports": bool(a.ports)}
        answered = [p for p in doc["ports"] if p["status"] in ("open", "refused")]
        if answered:
            best = next((p for p in answered if p["status"] == "open"), answered[0])
            got, sent, lost = sample_rtt(ip, best["port"], a.samples, a.timeout, connect=tcp_connect)
            if got:
                doc["latency"] = {"port": best["port"], "sent": sent, "answered": len(got), "lost": lost, **stats(got)}
                doc["feel"] = feel(doc["latency"], sent, lost)
        if status in NEXT and not opened:
            f.append(find("problem" if a.ports or status != "refused" else "info", status, NEXT[status]))
        elif a.ports or status == "error":
            f += [find("problem", f"port_{p['status']}", f"port {p['port']}: {p['status']}. {p['reason']}")
                  for p in doc["ports"] if p["status"] != "open"]
        if sn["same"] is False:
            f.append(find("info" if opened else "warn", "different_subnet",
                          f"{src} ({sn['local_net']}) and {ip} are on different subnets. Direct connections can "
                          "route, but discovery by broadcast or multicast does not cross subnets: add the device "
                          "by IP address."))
        if doc["feel"] and doc["feel"]["grade"] in ("laggy", "poor"):
            f.append(find("warn", "latency", f"round trip {doc['feel']['grade']}: {doc['feel']['text']}"))
    if a.json:
        print(json.dumps(doc, indent=2))
    else:
        render_peer(doc)
    return 1 if any(x["level"] in ("problem", "warn") for x in f) else 0


def render_findings(items: list[dict]) -> None:
    print("findings:" if items else "findings: none")
    for x in items:
        print(f"  [{x['level']}] {x['message']}")


def render_peer(d: dict) -> None:
    t, fr, sn, lt = d["target"], d["from"], d["subnet"], d["latency"]
    src = f" ({fr['source_address']})" if fr.get("source_address") else ""
    print(f"peer {t['host']}  from {fr['label'] or fr['hostname']}{src}")
    if t["addresses"]:
        print(f"name: {', '.join(t['addresses'])} in {t['resolve_ms']} ms")
    else:
        print(f"name: FAILED ({t['resolve_error']})")
    if sn:
        word = {True: "same", False: "different", None: "unknown"}[sn["same"]]
        print(f"subnet: {word} {sn.get('local_net', '')} {sn['note']}".rstrip())
    for p in d["ports"]:
        print(f"  port {p['port']:<6}{p['status']:<20}{p['ms']:>8.1f} ms")
    if lt:
        print(f"latency on port {lt['port']}: {lt['answered']}/{lt['sent']} answered, min {lt['min']} median "
              f"{lt['median']} p95 {lt['p95']} max {lt['max']} jitter {lt['jitter']} ms")
        print(f"feel: {d['feel']['grade']}, {d['feel']['text']}")
    render_findings(d["findings"])


def bind_listener(port: int) -> socket.socket:
    """Listen on all addresses: IPv4 and IPv6 together when the machine really has IPv6."""
    with socket.socket() as probe:  # a dual-stack bind can sit beside an IPv4 listener on macOS and Windows
        probe.bind(("0.0.0.0", port))
    for fam, addr in ((socket.AF_INET6, "::"), (socket.AF_INET, "0.0.0.0")):
        s = None
        try:
            s = socket.socket(fam, socket.SOCK_STREAM)
            if sys.platform != "win32":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if fam == socket.AF_INET6:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            s.bind((addr, port))
            s.listen(64)
            return s
        except OSError as exc:
            if s:
                s.close()
            if fam == socket.AF_INET or exc.errno in IN_USE or exc.errno in NO_ACCESS:
                raise
    raise OSError("no usable address family")


def greet(conn: socket.socket) -> None:
    """Close the connection. If a web browser dialled, answer with one line so a phone can see it worked."""
    try:
        conn.settimeout(0.05)
        try:
            first = conn.recv(256)
        except OSError:
            first = b""
        if first[:4] in (b"GET ", b"HEAD", b"POST"):
            body = b"mesh_link listener: this device is reachable on this port.\n"
            head = b"HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: %d\r\n\r\n"
            conn.sendall(head % len(body) + body)
    except OSError:
        pass
    finally:
        conn.close()


def _stop(*_args) -> None:
    raise KeyboardInterrupt


def serve(srv: socket.socket, a, doc: dict) -> None:
    """Accept connections until the time is up, a stop signal arrives or Ctrl-C."""
    t0 = time.monotonic()
    srv.settimeout(0.2)
    while time.monotonic() - t0 < a.seconds:
        try:
            conn, addr = srv.accept()
        except TimeoutError:
            continue
        except OSError:
            return
        src, at = addr[0].removeprefix("::ffff:"), round(time.monotonic() - t0, 2)
        doc["connections_total"] += 1
        if src not in doc["unique_sources"]:
            doc["unique_sources"].append(src)
        if len(doc["connections"]) < 50:
            doc["connections"].append({"from": src, "source_port": addr[1], "at_s": at})
        if not a.json and doc["connections_total"] <= 5:
            print(f"  connection from {src} at {at} s", flush=True)
        greet(conn)


def cmd_listen(a) -> int:
    doc = {"tool": "mesh_link", "version": VERSION, "kind": "listen", "label": a.label,
           "hostname": socket.gethostname(), "port": a.port, "seconds": a.seconds, "connections_total": 0,
           "unique_sources": [], "connections": [], "findings": []}
    f = doc["findings"]
    try:
        srv = bind_listener(a.port)
    except OSError as exc:
        why = "something already listens on it" if exc.errno in IN_USE else exc.strerror or str(exc)
        f.append(find("problem", "bind_failed", f"cannot listen on TCP port {a.port}: {why}"))
        srv = None
    if srv:
        try:
            old = signal.signal(signal.SIGTERM, _stop)
        except (ValueError, OSError):
            old = None
        if not a.json:
            print(f"listening on TCP port {a.port} for {a.seconds:g} s: test it from the other device now", flush=True)
        try:
            serve(srv, a, doc)
        except KeyboardInterrupt:
            doc["interrupted"] = True
        finally:
            srv.close()
            if old is not None:
                signal.signal(signal.SIGTERM, old)
        if not doc["connections_total"]:
            f.append(find("warn", "nothing_connected", f"nothing reached TCP port {a.port} in {a.seconds:g} s. "
                          "Check the address and port typed on the other device, this machine's firewall (allow this "
                          "one port, Private profile only) and router client isolation."))
    if a.json:
        print(json.dumps(doc, indent=2))
    else:
        who = ", ".join(doc["unique_sources"]) or "nobody"
        print(f"port {a.port}: {doc['connections_total']} connection(s) from {who}")
        render_findings(f)
    return 1 if f else 0


def ports_arg(text: str) -> list[int]:
    out = []
    for part in text.split(","):
        if not part.strip().isdigit() or not 1 <= int(part) <= 65535:
            raise argparse.ArgumentTypeError(f"bad port {part!r}: use whole numbers from 1 to 65535, comma separated")
        out.append(int(part))
    if len(out) > 32:
        raise argparse.ArgumentTypeError("at most 32 ports")
    return list(dict.fromkeys(out))


def bounded(lo: float, hi: float, kind=float):
    def conv(text: str):
        try:
            v = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
        if not lo <= v <= hi:
            raise argparse.ArgumentTypeError(f"{text} is outside {lo:g} to {hi:g}")
        return v

    return conv


def host_arg(text: str) -> str:
    text = text.strip().strip("[]")
    if not text or len(text) > 253 or not re.fullmatch(r"[\w.:%-]+", text):
        raise argparse.ArgumentTypeError("HOST must be a name or an IP address: letters, digits, dots, dashes, colons")
    return text


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print JSON instead of text")
    common.add_argument("--label", help="a name for this device in reports, for example laptop")
    ap = argparse.ArgumentParser(prog="mesh_link", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("peer", parents=[common], help="test reaching another device")
    p.add_argument("host", type=host_arg, help="name or IP address of the other device")
    p.add_argument("--ports", type=ports_arg, help="TCP ports, comma separated (default 22,80,443,445,3389,5900)")
    p.add_argument("--samples", type=bounded(1, 200, int), default=20, help="round-trip samples (default 20)")
    p.add_argument("--timeout", type=bounded(0.05, 10), default=1.0, help="seconds per connect (default 1)")
    p.add_argument("--local-prefix", type=bounded(0, 128, int), help="this machine's prefix length, from mesh_local")
    p.add_argument("--peer-prefix", type=bounded(0, 128, int), help="the other device's prefix length, if known")
    p = sub.add_parser("listen", parents=[common], help="listen so another device can test reaching this one")
    p.add_argument("port", type=bounded(1, 65535, int))
    p.add_argument("--seconds", type=bounded(0.1, 600), default=60.0, help="how long to listen (default 60, max 600)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return cmd_peer(args) if args.cmd == "peer" else cmd_listen(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
