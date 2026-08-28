#!/bin/bash -e

echo -e "\e[32m### Upgrading system packages ###\e[0m"
apt-get update
apt-get -y dist-upgrade

echo -e "\e[32m### Installing mitigation rpi-usb-gadget for linux ###\e[0m"
dpkg -i /home/pi/rpi-usb-gadget_1.0.6_arm64.deb
rm /home/pi/rpi-usb-gadget_1.0.6_arm64.deb