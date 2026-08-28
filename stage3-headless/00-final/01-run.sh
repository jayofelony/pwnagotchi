#!/bin/bash -e

echo -e "\e[32m### Installing patched files ###\e[0m"
install -v -m 0644 files/rpi-usb-gadget_1.0.7_arm64.deb "${ROOTFS_DIR}/home/pi/rpi-usb-gadget_1.0.7_arm64.deb"
install -v -m 755 files/user-data "${ROOTFS_DIR}/boot/firmware/user-data"
install -v -m 755 files/config.txt "${ROOTFS_DIR}/boot/firmware/config.txt"