PACKER_VERSION := 1.10.1
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

# sudo apt-get install qemu-user-static qemu-utils
all: clean packer image

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

packer:
	curl https://releases.hashicorp.com/packer/$(PACKER_VERSION)/packer_$(PACKER_VERSION)_linux_amd64.zip -o /tmp/packer.zip
	unzip /tmp/packer.zip -d /tmp
	sudo mv /tmp/packer /usr/bin/packer
	git clone https://github.com/solo-io/packer-builder-arm-image /tmp/packer-builder-arm-image
	cd /tmp/packer-builder-arm-image && go get -d ./... && go build

image: bullseye bookworm banagotchi

bullseye: clean packer
	export=LC_ALL=en_GB.utf-8
	cd builder && sudo /usr/bin/packer init data/32bit/pwnagotchi.json.pkr.hcl && sudo $(UNSHARE) /usr/bin/packer build -var "pwn_hostname=$(PWN_HOSTNAME)" -var "pwn_version=$(PWN_VERSION)" data/32bit/pwnagotchi.json.pkr.hcl
	cd ~ && sudo pishrink -vaZ pwnagotchi-$(PWN_VERSION)-32bit.img

bookworm: clean packer
	export=LC_ALL=en_GB.utf-8
	cd builder && sudo /usr/bin/packer init data/64bit/pwnagotchi.json.pkr.hcl && sudo $(UNSHARE) /usr/bin/packer build -var "pwn_hostname=$(PWN_HOSTNAME)" -var "pwn_version=$(PWN_VERSION)" data/64bit/pwnagotchi.json.pkr.hcl
	cd ~ && sudo pishrink -vaZ pwnagotchi-$(PWN_VERSION)-64bit.img

bananagotchi: clean packer
	export=LC_ALL=C.utf-8
	cd builder && sudo /usr/bin/packer init data/64bit/bananagotchi.json.pkr.hcl && sudo $(UNSHARE) /usr/bin/packer build -var "pwn_hostname=bananagotchi" -var "pwn_version=$(PWN_VERSION)" data/64bit/bananagotchi.json.pkr.hcl
	cd ~ && sudo pishrink -vaZ bananagotchi-$(PWN_VERSION).img

clean:
	- rm -rf /tmp/*
