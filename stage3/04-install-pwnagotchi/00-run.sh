#!/bin/bash -e

echo -e "\e[32m### Creating Pwnagotchi folders ###\e[0m"
install -v -d "${ROOTFS_DIR}/etc/pwnagotchi"
install -v -d "${ROOTFS_DIR}/etc/pwnagotchi/log"
install -v -d "${ROOTFS_DIR}/etc/pwnagotchi/conf.d/"
install -v -d "${ROOTFS_DIR}/etc/pwnagotchi/custom-plugins/"
install -v -d "${ROOTFS_DIR}/etc/pwnagotchi/handshakes/"
install -v -d "${ROOTFS_DIR}/etc/pwnagotchi/backups/"
install -v -d "${ROOTFS_DIR}/etc/pwnagotchi/sessions/"