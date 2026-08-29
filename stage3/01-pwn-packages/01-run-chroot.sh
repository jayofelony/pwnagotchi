#!/bin/bash -e

echo -e "\e[32m### Upgrading system packages ###\e[0m"
apt-get update
apt-get -y dist-upgrade

echo -e "\e[32m### Purging packages a pwnagotchi never uses ###\e[0m"
# Raspberry Pi OS Lite (pi-gen stage2) ships desktop/media/convenience
# packages that are dead weight here, and older WORK_DIRs may still carry
# packages this stage's own list used to install (an ocaml toolchain pulled
# in by the misnamed lib*-ocaml-dev entries, a permanently-installed
# gcc-arm-none-eabi, a debug CPython, fbi - which dragged in mesa+llvm for a
# framebuffer viewer nothing calls). Purging here rather than only trimming
# the install list means a reused WORK_DIR converges to the same state as a
# clean build.
#
# gcc-arm-none-eabi in particular is still needed to build nexmon from
# source, but 03-nexmon now installs and purges it around the build itself,
# so it never has to sit in the image - see NEXMON_FROM_SOURCE there.
UNNEEDED_PACKAGES="
gcc-arm-none-eabi
libcurl-ocaml-dev
libssl-ocaml-dev
python3-dbg
fbi
libopenblas-dev
mkvtoolnix
rpi-connect-lite
rpicam-apps-lite
v4l-utils
gdb
manpages-dev
p7zip-full
zip
ntfs-3g
libmtp-runtime
lua5.1
luajit
rpi-keyboard-config
rpi-keyboard-fw-update
rpifwcrypto
"

# apt-get errors out on a name it can't find, and this script runs under
# `set -e`, so only hand it packages that are actually installed - upstream
# is free to rename or drop any of these without breaking the build.
to_purge=""
for pkg in ${UNNEEDED_PACKAGES}; do
    if [ "$(dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null)" = "install ok installed" ]; then
        to_purge="${to_purge} ${pkg}"
    fi
done

if [ -n "${to_purge}" ]; then
    apt-get purge -y ${to_purge}
fi

# the packages above are only the roots; most of the space is in the
# auto-installed dependencies they were holding down (llvm, mesa, the ocaml
# stack, the debug interpreter, qt6+icu behind mkvtoolnix)
apt-get autoremove --purge -y
apt-get clean

echo -e "\e[32m### Installing mitigation rpi-usb-gadget for linux ###\e[0m"
dpkg -i /home/pi/rpi-usb-gadget_1.0.7_arm64.deb
rm /home/pi/rpi-usb-gadget_1.0.7_arm64.deb

echo -e "\e[32m### Installing rust ###\e[0m"
curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh -s -- -y
export PATH="/root/.cargo/bin:$PATH"
source /root/.profile
source /root/.cargo/env