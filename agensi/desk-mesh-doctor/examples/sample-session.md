# A real session

Everything on this page is real output, captured while I built the skill. Each block is the script's own output,
copied as it came. Part 1 is this one machine talking to itself. Part 2 is a small lab I built so there were two
devices to test.

Read the limits first:

- The machine is a Linux virtual machine with no Wi-Fi and no real second device. Loopback latency (Part 1) shows
  that the tool works, not what your network is like.
- The lab in Part 2 is two Linux network namespaces joined by a virtual Ethernet cable, standing in for a laptop
  and a desk PC. Its "firewall" is one `iptables` rule. It proves the diagnosis works on a real silent drop and a
  real one-way fault. It does not prove anything about Wi-Fi, a router, Windows, macOS, a phone or UDP.
- The macOS and Windows code paths were not run on real machines. Their parsers are tested against sample text.
- An agent runs each script from a temporary file. Here they are shown as `python3 mesh_local.py` and so on.

## Part 1: one machine, on its own

### What this machine looks like

```console
$ python3 mesh_local.py
vm  (Linux 6.18.44-fc-v470, python 3.13.18, IPv6 yes)
default route: 192.0.2.2/24 on eth0
  lo             up   loopback  127.0.0.1/8 (loopback)
  eth0           up   physical  192.0.2.2/24 (private)
vm.local: does not resolve (Name or service not known)
ports: 80 free, 443 free, 445 free, 3389 free, 5900 free, 8080 free
findings:
  [info] vm.local does not resolve here. Matters only if your tool finds devices by .local name: test by IP address as well.
  [info] this machine's own name resolves only to 127.0.0.1: a peer asking for it by name gets nothing useful
```

Exit code 0. Two `info` lines and no warnings: it has a private address, a default route, and the six default
ports are free. The `.local` line is information, not a fault: it only matters if a sharing tool
finds devices by `.local` name.

### A listener and a probe

In one terminal I started a listener on port 7001. In another I probed it, plus port 7002 where nothing listens.

```console
$ python3 mesh_link.py listen 7001 --seconds 12
listening on TCP port 7001 for 12 s: test it from the other device now
  connection from 127.0.0.1 at 1.01 s
  connection from 127.0.0.1 at 1.01 s
  connection from 127.0.0.1 at 1.02 s
  connection from 127.0.0.1 at 1.03 s
  connection from 127.0.0.1 at 1.04 s
port 7001: 42 connection(s) from 127.0.0.1
findings: none
```

```console
$ python3 mesh_link.py peer 127.0.0.1 --ports 7001,7002 --samples 20
peer 127.0.0.1  from vm (127.0.0.1)
name: 127.0.0.1 in 0.0 ms
subnet: same  both are loopback: this is the same machine
  port 7001  open                     2.3 ms
  port 7002  refused                  1.8 ms
latency on port 7001: 20/20 answered, min 0.07 median 0.09 p95 0.16 max 0.43 jitter 0.05 ms
feel: good, should feel instant (rule of thumb: median/p95 under 10/30 ms good, 25/60 ok, 50/120 laggy)
findings:
  [problem] port 7002: refused. the device answered and nothing listens there (or its firewall rejects it)
```

Exit code 1. Port 7001 answered `open`. Port 7002 answered `refused`: the machine was reachable and
nothing listened there, which is a different problem from silence. The 42 connections on the listener are
two runs of the probe (one for the text above and one for a JSON copy), each one port probe plus 20 latency samples. The latency block is loopback, so
`feel: good` means the script works, nothing more.

## Part 2: two devices

The lab: a "laptop" at `192.168.50.10/24` and a "desk" PC at `192.168.50.20/24`, one subnet, joined by a virtual
cable. On the desk one rule drops inbound TCP 7001. A listener on port 7001 stands in for the sharing tool on each
device. The scenario I set up: "the laptop cannot reach the desk, but the desk reaches the laptop."

The JSON files in this folder come from a second run of the same commands, so their millisecond figures differ
slightly from the text output on this page. The reports contain no timings, so they match exactly.

### 1. This machine's view of the laptop

```console
laptop$ python3 mesh_local.py --label laptop
laptop  (Linux 6.18.44-fc-v470, python 3.13.18, IPv6 yes)
default route: 192.168.50.10/24 on vlap
  lo             up   loopback  127.0.0.1/8 (loopback)
  vlap           up   physical  192.168.50.10/24 (private)
laptop.local: does not resolve (no answer from the resolver within 2 s)
ports: 80 free, 443 free, 445 free, 3389 free, 5900 free, 8080 free
findings:
  [info] laptop.local does not resolve here. Matters only if your tool finds devices by .local name: test by IP address as well.
```

Exit code 0. It has a private address on `192.168.50.0/24`, a default route, and no
warnings. The same command ran on the desk with `--json`. The JSON is in `lab-laptop-local.json` and
`lab-desk-local.json`.

### 2. The desk listens and nothing arrives

