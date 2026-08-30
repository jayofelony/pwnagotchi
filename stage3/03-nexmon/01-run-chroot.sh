#!/bin/bash -e

# Build the nexmon firmware patches from source for the chipsets we actually
# ship on. Set to 0 to fall back to Kali's prebuilt blobs only - useful to
# bisect whether a wifi regression came from a firmware rebuild.
NEXMON_FROM_SOURCE=1

NEXMON_SRC_URL="https://github.com/jayofelony/nexmon.git"
NEXMON_SRC_BRANCH="dev"
NEXMON_SRC_DIR="/home/pi/nexmon"

# "the card works in whatever Pi you put it in" is two separate things, and
# only one of them is built here:
#
#   - the firmware (brcmfmac<chip>-sdio.bin) is a blob uploaded to the wifi
#     chip's own core. It is per-chip and entirely kernel-independent, so
#     this list is chips, not kernels.
#   - the driver (brcmfmac.ko) is per-kernel, and that is DKMS's job: the
#     package installed by install_nexmon_driver builds against every kernel
#     that has headers present, here at image build time and again on any
#     later kernel upgrade. verify_driver_coverage() checks it did.
#
# <chip>/<firmware version>, naming a directory that exists under both
# patches/ and firmwares/ in the checkout.
#   bcm43430a1  Pi Zero W, Pi 3B, CM0
#   bcm43436b0  Pi Zero 2 W
#   bcm43455c0  Pi 3A+/3B+, Pi 4, Pi 5, Pi 500, CM4/CM5
#
# The Pi 400's bcm43456 is deliberately absent: nexmon upstream has no patch
# directory for it. It keeps Kali's prebuilt blob (see install_base_firmware)
# until that chip has been reverse engineered, at which point add it here.
# Latest version that has BOTH a patches/<chip>/<ver>/nexmon/Makefile and a
# firmwares/<chip>/<ver>/definitions.mk on the dev branch. Some versions ship
# firmware definitions with no patch tree yet (bcm43430a1/7_45_96_s1,
# bcm43455c0/7_45_241) - those are not buildable, check
# both trees before bumping.
NEXMON_PATCHES="
bcm43430a1/7_45_98
bcm43436b0/9_88_4_77
bcm43455c0/7_45_265
"

# nexmon's own documented Raspberry Pi build dependencies (the "Build ...
# for the Raspberry Pi" section of the checkout's README.md).
NEXMON_BUILD_DEPS="
autoconf
bison
flex
g++
gawk
git
libfl-dev
libgmp3-dev
libtool
make
qpdf
texinfo
wl
xxd
gcc-arm-none-eabi
"

# Only the packages we actually add get purged again afterwards. make, g++,
# git, xxd, wl and libfl-dev are already installed by 01-pwn-packages and
# other stages depend on them, so purging the whole dep list blindly would
# rip them out from under the rest of the build.
added_packages=""

install_build_deps() {
    echo -e "\e[32m=== Installing nexmon build dependencies ===\e[0m"
    for pkg in ${NEXMON_BUILD_DEPS}; do
        if [ "$(dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null)" != "install ok installed" ]; then
            added_packages="${added_packages} ${pkg}"
        fi
    done
    apt-get install -y --no-install-recommends ${NEXMON_BUILD_DEPS}
}

purge_build_deps() {
    echo -e "\e[32m=== Purging nexmon build dependencies ===\e[0m"
    if [ -n "${added_packages}" ]; then
        apt-get purge -y ${added_packages}
    fi
    # the toolchain packages are only the roots; most of the disk is in the
    # auto-installed dependencies they were holding down (gcc-arm-none-eabi
    # alone is ~520MB installed)
    apt-get autoremove --purge -y
    apt-get clean
}

# Kali's firmware-nexmon stays the base layer even when we build from source.
# It owns every NVRAM .txt, every .clm_blob and the whole
# brcmfmac<chip>-sdio.raspberrypi,<model> symlink matrix - none of which
# nexmon's build produces. Without the NVRAM the chip does not initialise at
# all, so this is not optional: dropping it costs wifi entirely, not just
# monitor mode. It also carries the Pi 400's 43456 blob, which we have no
# patch for yet.
install_base_firmware() {
    echo -e "\e[32m=== Installing base nexmon firmware ===\e[0m"
    cd /home/pi
    wget -O firmware-nexmon_0.2_all.deb https://kali.download/kali/pool/non-free-firmware/f/firmware-nexmon/firmware-nexmon_0.2_all.deb
    apt-get install -y /home/pi/firmware-nexmon_0.2_all.deb
    rm -f /home/pi/firmware-nexmon_0.2_all.deb
}

