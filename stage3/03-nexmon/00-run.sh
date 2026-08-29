#!/bin/bash -e

# A reused WORK_DIR can still hold a DKMS package from an older build, and
# the chroot side globs this directory. Leaving both behind means apt gets
# handed whichever sorts first lexically - and "6.12.2+ndevfix1" sorts before
# "6.18.39.2" because '2' < '8' - so a stale package wins over the one we
# just staged and the build dies with "Packages were downgraded and -y was
# used without --allow-downgrades". Clear them out first, unconditionally:
# a leftover would break the release-fallback path too.
rm -f "${ROOTFS_DIR}/home/pi/"brcmfmac-nexmon-dkms_*_all.deb

# Stage the DKMS package built on the host by `make nexmon-dkms` (the image
# targets depend on it) so 01-run-chroot.sh can install the exact driver
# source this tree pins. Optional: building pi-gen directly instead of
# through the Makefile leaves this absent, and the chroot script falls back
# to the newest published GitHub release.
deb="$(ls files/brcmfmac-nexmon-dkms_*_all.deb 2>/dev/null | head -1)"
if [ -n "${deb}" ]; then
    install -v -m 644 "${deb}" "${ROOTFS_DIR}/home/pi/"
else
    echo "no locally built nexmon DKMS package staged; the chroot will fall back to the latest release"
fi
