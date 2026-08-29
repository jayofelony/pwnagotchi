# Set an absolute path in the config file for WORK_DIR and DEPLOY_DIR
# DEPLOY_DIR is where the final image will be stored
# WORK_DIR is where all the data is stored before merged into an image
# WORK_DIR can use up to 20GB of storage space
# refer to https://github.com/RPi-Distro/pi-gen/blob/master/README.md
# sudo apt-get install -y make git quilt qemu-user-static debootstrap zerofree libarchive-tools curl pigz arch-test qemu-utils qemu-system-arm qemu-user
# gcc-aarch64-linux-gnu gcc-arm-linux-gnueabihf
# Building the nexmon DKMS package additionally needs:
# sudo apt-get install -y debhelper dh-sequence-dkms dpkg-dev
# Publishing a driver release additionally needs the GitHub CLI: gh

BUILD_USER ?= $(shell whoami)
BUILD_HOME ?= $(shell eval echo ~$(BUILD_USER))
IMAGE_DIR ?= $(BUILD_HOME)/images

NEXMON_DKMS_DIR := stage3/03-nexmon/brcmfmac-nexmon-dkms
NEXMON_DKMS_OUT := stage3/03-nexmon/files
NEXMON_DRIVER_SRC := stage3/03-nexmon/nexmon/patches/driver/brcmfmac_6.18.y-nexmon

# Check out every submodule at the commit this tree pins. Run after a fresh
# clone - the image build needs bettercap, pwngrid and the nexmon trees.
submodules:
	git submodule update --init --recursive

# Fast-forward each submodule to the tip of the branch .gitmodules tracks.
# This deliberately changes what the next image contains (bettercap, pwngrid
# and the nexmon sources all float), so the resulting pointer bumps should be
# committed and test-built, not left dangling in a working tree.
update-submodules:
	git submodule update --init --recursive --remote
	@echo "submodule pointers moved - review 'git diff' and test-build before committing"