# brcmfmac asks the kernel for brcmfmac<chip>-sdio.raspberrypi,<model>.bin
# before falling back to the generic name, and firmware-nexmon points those
# board-specific names at files under cypress/ - for the 43455 via
# /etc/alternatives. Writing only the generic name would leave every board
# still loading Kali's blob, so resolve where the board-specific links
# actually land and overwrite that too. (readlink -f only resolves the
# absolute /etc/alternatives hop correctly from inside the chroot, which is
# where this runs.)
install_firmware_image() {
    src="$1"
    base="$(basename "${src}")"

    # RAM_FILE tells us which firmware tree the image belongs in, and it is
    # NOT stable across versions: bcm43455c0 up to 7_45_206 builds
    # brcmfmac43455-sdio.bin (brcm/), while 7_45_234 and later build
    # cyfmac43455-sdio-standard.bin (cypress/). Writing to the wrong tree
    # produces a file nothing ever loads, silently.
    case "${base}" in
        cyfmac*)   dir="/lib/firmware/cypress" ;;
        brcmfmac*) dir="/lib/firmware/brcm" ;;
        *)         echo "unexpected firmware image name ${base}" >&2; exit 1 ;;
    esac

    targets="${dir}/${base}"
    for link in /lib/firmware/brcm/"${base%.bin}".raspberrypi,*.bin; do
        [ -e "${link}" ] || continue
        targets="${targets} $(readlink -f "${link}")"
    done

    for target in $(printf '%s\n' ${targets} | sort -u); do
        install -v -m 644 "${src}" "${target}"
    done
}

# brcmfmac derives the CLM blob name from the firmware name it requested, so
# every name a board can ask for needs a matching .clm_blob beside it. Kali's
# firmware-nexmon ships the blob only as cypress/cyfmac<chip>-sdio.clm_blob,
# with no brcmfmac<chip>-sdio.clm_blob and none of the .raspberrypi,<model>
# variants - so on a Pi 3B the driver logs
#
#   brcmf_c_process_clm_blob: no clm_blob available (err=-2)
#
# and the firmware comes up with every channel disabled. Monitor mode then
# receives nothing at all, and any channel set fails, which surfaces as a
# cascade of BCDC -110 timeouts that looks exactly like a firmware wedge.
# Measured on a Pi 3B: without this, rx_packets stayed 0 and the -110s began
# within ~40s; with it, 11 channels enabled and sustained RX with no -110s.
ensure_clm_blob_aliases() {
    base="$1"
    chip="$(echo "${base}" | sed -n 's/^[a-z]*\([0-9]\{5\}\).*/\1/p')"
    [ -n "${chip}" ] || return 0

    src=""
    for cand in "/lib/firmware/cypress/cyfmac${chip}-sdio.clm_blob" \
                "/lib/firmware/brcm/brcmfmac${chip}-sdio.clm_blob"; do
        if [ -e "${cand}" ] && [ ! -L "${cand}" ]; then
            src="${cand}"
            break
        fi
    done
    if [ -z "${src}" ]; then
        echo "no CLM blob available for chip ${chip}, channels may be restricted" >&2
        return 0
    fi

    # The generic name, plus every board-specific name that has a .bin. Glob
    # *.bin specifically: the same prefix also matches .txt (and .clm_blob
    # itself), and stripping only the .bin suffix off those would produce
    # names like "...sdio.raspberrypi,3-model-b.txt.clm_blob".
    for bin in "/lib/firmware/brcm/brcmfmac${chip}-sdio.bin" \
               /lib/firmware/brcm/brcmfmac${chip}-sdio.raspberrypi,*.bin; do
        case "${bin}" in *"*"*) continue ;; esac
        [ -e "${bin}" ] || continue
        stem="${bin%.bin}"
        if [ ! -e "${stem}.clm_blob" ]; then
            ln -sfv "$(realpath --relative-to="$(dirname "${stem}")" "${src}")" "${stem}.clm_blob"
        fi
    done
}

