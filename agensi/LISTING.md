# Agensi listing copy

Paste these into the submit form at agensi.io/dashboard/submit. Upload `dist/desk-mesh-doctor.zip`
(build it with `python3 tools/agensi_build.py`, which also checks this file against Agensi's field limits).
Logo and screenshots are in `agensi/media/`.

| Field | Value |
|---|---|
| Title | Desk Mesh Doctor: Fix Device Sharing That Won't Connect |
| Categories | Productivity; Workflow Automation; Testing & Debugging |
| Suggested price | $9 one-time |
| Tags | networking, troubleshooting, wifi, firewall, multi-device |
| Compatibility note | Requires Python 3.10+ on each computer you test from. No packages, no API key. Phones and tablets are tested from a computer or a browser. |
| Permissions | Terminal (runs three Python scripts from temporary files); network access only to hosts you name, plus one temporary listener on a port you choose; read-only OS network tools (ifconfig on macOS, Get-NetIPAddress on Windows). Reads no local files, writes no files, uses no environment variables. |
| Docs link | https://github.com/FinnTech3/desk-mesh-doctor |

## Summary

Finds why devices that should share one mouse, keyboard, clipboard or files will not connect. Tests address, subnet, names, ports, firewall profile, VPN and delay, then walks you to one fix. Works with any sharing tool. Needs Python 3.10+.

## Description

Your Mac, PC, Linux box, phone and tablet should work as one desk. They do not, and the sharing tool's error
message says "could not connect". Ask your agent why, and get an answer you can check.

The skill starts with a short interview: which devices, which OS versions, same router or not, any VPN, and what
exactly fails. Then it measures. Three bundled scripts read each device's addresses, subnet and route, test whether
`.local` names resolve, connect to the other device port by port with a clear reason for every failure (refused,
timed out, no route), time repeated connects for round-trip stats, and combine what several devices saw into a
pair-by-pair matrix. A decision tree and per-OS checklists turn the broken layer into one specific fix, which is
then tested again.

**How it works.** Your agent runs the scripts, reads their JSON, and writes the answer. The scripts connect only to
hosts you name, open none of your files and write none. For a second computer you run the same script there and paste the
JSON back. A phone or tablet is tested from a computer with a temporary listener and the phone's browser.

**What makes it different**

- It finds the layer, not a guess: a refusal, a silent drop and "no route" are different faults and it tells them apart.
- It tests both directions. A device that blocks inbound connections looks fine from its own side.
- It works for whichever sharing tool you use. It does not recommend, compare or name tools.
- Rules built in: it never asks you to turn a firewall off (it opens one port for one profile), never asks for
  secrets, changes one thing at a time and re-tests, and says "check your OS version" where menus differ.

**Where it stops.** It cannot see inside the sharing tool or the router's admin page. It tests TCP only, so a UDP
fault needs a second look. It cannot test another device unless you run the script there. Round-trip figures are
TCP connect times judged against rules of thumb.

## See it in action

**Request:** "My laptop can't reach my desk PC on port 7001, but the desk reaches the laptop fine. Same router.
What's wrong?"

**Result** (run in a Linux lab with two network namespaces standing in for the two devices, and one firewall rule
on the desk; see `examples/sample-session.md`):

**Verdict:** your desk PC drops inbound connections on TCP 7001. The router is not the cause.

**Evidence:**

| from \ to | laptop | desk |
|---|---|---|
| laptop | - | filtered |
| desk | ok | - |

Both are on `192.168.50.0/24`. Laptop to desk: port 7001 timed out after 1 s. Desk to laptop: port 7001 open in
1.1 ms, 20 of 20 samples answered, median 0.08 ms, p95 0.09 ms, jitter 0.01 ms. A listener on the desk for 7 s
saw no connection from the laptop. One direction works and the other is silent on one subnet, so the fault is on
the target of the failing direction. A router fault would break both ways.

**The fix:** on the desk, allow inbound TCP 7001 from the home subnet only. In the lab that was
`iptables -I INPUT 1 -p tcp --dport 7001 -s 192.168.50.0/24 -j ACCEPT`. On Windows it is one inbound firewall rule
for port 7001 on the Private profile; on macOS the Firewall options pane for the app; on Linux
`ufw allow from 192.168.50.0/24 to any port 7001 proto tcp` (check your OS version for menu paths). The firewall
stays on.

**Re-test:** the same `peer` command from the laptop now reports port 7001 `open` in 1.5 ms, and the report says
both directions work.

**What I could not check:** the router's admin page, the inside of the sharing tool, and UDP traffic.

## Limitations

- It finds the layer that is broken. It cannot see inside the sharing tool or the router's admin page.
- TCP only. A tool that also needs UDP can still fail after every TCP test passes.
- It cannot test a device unless you run the script on it. Phones and tablets are tested from a computer.
- Round-trip figures are TCP connect times judged against stated rules of thumb. They are not a measurement of the tool.
- The macOS and Windows code paths were not run on real machines. Their parsers are tested against sample text.

## FAQ

**Which sharing tools does it support?** Any. It tests the network between your devices and the port your tool
uses, which you read from the tool's own settings. It does not name, recommend or compare tools.

**Does it change my settings?** No. It only measures. It tells you the one setting to change, and you change it.

**Will it ask me to turn off my firewall?** Never. It opens one port for one profile instead.

**Does it need an account or an API key?** No. Python 3.10+ and nothing else.

**Can it test my phone?** From a computer, yes: it runs a temporary listener and you open its address in the phone's
browser, or you start the sharing app on the phone and the computer tests that port.

**Which agents does it work with?** Any agent that supports SKILL.md and can run a Python script.

## Use cases

- Working out why two computers on the same Wi-Fi cannot reach each other
- Finding the layer that breaks shared mouse, clipboard or file drop
- Checking a phone or tablet against a computer for local network permission and background limits
