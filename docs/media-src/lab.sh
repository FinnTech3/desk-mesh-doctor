#!/usr/bin/env bash
# lab.sh: functions that build a two-device lab out of two Linux network namespaces joined by a virtual cable.
# Needs root, iproute2 and iptables. Source it; it defines functions and runs nothing.
# Nothing outside the two namespaces changes: no host interface, route or firewall rule is touched. The namespaces
# are called dmd-laptop and dmd-desk, and lab_down removes only those.
#
#   laptop 192.168.50.10/24 (vlap)  <---- virtual cable ---->  192.168.50.20/24 (vdesk) desk
#   On the desk one iptables rule drops inbound TCP 7001. A listener on 7001 on each device stands in for a
#   sharing tool.

lab_down() {
  ip netns del dmd-laptop 2>/dev/null || true
  ip netns del dmd-desk 2>/dev/null || true
}

lab_up() {
  lab_down
  ip netns add dmd-laptop
  ip netns add dmd-desk
  ip link add vlap type veth peer name vdesk
  ip link set vlap netns dmd-laptop
  ip link set vdesk netns dmd-desk
  ip -n dmd-laptop addr add 192.168.50.10/24 dev vlap
  ip -n dmd-desk addr add 192.168.50.20/24 dev vdesk
  for d in laptop desk; do ip -n "dmd-$d" link set lo up; done
  ip -n dmd-laptop link set vlap up
  ip -n dmd-desk link set vdesk up
  # A default route, as on a home network. The "router" address is made up and nothing answers it; no packet goes there.
  ip -n dmd-laptop route add default via 192.168.50.1
  ip -n dmd-desk route add default via 192.168.50.1
  ip netns exec dmd-desk iptables -A INPUT -p tcp --dport 7001 -j DROP
}

# nsrun DEVICE COMMAND...: run a command on one device, with that device's own host name.
nsrun() {
  local dev=$1
  shift
  ip netns exec "dmd-$dev" unshare -u -- sh -c 'hostname "$0"; exec "$@"' "$dev" "$@"
}
