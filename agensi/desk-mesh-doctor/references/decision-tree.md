# Decision tree

Work top to bottom. Stop at the first step that fails. Change one thing, run the same test again, and only then
move on. The scripts name the layer; the fix is a setting on a device or a router that I cannot see, so every fix
below ends with the test that proves it.

Menu names change between OS versions. Where a path is given it is the usual one for current releases: tell the
person to check their OS version and look for the nearest match.

## 0. Start from the symptom

| What fails | Look at first | Why |
|---|---|---|
| Devices never appear in each other's lists, pairing by name fails | Step 2 (subnet), step 3 (names) | Discovery uses broadcast or multicast, which stops at a subnet edge and at some routers |
| Pairing by IP address works, name does not | Step 3 | `.local` needs multicast DNS on both devices |
| Pointer will not cross to the other machine | Step 4, then step 6 | Needs a live connection first, then an OS permission to capture and inject input |
| Pointer crosses but jumps, stutters or lags | Step 5 | Round trip time and jitter, usually Wi-Fi |
| Clipboard works one way only | Step 4 (asymmetry), step 6 | One device blocks inbound connections |
| File drop starts then stalls or fails | Step 5, then step 4 on the file port | Bulk transfer is the first thing a weak Wi-Fi link or a second port rule breaks |
| Phone notifications or calls stop after a while | Step 7 | Background limits on the phone, not the network |
| Worked yesterday, not today | Step 7 | Something changed: address, VPN, update, sleep |

## 1. Does each device have a usable address?

Evidence: `local` finding `no_address`, or only `169.254.x.x` / `fe80::` addresses.
Cause: the device joined the network but got no DHCP lease. Nothing above this layer can work.
Check: is it on the right Wi-Fi network, is the router's DHCP server on, is the cable seated.
Fix: reconnect to the network; restart the router only if several devices lost addresses.
Re-test: `local` again. The default route should now have a private address.

## 2. Are the devices on the same subnet?

Evidence: `report` pair line says `same subnet` or `different subnets`, or `peer` shows `subnet:`.
Different subnets with the devices on "the same Wi-Fi" means one of these:

- One device is on a guest network or an IoT network. Move it to the main network.
- Two routers each hand out addresses (double NAT). Put the second one in access-point mode, or join both
  devices to the same router. See `router-and-network.md`.
- A VPN gave one device a tunnel address. See `vpn.md`.
- The Wi-Fi band split (2.4 GHz and 5 GHz) is on separate networks with separate names. Join the same one.

Connections can still route across subnets. Discovery usually does not: add the other device by IP address.
Re-test: `local` on both, then `report`. It should say `same subnet`.

## 3. Does the name resolve?

Evidence: `peer` status `unresolved`, or `local` finding `mdns_unresolved` while the IP address works.
Method: run `peer` against the name, then against the IP address. IP works and the name does not: it is naming,
not the network.

Fixes, in order:

1. Use the IP address in the tool, and give the device a fixed address or a DHCP reservation so it stays put.
2. Linux: install and start the mDNS responder and name service (see `linux.md`).
3. Windows: set the network to Private (see `windows.md`).
4. Router: multicast or mDNS filtering, IGMP snooping, client isolation (see `router-and-network.md`).
5. VPN: a VPN that sends all DNS through the tunnel will not resolve `.local` (see `vpn.md`).

## 4. Can each device reach the other by TCP?

Run `peer` from each device to the other, on the port the person's tool uses (ask for it, never guess). Read
`summary.status` for each direction, then read the matrix from `report`.

| Result | What it means | Next |
|---|---|---|
| `ok` both ways | The TCP path is fine | Step 5, then step 6 |
| `refused` | The device answered and nothing listens on that port | Tool not running there, wrong port, tool bound to the loopback address only, or the device is asleep and woke into a different state. Linux: `ss -ltn`. Windows: `netstat -ano`. Start or restart the tool on that device and test again |
| `filtered` (timeout) both ways | Packets are dropped or never arrive | Same subnet: suspect client isolation or a guest network first, then both firewalls. Different subnets: routing, VLAN or VPN. Also confirm the address and that both devices are awake |
| `filtered` one way, `ok` the other | The device that did not answer drops inbound traffic; the router would have broken both ways | Firewall or network profile on that device: `windows.md`, `macos.md`, `linux.md`. Open one port, for one profile |
| `unreachable` | No route to that address | Wrong address, different network with no route, or a VPN taking the route |
| `unresolved` | Name did not resolve | Step 3 |
| `partial` | Some tested ports answer and some do not | The tool probably uses a port that was not tested. Test its real port |

macOS stealth mode and some Linux or Windows firewall rules answer closed ports with silence instead of a refusal.
So a `filtered` result on a port nothing listens on can still be "the firewall is stricter than I thought", not
"the device is unreachable". Test with `listen` on that port to tell them apart: if `listen` is reached, the path
and the port rule are fine and the tool is simply not listening. If it is not reached, remember that a rule tied
to one program does not cover the script: allow the test port the way you would allow the tool's port.

If every port answers `open` for an address that cannot be right (a device that is switched off), something in the
path is answering for it: a transparent proxy, a VPN client or a security product. The test then says nothing about
the device. Say so and stop.

## 5. Is the delay acceptable?

Evidence: `peer` latency block and `feel`. My thresholds are rules of thumb, not a standard: median under 10 ms
with p95 under 30 ms is good, 25 and 60 is usable, 50 and 120 is laggy.

- High median on Wi-Fi: move closer, use 5 GHz, wired is better. See `router-and-network.md`.
- Good median, high p95 or jitter: Wi-Fi power saving on one device, a busy channel, or a VPN hairpin. Test with
  the VPN paused. Linux power save: `linux.md`. Windows adapter power management: `windows.md`.
- Lost samples: that is loss, not latency. Weak signal, interference, or an overloaded link.
- The numbers are TCP connect times. They include the operating system, not the tool, so they are a fair floor
  and nothing more.

## 6. The TCP path is fine and the tool still fails

I cannot see inside the tool. These are the usual remaining layers:

1. **UDP.** This skill tests TCP only. Many tools also use UDP for pointer input. A firewall or router can treat
   UDP differently. Ask which UDP ports the tool uses and check the same firewall rule covers them.
2. **OS permissions.** Capturing and injecting input needs permission switches on macOS (`macos.md`), a
   non-elevated window cannot control an elevated one on Windows (`windows.md`), and Wayland blocks global input
   by design (`linux.md`). Phones need local network and background permission (`android.md`, `ios.md`).
3. **Version mismatch.** Two different versions of the tool on the two devices. Ask for both versions.
4. **Pairing state.** A device was reinstalled or its address changed and the old pairing is stale. Re-pair; never
   paste pairing codes or keys into the chat.

## 7. It worked, then stopped

| Clue | Likely cause |
|---|---|
| After the laptop slept | Wi-Fi dropped, address changed, or the tool did not reconnect. Run `local` and `peer` again |
| Phone side only, after minutes with the screen off | Battery optimiser or background limit (`android.md`), or iOS suspending the app (`ios.md`) |
| After an OS update | Permission switches reset, firewall profile changed, a Wayland session replaced an X11 one |
| After joining a VPN | Route or DNS captured (`vpn.md`) |
| After changing router or Wi-Fi name | New subnet, guest network, or devices on different networks |
| Phone address keeps changing | Private or random Wi-Fi addresses (`ios.md`, `android.md`): a router reservation tied to the old address no longer matches |
