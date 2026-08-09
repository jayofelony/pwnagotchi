#!/bin/bash -e
PWNSTORE_RAW="https://raw.githubusercontent.com/wpa-2/pwnagotchi-store/refs/heads/main"
echo -e "\e[32m### Installing PwnStore CLI ###\e[0m"
wget -q "${PWNSTORE_RAW}/pwnstore.py" -O "${ROOTFS_DIR}/usr/bin/pwnstore"
chmod 755 "${ROOTFS_DIR}/usr/bin/pwnstore"
echo -e "\e[32m### PwnStore CLI installed ###\e[0m"
