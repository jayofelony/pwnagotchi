#!/bin/bash -e

echo -e "\e[32m### Setting permissions ###\e[0m"
chmod +x /usr/bin/*
chmod +x /usr/local/bin/*
chmod +x /etc/update-motd.d/*

echo -e "\e[32m### Enabling services ###\e[0m"
systemctl enable bettercap pwngrid-peer pwnagotchi bluetooth.service
systemctl disable wpa_supplicant apt-daily-upgrade.service apt-daily-upgrade.timer apt-daily.service apt-daily.timer

echo -e "\e[32m### Disable apt packages from upgrading ###\e[0m"
apt-mark hold firmware-atheros firmware-brcm80211 firmware-libertas firmware-misc-nonfree firmware-realtek libpcap-dev libpcap0.8-dev

echo -e "\e[32m### Cleaning up ###\e[0m"
apt-get autoremove -y
apt-get clean