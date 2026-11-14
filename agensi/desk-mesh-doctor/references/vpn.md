# VPN and split tunnelling

A VPN adds a virtual network adapter and changes the routing table. Anything that changes which route a packet
takes can hide your other devices: local devices live on the local network, and a VPN that sends everything
through the tunnel sends the packets away from it.

`mesh_local.py` finds tunnel-looking adapters by name (for example `tun0`, `utun3`, `wg0`, `ppp0`, `tap`, or a
name containing "vpn"). It also notes addresses in `100.64.0.0/10`, which carrier NAT and some overlay VPNs use. It
raises `vpn_default_route` when the default route leaves through such an adapter.

## What a VPN can break

| Symptom | Cause |
|---|---|
| Both directions `filtered` to a device that is clearly on the same network | A full tunnel sends the local subnet's packets into the tunnel |
| `.local` does not resolve | DNS goes through the tunnel and mDNS multicast is not forwarded |
| Works with the VPN off | Routing or DNS capture. Not a firewall |
| One device is `ok` to the other and the reverse fails | Only one of them is running the VPN |
| Latency doubles | The path goes out to the VPN server and back to reach a device in the next room |

## Checks

Show the route a destination would take:

- Linux: `ip route get 192.168.1.20`
- macOS: `route -n get 192.168.1.20`
- Windows: `route print`, or PowerShell `Find-NetRoute -RemoteIPAddress 192.168.1.20`

If the interface shown is the tunnel, the VPN is capturing local traffic.

## Fixes, least invasive first

1. **Look for a local network setting in the VPN client.** Common names: "allow local network access", "LAN
   access", "exclude local network", "bypass LAN". Turn it on and test again.
2. **Use split tunnelling** so only the networks you need go through the VPN.
3. **Pause the VPN** on the devices for a test, then compare `peer` results with and without it. This proves the
   cause. Only do it if the person is allowed to: do not suggest bypassing an employer's security policy. A work
   laptop that must stay on the corporate VPN is a case for a second device, not a workaround.
4. **If both devices use the same overlay VPN,** its addresses reach across networks. Use those addresses in the
   tool. Then check the latency: the path may be indirect.
5. **A kill switch** blocks all traffic outside the tunnel, local traffic included. That is the setting doing its
   job. Ask for the VPN client's local network option rather than turning the kill switch off.

## What I cannot see

The VPN client's rules, the provider's server, and any policy pushed by an organisation. I can show where the
route goes and which test fails.
