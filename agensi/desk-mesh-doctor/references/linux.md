# Linux checklist

Distributions differ. Ask which distribution and release, whether the desktop is GNOME, KDE or something else,
and say "check your OS version" where a tool or menu may not exist. Commands that change firewall rules need root:
use the person's usual way of running a command with administrator rights, and give the exact command, once.

## X11 or Wayland

```
echo $XDG_SESSION_TYPE
```

- `x11`: applications can read and inject input and the clipboard globally. Most mouse-and-keyboard sharing tools
  were written for this.
- `wayland`: by design, an ordinary application cannot inject input into other windows, read other windows or
  watch the keyboard globally. A tool must use what the desktop offers instead (a remote-desktop portal, or the
  compositor's own input-emulation interface). Whether a given tool does that is the tool's business, and I cannot
  see it.

If the pointer or keyboard arrives and does nothing on a Wayland session, the quick test is to log out, pick an X11
session on the sign-in screen (the gear or session menu), and try again. That is a test, not a recommendation to
stay there. Clipboard sharing can also be limited on Wayland when the tool runs in the background.

## Is the tool listening, and on which address?

```
ss -ltn
ss -ltnp 'sport = :7001'
```

`0.0.0.0:7001`, `*:7001` or `[::]:7001` means all interfaces. `127.0.0.1:7001` means loopback only: no other
device can reach it. Nothing listed means the tool is not running or uses another port.

## Firewall tools

Find out which one is active before touching anything: `ufw status`, `firewall-cmd --state`, `nft list ruleset`.
Open one port, from the home subnet only, instead of turning anything off.

| Tool | Check | Open one TCP port to the local subnet only |
|---|---|---|
| ufw | `ufw status verbose` | `ufw allow from 192.168.1.0/24 to any port 7001 proto tcp` |
| firewalld | `firewall-cmd --get-active-zones` | `firewall-cmd --zone=home --add-port=7001/tcp --permanent`, then `firewall-cmd --reload` |
| nftables | `nft list ruleset` | add an accept rule for `tcp dport 7001 ip saddr 192.168.1.0/24` to the input chain |

Replace the subnet and port with the real ones. On firewalld, check the zone applied to the network interface: a
Wi-Fi connection placed in a public zone behaves differently from one in a home zone. NetworkManager can set it:
`nmcli connection modify "<connection name>" connection.zone home`.

## Names (`.local`)

Two pieces are needed: something that answers mDNS queries for this machine, and something that makes ordinary
programs use mDNS for `.local`.

- The Avahi daemon answers and browses: `systemctl status avahi-daemon`, and `avahi-browse -a` to list what it sees.
- Name lookup through mDNS is configured in `/etc/nsswitch.conf`, on the `hosts:` line, usually through an
  `nss-mdns` package. Without it, `.local` names fail in ordinary programs even if the daemon runs.
- systemd-resolved can do mDNS itself: `resolvectl status` shows a `MulticastDNS` setting per link, and
  `resolvectl mdns <interface> yes` turns it on for that link. Do not run two mDNS responders at once: pick one.

On Debian-derived systems the machine's own hostname often resolves to `127.0.1.1` through `/etc/hosts`. A tool
that advertises "the hostname" then advertises loopback. `mesh_local.py` raises `hostname_is_loopback` for it.
Using the IP address avoids it.

## Wi-Fi power saving and the wrong interface

- `iw dev wlan0 get power_save` shows it (replace `wlan0`). Turning it off with `iw dev wlan0 set power_save off`
  (root) often removes latency spikes. Revert if it does not help.
- Container and VM bridges such as `docker0` or `virbr0` add addresses. `local` marks them `virtual`. Make sure
  the tool binds to the physical interface's address.
- `ip route get 192.168.1.20` shows which interface and route a destination would use. A VPN that took the route
  shows up there.