build_nexmon_firmware() {
    install_build_deps

    rm -rf "${NEXMON_SRC_DIR}"
    git clone --depth 1 --branch "${NEXMON_SRC_BRANCH}" "${NEXMON_SRC_URL}" "${NEXMON_SRC_DIR}"

    cd "${NEXMON_SRC_DIR}"
    # shellcheck disable=SC1091
    source ./setup_env.sh
    # builds the buildtools, then extracts the ucode and flashpatches from
    # the stock firmware images vendored under firmwares/
    make

    for patch in ${NEXMON_PATCHES}; do
        definitions="${NEXMON_SRC_DIR}/firmwares/${patch}/definitions.mk"
        if [ ! -f "${definitions}" ]; then
            echo "no firmware definitions for ${patch}" >&2
            exit 1
        fi
        ram_file="$(sed -n 's/^RAM_FILE=//p' "${definitions}" | head -1)"
        if [ -z "${ram_file}" ]; then
            echo "could not determine RAM_FILE for ${patch}" >&2
            exit 1
        fi

        echo -e "\e[32m=== Building nexmon firmware ${patch} (${ram_file}) ===\e[0m"
        cd "${NEXMON_SRC_DIR}/patches/${patch}/nexmon"

        # Deliberately NOT `make` or `make install-firmware`. The default
        # target also builds brcmfmac.ko against `uname -r`, which inside the
        # chroot is the *build host's* kernel, and install-firmware then
        # rmmod/insmods it - on the host, since /proc is bind-mounted. Build
        # just the firmware image and place it ourselves. The kernel-side
        # driver comes from the prebuilt DKMS package regardless.
        make "${ram_file}"
        install_firmware_image "${ram_file}"
        ensure_clm_blob_aliases "${ram_file}"
    done

    cd /
    rm -rf "${NEXMON_SRC_DIR}"
    purge_build_deps
}

# The .deb is Architecture: all and contains no compiled module - it ships
# the driver source into /usr/src plus a dkms.conf, and DKMS compiles
# brcmfmac.ko here at install time against every kernel that has headers.
# That is what gives one package coverage of v8, 2712 and any future kernel.
install_nexmon_driver() {
    echo -e "\e[32m=== Installing nexmon brcmfmac driver ===\e[0m"

    # 00-run.sh clears stale packages before staging, so there should be
    # exactly one. Refuse to guess if that ever stops holding rather than
    # picking by `ls` order, which sorts lexically and would prefer an older
    # 6.12.x over 6.18.x.
    staged_count=$(ls -1 /home/pi/brcmfmac-nexmon-dkms_*_all.deb 2>/dev/null | wc -l)
    if [ "${staged_count}" -gt 1 ]; then
        echo "more than one staged nexmon DKMS package in /home/pi:" >&2
        ls -1 /home/pi/brcmfmac-nexmon-dkms_*_all.deb >&2
        exit 1
    fi

    staged_deb="$(ls /home/pi/brcmfmac-nexmon-dkms_*_all.deb 2>/dev/null | head -1)"
    if [ -z "${staged_deb}" ]; then
        echo "no nexmon DKMS package staged in /home/pi" >&2
        echo "build it first with 'make nexmon-dkms' - the 32bit/64bit targets do that for you" >&2
        echo >&2
        echo "This deliberately does not fall back to the newest GitHub release." >&2
        echo "Releases are cut by hand after a unit has been verified on hardware," >&2
        echo "so they lag this tree by design and can predate driver fixes that are" >&2
        echo "already here. Silently installing a driver of unknown age - possibly" >&2
        echo "without the monitor-mode promiscuous fix, or with the mmc_hw_reset" >&2
        echo "retry that boot-loops a wedged Pi - is worse than failing the build." >&2
        exit 1
    fi

    echo "installing ${staged_deb##*/}"
    # --allow-downgrades: the staged package is the one this tree built and is
    # by definition what we want installed, even when a reused WORK_DIR
    # already carries a higher version from an earlier build.
    apt-get install -y --allow-downgrades "${staged_deb}"
    rm -f "${staged_deb}"
}

# A kernel that ships in the image without a matching linux-headers-* package
# gets skipped by DKMS, and a board that boots it comes up on the stock
# in-tree brcmfmac - wifi works, monitor mode does not. That is silent at
# build time and only shows up as a dead-looking unit in someone's hand, so
# fail the build here instead.
verify_driver_coverage() {
    echo -e "\e[32m=== Verifying nexmon driver coverage ===\e[0m"
    missing=""
    for moddir in /lib/modules/*/; do
        kver="$(basename "${moddir}")"
        if ls "${moddir}"updates/dkms/brcmfmac.ko* >/dev/null 2>&1; then
            echo "  ${kver}: ok"
        elif [ -e "${moddir}build" ]; then
            echo "  ${kver}: FAILED (headers present, DKMS build did not produce a module)"
            missing="${missing} ${kver}"
        else
            echo "  ${kver}: FAILED (no linux-headers-* installed for this kernel)"
            missing="${missing} ${kver}"
        fi
    done

    if [ -n "${missing}" ]; then
        echo "no nexmon brcmfmac.ko was built for:${missing}" >&2
        echo "a Pi booting that kernel would fall back to the stock driver and lose monitor mode" >&2
        exit 1
    fi
}

# The stock brcm firmware has to go first: dpkg owns those paths, so removing
# the package later would take the nexmon images with it.
apt-get remove -y firmware-brcm80211

install_base_firmware

if [ "${NEXMON_FROM_SOURCE}" = "1" ]; then
    build_nexmon_firmware
fi

install_nexmon_driver
verify_driver_coverage