```console
desk$ python3 mesh_link.py listen 7001 --seconds 7 --label desk
listening on TCP port 7001 for 7 s: test it from the other device now
port 7001: 0 connection(s) from nobody
findings:
  [warn] nothing reached TCP port 7001 in 7 s. Check the address and port typed on the other device, this machine's firewall (allow this one port, Private profile only) and router client isolation.
```

Nothing reached it. That is the first sign the packets die before the desk's program: a silent drop, not a
refusal.

### 3. Test both directions

```console
laptop$ python3 mesh_link.py peer 192.168.50.20 --ports 7001 --label laptop --local-prefix 24 --samples 20
peer 192.168.50.20  from laptop (192.168.50.10)
name: 192.168.50.20 in 0.0 ms
subnet: same 192.168.50.0/24
  port 7001  timeout               1002.4 ms
findings:
  [problem] Every port timed out: packets are dropped or never arrive. Check in order: same Wi-Fi and not a guest network (client isolation), a VPN capturing the route, the other device's firewall profile, and that it is awake.
```

```console
desk$ python3 mesh_link.py peer 192.168.50.10 --ports 7001 --label desk --local-prefix 24 --samples 20
peer 192.168.50.10  from desk (192.168.50.20)
name: 192.168.50.10 in 0.0 ms
subnet: same 192.168.50.0/24
  port 7001  open                     1.1 ms
latency on port 7001: 20/20 answered, min 0.05 median 0.08 p95 0.09 max 0.1 jitter 0.01 ms
feel: good, should feel instant (rule of thumb: median/p95 under 10/30 ms good, 25/60 ok, 50/120 laggy)
findings: none
```

The laptop to the desk timed out after a full second (1002.4 ms). The desk to the laptop connected in
1.1 ms and the 20 samples gave a median of 0.08 ms.

### 4. Combine them

```console
$ cat lab-laptop-local.json lab-desk-local.json lab-laptop-to-desk-blocked.json lab-desk-to-laptop.json | python3 mesh_report.py
| from \ to | laptop | desk |
|---|---|---|
| laptop | - | filtered |
| desk | ok | - |

laptop <-> desk: same subnet (192.168.50.0/24)
  [problem] laptop->desk is filtered: nothing gets through, so desk's firewall or network profile is dropping inbound connections; desk->laptop works, which points at desk, not the router.
```

Exit code 1. One direction fails and the other works, on one subnet, so the fault is on
the target of the failing direction. A router fault would have blocked both. The files are in this folder, and
`lab-report-blocked.md` holds this output.

### 5. The fix: one port, from the home subnet only

I did not turn the firewall off. I added one rule on the desk that accepts TCP 7001 from `192.168.50.0/24` and
nothing else, above the drop rule:

```console
desk$ iptables -I INPUT 1 -p tcp --dport 7001 -s 192.168.50.0/24 -j ACCEPT
desk$ iptables -S INPUT
-P INPUT ACCEPT
-A INPUT -s 192.168.50.0/24 -p tcp -m tcp --dport 7001 -j ACCEPT
-A INPUT -p tcp -m tcp --dport 7001 -j DROP
```

### 6. The same test again

```console
laptop$ python3 mesh_link.py peer 192.168.50.20 --ports 7001 --label laptop --local-prefix 24 --samples 20
peer 192.168.50.20  from laptop (192.168.50.10)
name: 192.168.50.20 in 0.0 ms
subnet: same 192.168.50.0/24
  port 7001  open                     1.5 ms
latency on port 7001: 20/20 answered, min 0.07 median 0.09 p95 0.1 max 0.13 jitter 0.01 ms
feel: good, should feel instant (rule of thumb: median/p95 under 10/30 ms good, 25/60 ok, 50/120 laggy)
findings: none
```

```console
$ cat lab-laptop-local.json lab-desk-local.json lab-laptop-to-desk-fixed.json lab-desk-to-laptop.json | python3 mesh_report.py
| from \ to | laptop | desk |
|---|---|---|
| laptop | - | ok |
| desk | ok | - |

laptop <-> desk: same subnet (192.168.50.0/24)
  [ok] both directions work
```

Exit code 0. Both directions work. The before and after reports are in
`lab-report-blocked.md` and `lab-report-fixed.md`, and a test in the repo rebuilds both from the JSON files to
make sure this page cannot drift from what the script prints.

## What the agent would say

> **Verdict:** your desk PC drops inbound connections on TCP 7001. The router is not the cause.
>
> **Evidence:** laptop to desk timed out; desk to laptop connected in 1.1 ms; both are on `192.168.50.0/24`.
>
> **The fix:** on the desk, allow inbound TCP 7001 for the Private profile only. On Windows that is one inbound
> rule (check your OS version for the menu path); do not turn the firewall off.
>
> **Re-test:** run `peer 192.168.50.20 --ports 7001` from the laptop. A good result is `open`.
>
> **Could not check:** the router admin page, the inside of the sharing tool, and UDP.
