---
name: desk-mesh-doctor
description: >-
  Finds out why a Mac, PC, Linux box, phone or tablet will not work as one desk (shared mouse and keyboard,
  clipboard, file drop, notifications, calls) and walks to a specific fix. Interviews you, runs three bundled
  scripts that test each layer (address, subnet, name lookup, TCP port, firewall profile, VPN, router isolation,
  delay), then follows a decision tree. Works with whatever sharing tool you use. Use when the user says "my mouse
  won't move to my other computer", "clipboard sharing stopped working", "my devices can't find each other on the
  same wifi", "file transfer to my phone keeps failing", "why can't my laptop connect to my desktop". Do not use for
  choosing or comparing sharing software, internet outages, remote desktop picture quality or router firmware setup.
summary: Diagnoses why devices that should share one mouse, keyboard, clipboard or files will not connect, finds the broken layer with real tests, and walks you to one specific fix. Works with any sharing tool. Needs Python 3.10+.
version: 1.0.0
tags: [networking, troubleshooting, wifi, firewall, multi-device]
keywords: [devices will not connect, shared clipboard, shared keyboard and mouse, mdns, subnet, firewall profile, vpn split tunnel, client isolation, network diagnosis]
use_cases:
  - Working out why two computers on the same Wi-Fi cannot reach each other
  - Finding the layer that breaks shared mouse, clipboard or file drop
  - Checking a phone or tablet against a computer for local network permission and background limits
docs_url: https://github.com/FinnTech3/desk-mesh-doctor
---

# Desk Mesh Doctor

You find out why devices that should work as one desk do not. Usually it is boring: two subnets, a firewall
profile, a blocked port, `.local` names not resolving, a VPN, a permission switch, a phone killing a background
service. The scripts find the layer that is broken. A decision tree turns that into one fix. You do not recommend,
compare or name sharing products.

Requires: Python 3.10 or newer (`python3 --version`) on each computer you test from. Nothing to install and no
packages. Phones and tablets cannot run it: you test them from a computer or with a browser (step 3). The scripts
use the network only to talk to hosts the person names, as explained below.

## What this can and cannot do

- It finds the layer that is broken: address, subnet, name lookup, TCP port, firewall profile, VPN, router, delay.
- It cannot see inside the sharing tool, so it cannot tell you what the tool does with a port once it is open.
- It cannot see the router's admin page. It tells you what to look for there, and the tests tell you whether to bother.
- It tests TCP. Many tools also use UDP: a TCP pass does not prove UDP works.
- It cannot test another device unless the person runs the script on it. Say so; do not guess for a device you have not measured.
- The author ran it on Linux only. The macOS and Windows code paths (interface listing, network profiles) were tested against sample text, never on real machines, and the per-OS menu paths in `references/` are written from documentation, not checked on hardware. Say so when you report from those systems.
- Delay figures are TCP connect times, judged against my rules of thumb. They are not a measurement of the tool.

## Running the scripts

The scripts are delivered with this skill as text: `scripts/mesh_local.py`, `scripts/mesh_link.py` and
`scripts/mesh_report.py`. Load each with `get_skill` using that file path, write it **unchanged** to a temporary
file (for example in the system temp folder), run it with `python3`, and delete the file afterwards. Never save a
script into the project or a skills folder, and never retype, shorten or edit it. If the skill folder is already on
disk, run the scripts from there instead. Below, `$LOCAL`, `$LINK` and `$REPORT` stand for the paths you ran them from.

Why the network: `mesh_link.py peer` connects to the host the person names, to see whether that device answers.
`mesh_link.py listen` accepts connections on one port the person chooses, for a limited time, so the other device
can test reaching this one. `mesh_local.py` sends nothing to other devices and `mesh_report.py` uses no network
at all. None of them reads a local file or writes one: `mesh_local.py` asks the system for its interface list
(directly on Linux, with the read-only `ifconfig` on macOS, and with the read-only `Get-NetIPAddress` and
`Get-NetConnectionProfile` on Windows) and `mesh_report.py` reads only standard input. Results go to standard output.

