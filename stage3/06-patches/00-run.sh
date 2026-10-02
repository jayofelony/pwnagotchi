#!/bin/bash -e

echo -e "\e[32m### Installing patched files ###\e[0m"
install -v -m 644 files/profile "${ROOTFS_DIR}/etc/profile"
install -v -m 644 files/sudoers "${ROOTFS_DIR}/etc/sudoers"

# /usr/bin/
# must be executable (755)
echo -e "\e[32m### Installing /usr/bin/ files ###\e[0m"
install -v -m 755 files/bettercap-launcher "${ROOTFS_DIR}/usr/bin/bettercap-launcher"
install -v -m 755 files/decryption-webserver "${ROOTFS_DIR}/usr/bin/decryption-webserver"
install -v -m 755 files/monstart "${ROOTFS_DIR}/usr/bin/monstart"
install -v -m 755 files/monstop "${ROOTFS_DIR}/usr/bin/monstop"
install -v -m 755 files/pwnagotchi-launcher "${ROOTFS_DIR}/usr/bin/pwnagotchi-launcher"
install -v -m 755 files/pwnlib "${ROOTFS_DIR}/usr/bin/pwnlib"
install -v -m 755 files/auto-update.sh "${ROOTFS_DIR}/usr/bin/auto-update.sh"
install -v -m 755 files/brcmfmac-watchdog.sh "${ROOTFS_DIR}/usr/bin/brcmfmac-watchdog.sh"

# /etc/
echo -e "\e[32m### Installing /etc/ files ###\e[0m"
install -v -m 644 files/dphys-swapfile "${ROOTFS_DIR}/etc/dphys-swapfile"

# /etc/bash_completion.d/
echo -e "\e[32m### Installing /etc/bash_completion.d/ files ###\e[0m"
install -v -m 644 files/pwnagotchi_completion.sh "${ROOTFS_DIR}/etc/bash_completion.d/pwnagotchi_completion.sh"

# /etc/systemd/system/
echo -e "\e[32m### Installing /etc/systemd/system/ files ###\e[0m"
install -v -m 644 files/bettercap.service "${ROOTFS_DIR}/etc/systemd/system/bettercap.service"
install -v -m 644 files/pwnagotchi.service "${ROOTFS_DIR}/etc/systemd/system/pwnagotchi.service"
install -v -m 644 files/pwnagotchi-usb-gadget.service "${ROOTFS_DIR}/etc/systemd/system/pwnagotchi-usb-gadget.service"
install -v -m 644 files/pwngrid-peer.service "${ROOTFS_DIR}/etc/systemd/system/pwngrid-peer.service"
install -v -m 644 files/auto-update.service "${ROOTFS_DIR}/etc/systemd/system/auto-update.service"
install -v -m 644 files/auto-update.timer "${ROOTFS_DIR}/etc/systemd/system/auto-update.timer"
install -v -m 644 files/brcmfmac-watchdog.service "${ROOTFS_DIR}/etc/systemd/system/brcmfmac-watchdog.service"

# /etc/update-motd.d/
# must be executable (755)
echo -e "\e[32m### Installing /etc/update-motd.d/ files ###\e[0m"
install -v -m 755 files/01-motd "${ROOTFS_DIR}/etc/update-motd.d/01-motd"

install -v -m 755 files/user-data "${ROOTFS_DIR}/boot/firmware/user-data"

# Remove unnecessary files, if they exist
echo -e "\e[32m### Removing unnecessary files ###\e[0m"
if [ -f "${ROOTFS_DIR}/etc/motd" ]; then
    rm "${ROOTFS_DIR}/etc/motd"
fi
if [ -f "${ROOTFS_DIR}/etc/update-motd.d/10-uname" ]; then
    rm "${ROOTFS_DIR}/etc/update-motd.d/10-uname"
fi
if [ -f "${ROOTFS_DIR}/etc/profile.d/sshpwd.sh" ]; then
    rm "${ROOTFS_DIR}/etc/profile.d/sshpwd.sh"
fi

install -v -m 755 files/config.txt "${ROOTFS_DIR}/boot/firmware/config.txt"
