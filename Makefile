PACKER_VERSION := 1.10.0
PWN_HOSTNAME := pwnagotchi
PWN_VERSION := $(shell cut -d"'" -f2 < pwnagotchi/_version.py)

MACHINE_TYPE := $(shell uname -m)
ifneq (,$(filter x86_64,$(MACHINE_TYPE)))
GOARCH := amd64
else ifneq (,$(filter i686,$(MACHINE_TYPE)))
GOARCH := 386
else ifneq (,$(filter arm64% aarch64%,$(MACHINE_TYPE)))
GOARCH := arm64
else ifneq (,$(filter arm%,$(MACHINE_TYPE)))
GOARCH := arm
else
GOARCH := amd64
$(warning Unable to detect CPU arch from machine type $(MACHINE_TYPE), assuming $(GOARCH))
endif

# The Ansible part of the build can inadvertently change the active hostname of
# the build machine while updating the permanent hostname of the build image.
# If the unshare command is available, use it to create a separate namespace
# so hostname changes won't affect the build machine.
UNSHARE := $(shell command -v unshare)
ifneq (,$(UNSHARE))
UNSHARE := $(UNSHARE) --uts
endif

all: clean image clean

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

PACKER := ~/pwnagotchi/packer
PACKER_URL := https://releases.hashicorp.com/packer/$(PACKER_VERSION)/packer_$(PACKER_VERSION)_linux_$(GOARCH).zip
$(PACKER):
	mkdir -p $(@D)
	curl -L "$(PACKER_URL)" -o $(PACKER).zip
	unzip $(PACKER).zip -d $(@D)
	rm $(PACKER).zip
	chmod +x $@

SDIST := dist/pwnagotchi-$(PWN_VERSION).tar.gz
$(SDIST): setup.py pwnagotchi
	python3 setup.py sdist

# Building the image requires packer, but don't rebuild the image just because packer updated.
pwnagotchi: | $(PACKER)

# If the packer or ansible files are updated, rebuild the image.
pwnagotchi: $(SDIST) builder/pwnagotchi.json.pkr.hcl builder/raspberrypi32.yml builder/raspberrypi64.yml builder/orangepi.yml builder/extras/nexmon.yml $(shell find builder/data -type f)

	cd builder && $(PACKER) init pwnagotchi.json.pkr.hcl && sudo $(UNSHARE) $(PACKER) build -var "pwn_hostname=$(PWN_HOSTNAME)" -var "pwn_version=$(PWN_VERSION)" pwnagotchi.json.pkr.hcl

.PHONY: image
image: pwnagotchi

clean:
	- rm -rf build dist pwnagotchi.egg-info
	- rm -f $(PACKER)