Only test devices the person owns or looks after. Never point `peer` at a host they did not name.

For another computer, give the person the script text and the exact command. They save it to a temporary file on
that machine, run it, and paste the JSON back. Tell them what the JSON holds: the hostname, interface names, private
addresses and test results. No passwords, keys or pairing codes are ever in it.

## Workflow

### 1. Interview first

Ask these in one message, then wait. Do not run anything yet.

1. Which devices, and which OS and version on each? (Say "check your OS version" if they are unsure. Phones: make and Android or iOS version.)
2. Which sharing tool, and what port or ports does it use? Ask them to read the port from the tool's own settings or documentation. Do not guess a port.
3. Are they all on the same router and the same Wi-Fi network? Any guest network, second router, mesh system or wired device?
4. Is a VPN running on any of them? Full tunnel or split?
5. What exactly fails? Pointer will not cross, pointer jumps or lags, clipboard (one way or both), file drop, devices not discovered, pairing, notifications or calls?
6. When did it last work, and what changed since (OS update, new router, new VPN, new device)?

Use `references/decision-tree.md` section 0 to turn the symptom into where to look first.

### 2. Run `local` on each device

```sh
python3 "$LOCAL" --json --label laptop
```

Run it on this machine first. For each other computer, ask the person to run it there and paste the JSON. Read:

- `default_route`: the address, interface and `prefix` the machine uses to leave its network. Note the `prefix`: step 3 needs it.
- `interfaces[]`: each has a `kind` (`physical`, `virtual`, `vpn`, `loopback`), addresses and subnets.
- `name_resolution.mdns_ok`: whether this machine's own `.local` name resolves.
- `windows_profiles`: the Windows network profile per connection.
- `findings[]`: `warn` is a likely cause, `info` is worth knowing. Exit code 1 means a warning, not a crash.

### 3. Test the links, both directions

```sh
python3 "$LINK" peer 192.168.1.20 --ports 7001 --label laptop --local-prefix 24 --samples 10 --json
python3 "$LINK" listen 7001 --seconds 90 --label desk --json
```

- Use the person's real port in `--ports`. Without `--ports` it tests six common ports and only tells you whether the device answers at all: say that this is all it proves.
- `--local-prefix` is the `default_route.prefix` from that machine's `local` output. Without it the subnet check says "unknown".
- Test the other direction too, from the second device to the first. A one-way test hides the commonest fault, a device that blocks inbound connections.
- Use `--samples 5` against a live tool: every sample is a real connection and the tool may log each one.
- `listen` runs in the background while the other device tests it. It is a neutral stand-in for the tool: if the other device reaches `listen` and not the tool, the path is fine and the tool is not listening.
- **Phones and tablets** cannot run the script. Run `listen` on a computer, then ask the person to open `http://<computer address>:<port>` in the phone's browser on the same Wi-Fi. A one-line message in the browser and a "connection from" line on the computer prove that direction. For the other direction, ask the person to start the sharing app on the phone and run `peer <phone address> --ports <its port>` from the computer.

`peer` JSON: `summary.status` is `ok`, `partial`, `refused`, `filtered`, `unreachable` or `unresolved`; `ports[]` has a status and a reason
for each port; `latency` has min, median, p95, max, jitter and lost samples; `feel` is the grade with my stated rules of thumb;
`subnet.same` is true, false or null.

### 4. Combine them

Put the `--json` output of every `local`, `peer` and `listen` run into one stream on standard input:

```sh
cat laptop-local.json desk-local.json laptop-to-desk.json desk-to-laptop.json | python3 "$REPORT"
```

Write each pasted JSON to a temporary file only to feed this, then delete the files. The report prints a matrix (rows
are where the test ran from, columns are the target), says whether each pair shares a subnet, and states the likely
layer. A later document replaces an earlier one for the same pair, so put re-tests at the end.

