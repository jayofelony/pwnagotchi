#!/bin/bash -e

echo -e "\e[32m### Upgrading system packages ###\e[0m"
apt-get update
apt-get -y dist-upgrade

echo -e "\e[32m### Installing mitigation rpi-usb-gadget for linux ###\e[0m"
apt-get install -y /home/pi/rpi-usb-gadget_1.0.6_arm64.deb
rm /home/pi/rpi-usb-gadget_1.0.6_arm64.deb

echo -e "\e[32m### Installing rust ###\e[0m"
curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh -s -- -y
export PATH="/root/.cargo/bin:$PATH"
source /root/.profile
source /root/.cargo/env