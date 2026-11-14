# Windows checklist

Menu names differ between Windows 10 and Windows 11 and between builds. Ask for the Windows version, and say
"check your OS version" when a path may not match. Commands marked "administrator" need an elevated PowerShell.

These steps come from documentation and were not checked on a real Windows machine. If the person's screen differs, trust the screen.

## Network profile: Private or Public

Every network connection has a profile. It decides which firewall rules apply and whether the PC is discoverable.

| Profile | Meaning | Effect |
|---|---|---|
| Private | A network you trust, such as home | Network discovery can be on; inbound rules for Private apply |
| Public | Anything untrusted, such as a cafe | Discovery off, strictest inbound rules |
| Domain | A work network joined to a directory | Set by the organisation |

A home network that Windows labelled Public is the single most common reason one Windows PC will not accept
connections while it can connect out. `mesh_local.py` shows the profile as `windows_profiles`, and raises
`windows_public_profile` when it is Public.

Check and change it:

- Settings, Network & internet, then the Wi-Fi or Ethernet connection's properties, "Network profile type"
  (check your OS version).
- PowerShell, read only: `Get-NetConnectionProfile`
- PowerShell, administrator, one named connection: `Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private`

Only switch a network to Private if the person trusts it. A shared office or a hotel is not that network.

## Firewall: open one port for one profile

Do not ask the person to turn Windows Defender Firewall off. Add one inbound rule for the tool's port, for the
Private profile only.

- Windows Security, Firewall & network protection, "Allow an app through firewall": tick Private for the tool,
  and leave Public unticked.
- Or one rule for one port, PowerShell, administrator:
  `New-NetFirewallRule -DisplayName "Desk sharing 7001" -Direction Inbound -Protocol TCP -LocalPort 7001 -Profile Private -Action Allow`
  Replace 7001 with the tool's real port, and `TCP` with `UDP` for a UDP port.
- Read only: `Get-NetFirewallProfile` shows which profiles are enabled. `Get-NetFirewallRule -DisplayName "Desk*" | Get-NetFirewallPortFilter` shows what a rule covers.

Two traps:

1. A **Block** rule beats an Allow rule. When a first-run prompt was dismissed or answered with Cancel, check
   Windows Defender Firewall with Advanced Security, Inbound Rules, for a Block rule on the same program.
2. A rule for a program covers that program only. A rule for a port covers whatever listens there. The test
   script is a different program, so to test with `listen` use a port rule.

## Listening check

Is the tool listening, and on which address?

```
netstat -ano | findstr :7001
Test-NetConnection -ComputerName 192.168.1.20 -Port 7001
```

`LISTENING` on `0.0.0.0` or `[::]` means all interfaces. `127.0.0.1` means the tool is loopback-only and no other
device can reach it: that is a tool setting, not a network fault. `Test-NetConnection` is Windows' own TCP test
and agrees with `mesh_link.py peer`.

## Input control

- A normal window cannot send input to an elevated window (an app run as administrator) or to the UAC prompt or
  lock screen. If the pointer works everywhere except one app, ask whether that app runs as administrator.
- Sharing the keyboard to a Windows PC that is on the sign-in screen generally does not work for a tool running as
  a normal user.

## Adapter power saving

Device Manager, the Wi-Fi adapter, Properties, Power Management: "Allow the computer to turn off this device to
save power". If it is ticked and the link stutters or drops after idling, untick it for that adapter and test
again. Also check the power plan's wireless adapter setting.

## Names and discovery

Recent Windows 10 and 11 resolve `.local` names themselves. If a `.local` name fails, check the profile first
(Private), then a VPN. Virtual switches made by virtualisation or WSL appear as `vEthernet` adapters and add extra
addresses: make sure the tool uses the physical one.
