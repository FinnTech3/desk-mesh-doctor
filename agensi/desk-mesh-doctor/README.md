# Desk Mesh Doctor

An agent skill that finds out why devices that should work as one desk will not connect: shared mouse and
keyboard, clipboard, file drop, notifications and calls across a Mac, a PC, a Linux box, a phone and a tablet. It
works for whatever sharing tool you use. It does not recommend or compare tools.

## What you get

- A short interview, then real tests: each device's addresses, subnet, route and name lookup; a TCP test of the
  other device with round-trip stats; a temporary listener so the other device can test reaching you.
- A pair-by-pair matrix of what works in each direction, with the likely broken layer.
- A decision tree to one specific fix, and per-OS checklists (macOS, Windows, Linux, Android, iOS, routers, VPN).
- A "report to paste" for asking the tool's maker or a forum for help, with no secrets in it.

## What it needs

- Python 3.10 or newer on each computer you test from. No packages and no API key.
- Permission for your agent to run Python scripts. The scripts connect only to hosts you name, read no local
  files and write none.
- Phones and tablets cannot run the scripts: you test them from a computer or with a browser.

## How to use it

Ask your agent, for example:

- "My mouse won't move to my other computer."
- "Clipboard sharing stopped working between my laptop and my desktop."
- "My phone can't find my computer on the same Wi-Fi."
- "File drop to my tablet keeps failing."

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `scripts/mesh_local.py` | This machine's addresses, route, name lookup and free ports |
| `scripts/mesh_link.py` | `peer` tests reaching another device, `listen` lets another device test reaching this one |
| `scripts/mesh_report.py` | Combines the JSON from several devices into a connectivity matrix |
| `references/decision-tree.md` | Symptom to layer to fix |
| `references/macos.md`, `windows.md`, `linux.md`, `android.md`, `ios.md` | Per-OS checklists |
| `references/router-and-network.md`, `vpn.md` | Client isolation, guest networks, multicast, split tunnelling |
| `references/ports.md` | Well-known service ports and what each result means |
| `references/report-template.md` | A template to paste when asking for help |
| `examples/sample-session.md` | A real session, with the JSON and reports it produced |

## Limits

It finds the layer that is broken. It cannot see inside the sharing tool or the router's admin page, it tests TCP
only, and it cannot test another device unless you run it there. Round-trip figures are TCP connect times judged
against rules of thumb, not a measurement of the tool. The macOS and Windows code paths were not run on real
machines: their parsers are tested against sample text.