# Build the brcmfmac-nexmon DKMS package from the submodule.
#
# The package is Architecture: all and debian/rules overrides dh_auto_build
# to do nothing: it ships the driver *source* into /usr/src plus a dkms.conf,
# and brcmfmac.ko is compiled per-kernel by DKMS at install time inside the
# image. So there is nothing arch-specific here and this builds fine on an
# x86 host. debian/rules forces PACKAGE_VERSION from debian/changelog, which
# is the single source of truth for the version - bump it there.
nexmon-dkms:
	@command -v dh_dkms >/dev/null || { echo "dh-sequence-dkms is not installed (see the header of this Makefile)"; exit 1; }
	[ -f $(NEXMON_DKMS_DIR)/debian/changelog ] || { echo "$(NEXMON_DKMS_DIR) is empty - run 'make submodules' first"; exit 1; }
	[ -f $(NEXMON_DRIVER_SRC)/sdio.c ] || { echo "$(NEXMON_DRIVER_SRC) is missing - run 'make submodules' first"; exit 1; }
	# The nexmon repo is canonical for driver source: that is where the
	# root-cause work happens, and its copy carries fixes the packaging repo
	# never got (promiscuous mode on monitor open). Copy the .c/.h over the
	# packaging tree before building so the two cannot drift.
	#
	# Only the sources - Makefile, Kconfig and dkms.conf stay as the
	# packaging repo has them. nexmon's driver Makefile is a bare kbuild
	# stub, while the packaging one also handles the standalone
	# KVER/KSRC/MODDESTDIR path that DKMS drives.
	cp -v $(NEXMON_DRIVER_SRC)/*.c $(NEXMON_DRIVER_SRC)/*.h $(NEXMON_DKMS_DIR)/
	cd $(NEXMON_DKMS_DIR) && dpkg-buildpackage -us -uc -b
	mkdir -p $(NEXMON_DKMS_OUT)
	rm -f $(NEXMON_DKMS_OUT)/brcmfmac-nexmon-dkms_*.deb
	mv stage3/03-nexmon/brcmfmac-nexmon-dkms_*_all.deb $(NEXMON_DKMS_OUT)/
	rm -f stage3/03-nexmon/brcmfmac-nexmon-dkms_*.buildinfo stage3/03-nexmon/brcmfmac-nexmon-dkms_*.changes
	# dpkg-buildpackage litters the submodule, and debian/rules seds dkms.conf
	# to force PACKAGE_VERSION from the changelog on every build - so the
	# tracked value is inert and restoring it just keeps the tree clean.
	# Restore only dkms.conf, which debian/rules seds to force PACKAGE_VERSION
	# from the changelog. The synced *.c/*.h are deliberately LEFT in place:
	# reverting them would make the sync exist only during the build, so the
	# packaging repo would keep shipping stale source to anyone who clones and
	# builds it directly. Leaving them means drift shows up as uncommitted
	# changes in the submodule - which is also what nexmon-dkms-release
	# refuses to publish over.
	cd $(NEXMON_DKMS_DIR) && dh_clean && git checkout -- dkms.conf
	@echo "built $$(ls $(NEXMON_DKMS_OUT)/brcmfmac-nexmon-dkms_*.deb)"

NEXMON_DKMS_REPO := jayofelony/brcmfmac-nexmon-dkms

# Publish the built DKMS package as a GitHub release on the packaging repo.
#
# Deliberately NOT a dependency of any image target. Publishing is
# outward-facing, and a green image build only proves the module compiled -
# not that monitor mode works on real hardware. Run this after verifying a
# unit, and only then: CONFIRM=yes is required so it can never fire as a side
# effect of something else.
#
# The tag comes from debian/changelog (the same source dpkg uses for the
# package version) and is anchored to the packaging submodule's exact commit,
# so a release always names source that is actually published.
nexmon-dkms-release: nexmon-dkms
	@[ "$(CONFIRM)" = "yes" ] || { echo "refusing to publish without confirmation"; echo "usage: make nexmon-dkms-release CONFIRM=yes"; exit 1; }
	@command -v gh >/dev/null || { echo "the GitHub CLI (gh) is not installed"; exit 1; }
	@set -e; \
	for m in $(NEXMON_DKMS_DIR) $(NEXMON_DRIVER_SRC:/patches/driver/brcmfmac_6.18.y-nexmon=); do \
	  [ -z "$$(git -C $$m status --porcelain)" ] || { echo "$$m has uncommitted changes - commit them before releasing"; exit 1; }; \
	  git -C $$m fetch -q origin; \
	  [ "$$(git -C $$m rev-parse HEAD)" = "$$(git -C $$m rev-parse @{u})" ] || { echo "$$m is not in sync with its upstream branch - push before releasing"; exit 1; }; \
	done; \
	ver="$$(cd $(NEXMON_DKMS_DIR) && dpkg-parsechangelog -S Version)"; \
	sha="$$(git -C $(NEXMON_DKMS_DIR) rev-parse HEAD)"; \
	deb="$(NEXMON_DKMS_OUT)/brcmfmac-nexmon-dkms_$${ver}_all.deb"; \
	[ -f "$$deb" ] || { echo "$$deb not found - 'make nexmon-dkms' should have produced it"; exit 1; }; \
	if gh release view "v$$ver" --repo $(NEXMON_DKMS_REPO) >/dev/null 2>&1; then \
	  echo "release v$$ver already exists - bump debian/changelog rather than overwriting a published release"; exit 1; \
	fi; \
	notes="$$(awk 'NR>1 && /^brcmfmac-nexmon-dkms /{exit} {print}' $(NEXMON_DKMS_DIR)/debian/changelog)"; \
	echo "publishing v$$ver from $$sha with $$deb"; \
	gh release create "v$$ver" "$$deb" --repo $(NEXMON_DKMS_REPO) --target "$$sha" --title "v$$ver" --notes "$$notes"

# stock test build with cloud-init ssh and rpi-usb-gadget enabled
headless:
	[ -d pi-gen-64bit ] || git clone --branch arm64 "https://github.com/jayofelony/pi-gen.git" pi-gen-64bit
	[ -d pi-gen-64bit ] && cd pi-gen-64bit && git pull
	rm -rf pi-gen-64bit/stage2/EXPORT_IMAGE
	sed -i "s|WORK_DIR=.*|WORK_DIR=\"$(BUILD_HOME)/work-64bit\"|" config-headless
	sed -i "s|DEPLOY_DIR=.*|DEPLOY_DIR=\"$(IMAGE_DIR)\"|" config-headless
	sudo ./pi-gen-64bit/build.sh -c config-headless
	mkdir -p $(IMAGE_DIR)
	sudo chown $(BUILD_USER):$(BUILD_USER) -R $(IMAGE_DIR)

# clone pi-gen into pi-gen-32bit folder
32bit: nexmon-dkms
	[ -d pi-gen-32bit ] || git clone "https://github.com/jayofelony/pi-gen.git" pi-gen-32bit
	[ -d pi-gen-32bit ] && cd pi-gen-32bit && git pull
	rm -rf pi-gen-32bit/stage2/EXPORT_IMAGE
	sed -i "s|WORK_DIR=.*|WORK_DIR=\"$(BUILD_HOME)/work-32bit\"|" config-32bit
	sed -i "s|DEPLOY_DIR=.*|DEPLOY_DIR=\"$(IMAGE_DIR)\"|" config-32bit
	sudo ./pi-gen-32bit/build.sh -c config-32bit
	mkdir -p $(IMAGE_DIR)
	sudo chown $(BUILD_USER):$(BUILD_USER) -R $(IMAGE_DIR)

# clone pi-gen arm64 branch into pi-gen-64bit folder
64bit: nexmon-dkms
	[ -d pi-gen-64bit ] || git clone --branch arm64 "https://github.com/jayofelony/pi-gen.git" pi-gen-64bit
	[ -d pi-gen-64bit ] && cd pi-gen-64bit && git pull
	rm -rf pi-gen-64bit/stage2/EXPORT_IMAGE
	sed -i "s|WORK_DIR=.*|WORK_DIR=\"$(BUILD_HOME)/work-64bit\"|" config-64bit
	sed -i "s|DEPLOY_DIR=.*|DEPLOY_DIR=\"$(IMAGE_DIR)\"|" config-64bit
	sudo ./pi-gen-64bit/build.sh -c config-64bit
	mkdir -p $(IMAGE_DIR)
	sudo chown $(BUILD_USER):$(BUILD_USER) -R $(IMAGE_DIR)

update_langs:
	@for lang in pwnagotchi/locale/*/; do\
		echo "updating language: $$lang ..."; \
		./scripts/language.sh update $$(basename $$lang); \
	done

compile_langs:
	@for lang in pwnagotchi/locale/*/; do\
		echo "compiling language: $$lang ..."; \
		./scripts/language.sh compile $$(basename $$lang); \
	done
