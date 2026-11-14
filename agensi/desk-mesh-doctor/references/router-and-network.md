# Router and network checklist

I cannot see the router's admin page. This file tells the person what to look for, and the `peer` and `report`
results tell them whether to bother. Setting names differ by brand and firmware: give the common names and say
that the exact label varies.

## Client isolation (the most common router cause)

Also called AP isolation, client isolation, wireless isolation or "isolate clients". When it is on, devices joined
to the same Wi-Fi network cannot talk to each other. They can still reach the internet, which is why nothing looks
wrong.

Evidence: both directions `filtered`, `same subnet` in the report, firewalls ruled out. A device on the cable and
a device on Wi-Fi may talk fine while two Wi-Fi devices cannot.

Where: the Wi-Fi settings of the router, per network or per band. Guest networks switch it on by default and
often cannot switch it off.

## Guest and IoT networks

A guest network is a separate network with its own subnet. Devices on it cannot reach devices on the main network.
The report shows `different subnets`. Move the device to the main network; do not weaken the guest network.

## Double NAT and second routers

Two routers both handing out addresses make two subnets, with the second router's devices hidden behind it.
`local` shows an address on a different private range from the other device (for example `192.168.0.x` against
`192.168.1.x`). Put the second router into access-point or bridge mode, or connect everything to one router.

## Mesh Wi-Fi

Nodes of one mesh system normally share one subnet. If a node was set up as a separate router, or if there is a
"guest" or "IoT" network, it will not. Compare the subnets with `report`.

## Multicast and mDNS

Name discovery (`.local`) and many "find devices" screens use multicast. If the IP address works and the name does
not, look for:

- **IGMP snooping** on a managed switch or router. Misconfigured, it drops multicast to ports that did not ask
  for it. Switching it off, or enabling the router's IGMP querier, is the usual fix on a small network.
- **Multicast to unicast conversion** or "multicast enhancement" on Wi-Fi: can help or hurt. Test both ways.
- **Wi-Fi to cable bridging** that blocks multicast between the two sides.
- **An mDNS gateway or repeater** on routers that offer one. Needed only when devices sit on different subnets
  and you want names to work between them. Some brands call it Bonjour or service discovery.

## DHCP

- A DHCP **reservation** keeps a device's address steady. Tie it to the device's current Wi-Fi address (see the
  private-address notes in `ios.md`, `android.md` and `macos.md`).
- A short **lease time** plus a sleeping device can mean the address changes under a tool that remembers the old one.
- Two DHCP servers on one network hand out conflicting subnets: the "double NAT" case again.

## Wi-Fi quality (when the numbers are bad, not the path)

- **Band.** 5 GHz is faster and shorter range. 2.4 GHz reaches further and is crowded. A device on 2.4 GHz with a
  busy neighbourhood shows high jitter.
- **Distance and walls** raise latency and loss. Test beside the router first.
- **Wi-Fi power saving** on a device adds latency spikes (see `linux.md` and `windows.md`).
- **Cable.** A wired computer is the cheapest improvement: run `peer` to a wired device and compare.

## Networks you do not control

Offices, campuses, hotels and cafes usually switch client isolation on and cannot be changed. Say so plainly. Two
options that need no admin access: a direct cable between two computers, or both devices joined to a phone's
hotspot. Test the hotspot with `report`: some hotspots isolate clients as well.
