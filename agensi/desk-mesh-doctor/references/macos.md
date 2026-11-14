# macOS checklist

Menu names move between releases. Before giving a path, ask for the macOS version, and say "check your OS
version" if you are not sure the path matches. Current releases use System Settings; older ones use System
Preferences with similar panes.

These steps come from documentation and were not checked on a real macOS machine. If the person's screen differs, trust the screen.

## Permission switches (the usual reason the pointer or keyboard does nothing)

These live under Privacy & Security. A tool that shares a mouse and keyboard needs some or all of them, and macOS
asks only once. If the person clicked "Don't allow", the prompt never returns: they have to switch it on by hand.

| Pane | What it allows | Symptom when it is off |
|---|---|---|
| Accessibility | Controlling the computer: injecting pointer and key events | Pointer arrives on this Mac and does not move, keys do nothing |
| Input Monitoring | Reading keyboard and pointer input from other apps | The Mac cannot capture its own input to send it away |
| Screen Recording | Capturing the screen | Screen sharing is black or empty |
| Local Network | Reaching devices on the local network. Shown on recent macOS versions only: check your OS version | The tool cannot connect to anything on the LAN while the internet works |

After switching one on, quit and reopen the tool: some permissions apply only to a fresh launch. If a tool is
listed but not working after an update, remove it from the list with the minus button and add it again.

## Firewall

System Settings, Network, Firewall (older releases: Security & Privacy, Firewall).

- "Block all incoming connections" must be off, or nothing can connect in.
- With the firewall on, macOS asks the first time an app tries to accept connections. "Allow" adds a per-app
  rule. If the person clicked "Deny", open Firewall options and set that app to "Allow incoming connections".
- Stealth mode makes the Mac ignore connection attempts to closed ports instead of refusing them. A closed port
  then looks `filtered` in `mesh_link.py` instead of `refused`. It is a fair setting; it only changes how a failure
  looks.

Read-only checks that need no administrator rights:

```
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
/usr/libexec/ApplicationFirewall/socketfilterfw --getstealthmode
```

Changing firewall rules from a terminal needs an administrator. Prefer the Firewall options pane: one app, one
rule. Do not ask the person to turn the firewall off.

## Network

- **Private Wi-Fi Address.** Newer macOS versions can use a different Wi-Fi address per network, or rotate it.
  A router reservation or a MAC allow list tied to the old address stops matching. Wi-Fi, details for the
  network, Private Wi-Fi Address: Fixed is steadier than Rotating at home (check your OS version).
- **Sleep.** A sleeping Mac does not answer. Check Battery or Energy settings for "Prevent automatic sleeping" and
  "Wake for network access". A `timeout` on a laptop with its lid closed is not a firewall.
- **Names.** `.local` names work out of the box through mDNS. If the Mac does not resolve a `.local` name that
  another device does, suspect a VPN or a router that filters multicast.
- **Several adapters.** USB Ethernet dongles, tethering and bridges give the Mac more than one address. `local`
  lists them all; make sure the tool is using the one on the shared subnet.

Useful read-only commands:

```
ifconfig                          # addresses and prefix lengths
networksetup -listallhardwareports
route -n get 192.168.1.20         # which interface a destination would use
scutil --dns                      # which DNS servers apply, and whether a VPN took over
```

## When the Mac is the device that will not accept connections

1. `local` on the Mac: does it have a private address on the same subnet as the other device?
2. `peer` from the other device to the Mac on the tool's port. `filtered`: firewall or stealth mode. `refused`:
   the tool is not running or listens elsewhere.
3. Fix the one thing found, and run the same `peer` again.
