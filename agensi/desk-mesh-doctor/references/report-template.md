# Report to paste

Use this when the person wants to ask the maker of their sharing tool, a forum or a support desk for help. Fill it
in from what was actually measured. Leave a line out rather than guess it.

Never include pairing codes, passwords, keys, Wi-Fi passphrases or licence keys. Private addresses such as
`192.168.x.x` are fine to share. If the person would rather not share addresses, replace the last number with `x`.

```
## Setup
Devices: <name: OS and version, how it connects (Wi-Fi 5 GHz, Wi-Fi 2.4 GHz, cable)>
Router: <make and model if known>. Same router for all devices: <yes or no>. Guest network involved: <yes or no>
VPN: <none, or which device runs one and whether it is full or split tunnel>
Sharing tool: <name and version on each device>, port or ports it uses: <from its settings or documentation>

## What fails
<one sentence: pointer, clipboard, file drop, discovery or notifications>
Started: <when it last worked, and what changed since>

## What I measured (desk-mesh-doctor)
<paste the matrix from the report>
Subnets: <same or different, with the subnet>
Name resolution: <.local resolves on each device: yes or no; IP address works: yes or no>
Round trip on the tool's port: <median, p95, jitter in ms, and samples lost>
Findings: <the warn lines from `local` on each device>

## What I changed, one at a time
1. <change> -> <result of the same test>
2. <change> -> <result>

## What I could not check
<the router admin page, the inside of the tool, UDP traffic, devices I could not run the scripts on>
```
