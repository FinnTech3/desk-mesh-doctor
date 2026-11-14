| from \ to | laptop | desk |
|---|---|---|
| laptop | - | filtered |
| desk | ok | - |

laptop <-> desk: same subnet (192.168.50.0/24)
  [problem] laptop->desk is filtered: nothing gets through, so desk's firewall or network profile is dropping inbound connections; desk->laptop works, which points at desk, not the router.
