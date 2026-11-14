#!/usr/bin/env python3
"""mesh_report.py - combine the JSON from several devices into a pair-by-pair connectivity matrix.

Feed it, on standard input, the --json output of mesh_local.py (one per device) and mesh_link.py peer or listen
runs, as separate JSON documents one after another or as one JSON array. For each pair of devices it shows what
works in each direction, whether the two sit on the same subnet, and the most likely layer that is broken.
Later documents replace earlier ones for the same pair, so a re-test after a fix just goes at the end.

Python 3.10+, standard library only. No network access, reads no local files, writes none.
Usage: python3 mesh_report.py [--json] < all-the-json.txt
Exit codes: 0 every tested direction works and no warnings, 1 problems found, 2 bad input.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys

VERSION = "1.0.0"
MAX_INPUT, MAX_DEVICES = 2_000_000, 12
CELL = {"ok": "ok", "partial": "partial", "refused": "refused", "filtered": "filtered", "unreachable": "unreachable",
        "unresolved": "no name", "error": "error"}  # fmt: skip
DEVICE_CODES = ("windows_public_profile", "vpn_default_route", "no_default_route", "no_address", "no_interface_data")


def read_docs(text: str) -> list[dict]:
    """Parse one or more JSON documents (or arrays of them) from text."""
    dec, i, docs = json.JSONDecoder(), 0, []
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return docs
        obj, i = dec.raw_decode(text, i)
        docs += obj if isinstance(obj, list) else [obj]


def key(name: str) -> str:
    n = name.strip().lower()
    return n[: -len(".local")] if n.endswith(".local") else n


def usable(local: dict | None) -> list[dict]:
    """Addresses that can say 'same subnet': on an up physical or VPN interface, not loopback or link-local."""
    if not local:
        return []
    return [
        x
        for i in local.get("interfaces", [])
        if i.get("up") and i.get("kind") in ("physical", "vpn")
        for x in i.get("addresses", [])
        if x.get("scope") not in ("loopback", "link_local", "multicast")
    ]


def same_subnet(a_local: dict | None, b_local: dict | None) -> tuple[bool | None, str | None]:
    xs, ys = usable(a_local), usable(b_local)
    if not xs or not ys:
        return None, None
    for x in xs:
        for y in ys:
            nx, ny = ipaddress.ip_network(x["subnet"]), ipaddress.ip_network(y["subnet"])
            both = ipaddress.ip_address(y["address"]) in nx and ipaddress.ip_address(x["address"]) in ny
            if x["family"] == y["family"] and both:
                return True, str(nx)
    return False, None


GROUP_FILTERED = {
    True: "Same subnet, so suspect client or AP isolation on the router, a guest network, or both devices' firewalls "
          "dropping inbound traffic. Check the router first, then each firewall.",
    False: "Different subnets, so the router, a VLAN, a guest network or a VPN separates them.",
    None: "Run mesh_local.py on both devices to see whether they share a subnet.",
}
BOTH = {
    "unreachable": "no route either way: the devices sit on networks that cannot reach each other.",
    "refused": "each side answers and refuses: the path works but nothing listens on the tested ports. Check the "
               "port, that the tool is running, and for a battery optimiser killing it.",
    "unresolved": "the name does not resolve from either side. Use IP addresses; for .local names check multicast "
                  "DNS and VPNs.",
}


def one_way(p: str, q: str, status: str) -> tuple[str, str]:
    """(level, text) for a single failing direction p->q."""
    if status == "refused":
        return "info", f"{q} answers but nothing listens on the tested ports (normal if only one device listens there)"
    if status == "partial":
        return "warn", f"only some of the tested ports answer on {q}: the tool may use a port that was not tested"
    if status == "unresolved":
        return "problem", f"the name {q} did not resolve from {p}: use its IP address"
    if status == "unreachable":
        return "problem", f"{p} has no route to {q}: different networks, or a VPN taking the route"
    if status == "filtered":
        return "problem", f"nothing gets through, so {q}'s firewall or network profile is dropping inbound connections"
    return "problem", f"the test reported {status}"


def judge(a: str, b: str, ab: str | None, ba: str | None, same: bool | None) -> list[dict]:
    """Findings for one pair from the status of a->b and b->a (a peer summary status such as ok or filtered)."""
    out = []
    if ab is None and ba is None:
        return [{"level": "info", "message": f"{a} and {b}: no peer test yet. Run mesh_link.py peer from each device."}]
    if ab == ba and ab != "ok":
        text = BOTH.get(ab, f"both directions report {ab}.")
        if ab == "filtered":
            text = "both directions time out. " + GROUP_FILTERED[same]
        return [{"level": "problem", "message": f"{a} <-> {b}: {text}"}]
    for p, q, s, back in ((a, b, ab, ba), (b, a, ba, ab)):
        if s is None:
            out.append({"level": "info", "message": f"{p}->{q} not tested: it must work both ways, so test it too."})
        elif s != "ok":
            level, text = one_way(p, q, s)
            tail = f"; {q}->{p} works, which points at {q}, not the router" if back == "ok" and s == "filtered" else ""
            out.append({"level": level, "message": f"{p}->{q} is {s}: {text}{tail}."})
    if same is False and "ok" in (ab, ba):
        out.append({"level": "info", "message": f"{a} and {b} are on different subnets: direct connections route, but "
                    "discovery by broadcast or multicast does not cross subnets. Add the device by IP address."})
    return out


def build(docs: list[dict]) -> dict:
    locals_: dict[str, dict] = {}
    peers, listens, ignored = [], [], 0
    for d in docs:
        kind = d.get("kind") if isinstance(d, dict) and str(d.get("tool", "")).startswith("mesh_") else None
        if kind == "local":
            locals_[key(d.get("label") or d.get("hostname") or "device")] = d
        elif kind in ("peer", "listen"):
            (peers if kind == "peer" else listens).append(d)
        else:
            ignored += 1
    names = {k: d.get("label") or d.get("hostname") for k, d in locals_.items()}
    owner = {x["address"]: k for k, d in locals_.items() for i in d.get("interfaces", [])
             for x in i.get("addresses", [])}
    cells: dict[tuple[str, str], str] = {}
    for d in peers:
        who, tgt = d["from"], d["target"]
        src = key(who.get("label") or who.get("hostname") or "device")
        dst = next((owner[x] for x in tgt.get("addresses", []) if x in owner), None) or key(tgt.get("host", "?"))
        names.setdefault(src, who.get("label") or who.get("hostname"))
        names.setdefault(dst, tgt.get("host"))
        if src != dst:
            cells[(src, dst)] = d.get("summary", {}).get("status", "error")
    for d in listens:  # a connection seen by a listener proves that direction works
        me = key(d.get("label") or d.get("hostname") or "device")
        names.setdefault(me, d.get("label") or d.get("hostname"))
        for src in d.get("unique_sources", []):
            if src in owner and owner[src] != me:
                cells.setdefault((owner[src], me), "ok")
    keys = list(names)[:MAX_DEVICES]
    devices = [{"name": names[k], "os": (locals_.get(k) or {}).get("os"), "profiled": k in locals_,
                "findings": [x for x in (locals_.get(k) or {}).get("findings", []) if x["code"] in DEVICE_CODES]}
               for k in keys]  # fmt: skip
    pairs = []
    for n, a in enumerate(keys):
        for b in keys[n + 1 :]:
            ab, ba = cells.get((a, b)), cells.get((b, a))
            if ab is None and ba is None and not (a in locals_ and b in locals_):
                continue
            same, net = same_subnet(locals_.get(a), locals_.get(b))
            pairs.append({"a": names[a], "b": names[b], "same_subnet": same, "subnet": net, "a_to_b": ab, "b_to_a": ba,
                          "findings": judge(names[a], names[b], ab, ba, same)})  # fmt: skip
    matrix = {names[a]: {names[b]: "-" if a == b else CELL.get(cells.get((a, b)), cells.get((a, b)) or "untested")
                         for b in keys} for a in keys}  # fmt: skip
    problem = any(f["level"] in ("problem", "warn") for p in pairs for f in p["findings"])
    problem = problem or any(x["level"] == "warn" for d in devices for x in d["findings"])
    return {"tool": "mesh_report", "version": VERSION, "kind": "report", "ignored_documents": ignored,
            "devices": devices, "matrix": matrix, "pairs": pairs, "problem": problem}  # fmt: skip


def render(rep: dict) -> None:
    names = list(rep["matrix"])
    print("| from \\ to | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for a in names:
        print(f"| {a} | " + " | ".join(rep["matrix"][a][b] for b in names) + " |")
    for p in rep["pairs"]:
        same = {True: f"same subnet ({p['subnet']})", False: "different subnets", None: "subnet unknown"}
        sub = same[p["same_subnet"]]
        print(f"\n{p['a']} <-> {p['b']}: {sub}")
        for x in p["findings"] or [{"level": "ok", "message": "both directions work"}]:
            print(f"  [{x['level']}] {x['message']}")
    notes = [(d["name"], x) for d in rep["devices"] for x in d["findings"]]
    if notes:
        print("\nDevice warnings:")
        for name, x in notes:
            print(f"  [{x['level']}] {name}: {x['message']}")
    if rep["ignored_documents"]:
        print(f"\nignored {rep['ignored_documents']} document(s) that are not mesh output")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mesh_report", description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    text = sys.stdin.read(MAX_INPUT + 1)
    if len(text) > MAX_INPUT:
        print(f"error: input is over {MAX_INPUT:,} characters", file=sys.stderr)
        return 2
    try:
        rep = build(read_docs(text))
    except (ValueError, RecursionError, KeyError, TypeError, AttributeError) as exc:
        print(f"error: input is not JSON from the mesh scripts ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2
    if not rep["devices"]:
        print("error: no device data found: pipe in --json output from mesh_local.py and mesh_link.py", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        render(rep)
    return 1 if rep["problem"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
