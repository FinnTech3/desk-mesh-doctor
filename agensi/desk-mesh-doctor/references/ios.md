# iPhone and iPad checklist

Menu names change with the iOS or iPadOS version. Ask for the version and say "check your OS version" when you give
a path. You cannot run the scripts on an iPhone or iPad: test from a computer (the "Testing" section of
`android.md` works the same way with the iPhone's browser).

## Local Network permission

Since iOS 14, an app must be allowed to reach devices on the local network. The first time it tries, iOS shows a
prompt. If the person tapped "Don't Allow", the app can still reach the internet and can never reach a computer on
the LAN, and the prompt does not come back.

Settings, Privacy & Security, Local Network: switch the app on. If the app is not in the list, it has not asked
yet: open it and trigger a connection to a device on the network. A reboot of the phone is sometimes needed after
changing this (check your OS version).

## Private Wi-Fi Address

Each Wi-Fi network gets its own address by default, and on newer versions it can rotate. This stops a router
reservation or a MAC allow list from matching, and makes the iPhone look like a new device.

Settings, Wi-Fi, the "i" next to the network, Private Wi-Fi Address. For a trusted home network, "Fixed" or off
gives a steady address. If you change it, the phone rejoins and takes a new lease: run the test again from scratch.

## Background limits

iOS suspends an app a short time after it leaves the screen, and does not allow general long-lived background
connections. A sharing app that "stops when the phone locks" may be behaving as iOS requires. Things that change it:

- Background App Refresh for the app, under Settings, General.
- Low Power Mode, which reduces background activity: turn it off for a test.
- Whether the app uses one of the few background modes iOS offers. I cannot see that.

## Wi-Fi, hotspot and relay features

- The iPhone must be on the same Wi-Fi network as the computer, not the guest network and not mobile data.
- A device using the iPhone's Personal Hotspot is on the phone's own subnet: run `local` on it to see.
- Features that route traffic through a relay or hide the device's address can change what a local app sees. If a
  setting like that is on for the Wi-Fi network, switch it off for the network under test and compare.

## What I cannot see

The phone's permission state and whether iOS has suspended the app. I can only show that connections to the
phone's port fail or succeed, and that the computer's side is healthy.
