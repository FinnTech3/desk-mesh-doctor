# Port reference

Well-known service ports only, with the standard that owns each one. I deliberately do not list the ports of any
sharing tool: they are not mine to guess. Ask the person to read the port from the tool's own settings or
documentation, and test that exact number.

`mesh_link.py` tests TCP. UDP rows are here so you can recognise them in a firewall list, not because the script
can test them.

| Port | Protocol | Service | Standard or owner |
|---:|---|---|---|
| 22 | TCP | SSH | IANA, RFC 4253 |
| 53 | UDP and TCP | DNS | RFC 1035 |
| 67, 68 | UDP | DHCP server, DHCP client | RFC 2131 |
| 80 | TCP | HTTP | RFC 9110 |
| 123 | UDP | NTP | RFC 5905 |
| 137, 138, 139 | UDP, UDP, TCP | NetBIOS name, datagram, session | IANA, RFC 1002 |
| 443 | TCP (and UDP for QUIC) | HTTPS | RFC 9110, RFC 9000 |
| 445 | TCP | SMB file sharing | IANA (microsoft-ds), Microsoft protocol documents |
| 548 | TCP | AFP file sharing | IANA |
| 631 | TCP and UDP | IPP printing | RFC 8010 |
| 1900 | UDP | SSDP, UPnP discovery | UPnP Device Architecture |
| 3389 | TCP and UDP | RDP | Microsoft protocol documents |
| 3702 | UDP | WS-Discovery | OASIS |
| 5353 | UDP | mDNS (`.local` names and service discovery) | RFC 6762 |
| 5355 | UDP and TCP | LLMNR | RFC 4795 |
| 5900 | TCP | VNC, the remote framebuffer protocol | RFC 6143 |
| 8080 | TCP | Alternate HTTP, a convention rather than a standard | IANA lists it as http-alt |

## Ranges

| Range | What it is |
|---|---|
| 1 to 1023 | System ports. Listening on one usually needs administrator or root rights |
| 1024 to 49151 | Registered ports. A sharing tool's own port will normally be here |
| 49152 to 65535 | Dynamic or ephemeral ports: what the connecting side uses for its end |

## Discovery addresses

| Address | Used for |
|---|---|
| `224.0.0.251` and `ff02::fb` | mDNS multicast groups (UDP 5353) |
| `239.255.255.250` | SSDP multicast group (UDP 1900) |
| `169.254.0.0/16` and `fe80::/10` | Link-local: the device got no DHCP address, or it is IPv6 on-link |
| `100.64.0.0/10` | Shared address space (RFC 6598): carrier NAT and some overlay VPNs |

Multicast and broadcast stay inside one subnet unless the router is told to relay them.

## What a result means for a port

| `mesh_link.py` status | Meaning |
|---|---|
| `open` | Something accepted the TCP connection |
| `refused` | The device answered and nothing listens, or its firewall rejects instead of dropping |
| `timeout` | No answer: dropped by a firewall, wrong address, asleep, or isolated by the router |
| `unreachable_network` or `unreachable_host` | The network told this machine there is no route |
| `blocked_local` | This machine's own firewall or permission rules stopped the attempt |
