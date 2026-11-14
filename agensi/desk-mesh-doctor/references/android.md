# Android checklist

Android menus differ by version and by maker. Ask for the Android version and the phone's make, and say "check
your OS version" when you give a path. The paths below are the stock ones: makers rename and move them.

You cannot run the scripts on a phone. Test the phone from a computer instead (see "Testing a phone" below).

## Background limits: the usual reason it works, then stops

An app that must stay connected while the screen is off competes with the system's power saving. Most "it stopped
after a few minutes" reports on a phone are this, not the network.

Check, for the sharing app, in roughly this order:

1. **Battery usage.** Settings, Apps, the app, Battery. Set it to Unrestricted (the word varies: "No restrictions",
   "Don't optimise"). The older route is Settings, Battery, Battery optimisation, then set the app to "Don't
   optimise".
2. **Adaptive or smart battery features.** These learn which apps to restrict. An app you rarely open is a
   candidate. Add the app to the "never sleeping" list if your phone has one.
3. **Maker battery managers.** Several makers add their own app-killer on top of stock Android, with names such as
   "sleeping apps", "app launch" or "protected apps". These are known to stop background services even when the
   stock setting is unrestricted. Look in the phone's battery or security settings for a per-app switch.
4. **Data saver.** Settings, Network & internet, Data Saver: allow the app "Unrestricted data". Data Saver
   restricts background data.
5. **Persistent notification.** Since Android 8, a long-running background service has to show a notification. If
   the person turned that notification off, the system may stop the service.
6. **Doze.** While the phone sits idle and unplugged with the screen off, the system defers background work and
   network access. Charging or keeping the screen on is a quick test: if it works then, it is a power rule.

Test one change at a time. After each, lock the phone for the time it used to take to fail, then run the same test.

## Local network and Wi-Fi

- **Same network.** The phone must be on the same Wi-Fi network (not the guest network, not mobile data). Some
  phones switch to mobile data when the Wi-Fi has no internet ("Adaptive Wi-Fi" or "Switch to mobile data"):
  turn that off for a LAN-only test.
- **Local network permission.** Some recent Android versions add a permission that limits an app's access to
  devices on the local network, under the app's Permissions. Check your OS version. If the permission exists and
  is off, the app cannot reach computers on the LAN while internet access works.
- **Random Wi-Fi addresses.** Android 10 and later can use a different MAC address per network. A router
  reservation made for the phone's old address stops matching. Settings, Wi-Fi, the network, Privacy: use the
  device MAC for a trusted home network (check your OS version). Fix the reservation instead if you can.
- **Hotspot.** When the phone is the hotspot, the devices joined to it are on the phone's subnet. Test with `local`
  on a joined computer.
- **Private DNS** does not affect devices on the LAN. Ignore it for this problem.
- **Battery saver and Wi-Fi sleep.** Aggressive battery saver modes can switch the Wi-Fi radio into a low-power
  state. A `timeout` that disappears when the screen is on points there.

## Testing a phone

1. On the computer, find its address with `local` and run `mesh_link.py listen 8099 --seconds 120`. It says
   "listening" and waits.
2. On the phone's browser, on the same Wi-Fi, open `http://<computer address>:8099`.
3. A one-line message appears in the browser, and the computer prints "connection from <phone address>". That
   proves phone to computer on that port and tells you the phone's address.
4. Computer to phone needs a listener on the phone, which is the sharing app itself. Ask the person to start it,
   then run `peer <phone address> --ports <the app's port>` from the computer.

If step 2 fails and the computer is on Windows or macOS, the computer's firewall is the first suspect: allow that
one port for the private network, run the test, then remove the rule.

## What I cannot see

The phone's battery manager internals, the app's permission state, and whether the maker's own app-killer has
stopped the service. I can only show that connections to the phone's port fail or succeed.
