#!/usr/bin/env bash

# Upstream (internet-facing) interface
# Defaults to "en0" if not provided as first argument
UPSTREAM_IFACE=${1:-en0}

# Will hold the detected USB network interface
USB_IFACE=''

# IP address expected on the USB interface
# Defaults to 10.0.0.1 if not provided as second argument
USB_IP=${2:-10.0.0.1}

# Iterate over all network interfaces
for i in $(ifconfig -lu); do
  # Check if the interface has the specified USB IP
  if ifconfig "$i" | grep -q "${USB_IP}" ; then
    USB_IFACE=$i
  fi
done

# Abort if no USB interface with the given IP was found
if [ -z "$USB_IFACE" ]
then
  echo "can't find usb interface with ip $USB_IP"
  exit 1
fi

# Inform user about the interface mapping
echo "sharing connecting from upstream interface $UPSTREAM_IFACE to usb interface $USB_IFACE ..."

# Enable IPv4 packet forwarding (required for routing/NAT)
sysctl -w net.inet.ip.forwarding=1

# Enable the packet filter (pf) firewall
pfctl -e

# Set up NAT:
# - Translate traffic coming from the USB interface network
# - Route it out through the upstream interface
echo "nat on ${UPSTREAM_IFACE} from ${USB_IFACE}:network to any -> (${UPSTREAM_IFACE})" | pfctl -f -
