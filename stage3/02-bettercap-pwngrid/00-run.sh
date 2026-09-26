#!/bin/bash -e
# Host-side emulation probe for the Go builds in 02-run-chroot.sh.
#
# When cross-building the arm64 image under QEMU user emulation, Go's
# signal-based async preemption deadlocks and the multi-threaded compiler
# hangs forever on bettercap/pwngrid. Go must be constrained in that case.
#
# The chroot script CANNOT detect emulation itself: uname is faked by QEMU,
# the qemu interpreter is preloaded via the binfmt "F" flag so it is never
# copied into the rootfs, and pi-gen mounts a fresh /proc so binfmt_misc is
# not visible inside the chroot. The build HOST, however, knows its real
# architecture - so probe here and leave a marker the chroot script reads.
# Native arm64 builders leave no marker and keep full Go parallelism.
case "$(uname -m)" in
    aarch64|arm64)
        rm -f "${ROOTFS_DIR}/tmp/.pwn-go-emulated"
        ;;
    *)
        install -d "${ROOTFS_DIR}/tmp"
        : > "${ROOTFS_DIR}/tmp/.pwn-go-emulated"
        echo "[build] non-arm64 host ($(uname -m)) - Go will be constrained for emulation"
        ;;
esac