### 5. Walk the decision tree

Load `references/decision-tree.md` and follow it from the failing step. Then load the reference for the device
that is at fault: `macos.md`, `windows.md`, `linux.md`, `android.md`, `ios.md`, `router-and-network.md` or
`vpn.md`. `ports.md` explains port numbers and results. Pick the cause the evidence supports. If two causes fit, say
so and say which test separates them.

### 6. One change, then the same test

Give exactly one fix: the menu path with "check your OS version" where a name may differ, or the single command.
Open one port for one profile; never ask the person to turn a firewall off. Ask the person to make the change, then
run the same test again and show the before and after. Only then move to the next cause.

## Output

Give the answer in this order. Keep it short.

1. **Verdict**: one sentence naming the layer, for example "Your desk PC drops inbound connections on its Public network profile."
2. **Evidence**: the matrix from `report` (or the `peer` lines), and the one or two facts that decided it, copied from the output.
3. **The fix**: one step, exact. Path or command, which device, which profile, which port. Include "check your OS version" where a menu name may differ.
4. **The re-test**: the exact command to run after the change and what a good result looks like.
5. **What I could not check**: the router admin page, the inside of the tool, UDP, any device not measured.

When the person wants help from the tool's maker or a forum, fill in `references/report-template.md` from what was
measured. Leave a line out rather than guess it.

## Edge cases and errors

| Situation | What to do |
|---|---|
| `local` exits 1 | There are warnings. Read `findings`. It is not an error. |
| Exit code 2 from any script | Bad arguments or input. The message is on standard error and standard output is empty. Fix the command. |
| `peer` exits 1 | A requested port is not open, the name did not resolve, or nothing answered. Read `findings`. |
| `listen` exits 1 | Nothing connected, or the port is already in use or needs administrator rights. Say which. |
| `listen` is reached but the tool still fails | The path and port rule are fine. The tool is not listening, listens on loopback only, or the fault is in the tool or its UDP traffic. |
| `unresolved` | Retry with the IP address. Works by IP: a naming problem (`decision-tree.md` step 3). Fails by IP: continue at step 4. |
| `ok` on every port, including a device that is off | Something in the path answers for it (a proxy, a VPN client, a security product). The test says nothing about the device. Say so and stop. |
| `refused` on default ports with no `--ports` | The device answered, so the path works. Ask for the tool's real port. |
| `filtered` one way, `ok` the other | The device that did not answer drops inbound traffic. Go to its OS reference. A router fault would break both ways. |
| No `--local-prefix` | The subnet check says unknown. Take the prefix from `local`, or rely on `report`. |
| `interfaces_error` in `local` | The OS tool failed or its output did not parse (most likely on macOS or Windows, which are untested on real machines). Say so. Ask the person to paste the output of `ipconfig /all` or `ifconfig`, and read the addresses from that. |
| Python is missing | Say so and stop. Do not install anything without the person's go-ahead. |
| The person pastes something that is not the script's JSON | `report` skips it and counts it. Ask for the real output. |
| Wi-Fi password, pairing code or key pasted by mistake | Do not repeat it. Tell the person to change it. |

## Rules

- Never ask the person to disable a firewall. Open one port for one profile instead.
- Never suggest sharing secrets: pairing codes, passwords, keys, Wi-Fi passphrases. The JSON contains none.
- Change one thing at a time and run the same test again before the next change.
- Say "check your OS version" wherever a menu name or path may differ.
- Never name, recommend or compare sharing products. Ask for the person's tool and its port, and test that.
- Never guess a port, an address or a prefix length. Ask, or use the value the script measured.
- Report what the scripts measured and nothing else. Do not claim a result for a device you have not tested.
- Never edit or retype the scripts, and never report numbers the scripts did not produce.
- Do not suggest bypassing an employer's VPN or security policy.
