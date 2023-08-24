PACKER_VERSION=1.9.4
PWN_HOSTNAME=pwnagotchi
PWN_VERSION=2.0.1

all: clean install image

langs:
	@for lang in pwnagotchi/locale/*/; do\
		echo "compiling language: $$lang ..."; \
		./scripts/language.sh compile $$(basename $$lang); \
    done

install:
	curl https://releases.hashicorp.com/packer/$(PACKER_VERSION)/packer_$(PACKER_VERSION)_linux_amd64.zip -o /tmp/packer.zip
	unzip /tmp/packer.zip -d /tmp
	sudo mv /tmp/packer /usr/bin/packer
	git clone https://github.com/solo-io/packer-plugin-arm-image /tmp/packer-plugin-arm-image
	cd /tmp/packer-plugin-arm-image && go get -d ./... && go build -buildvcs=false
	sudo cp /tmp/packer-plugin-arm-image/packer-plugin-arm-image /usr/bin

image:
	cd builder && sudo /usr/bin/packer build -var "pwn_hostname=$(PWN_HOSTNAME)" -var "pwn_version=$(PWN_VERSION)" pwnagotchi.json
	sudo mv builder/output-pwnagotchi/image pwnagotchi-rpi-os-lite-$(PWN_VERSION).img
	sudo sha256sum pwnagotchi-rpi-os-lite-$(PWN_VERSION).img > pwnagotchi-rpi-os-lite-$(PWN_VERSION).sha256
	sudo zip pwnagotchi-rpi-os-lite-$(PWN_VERSION).zip pwnagotchi-rpi-os-lite-$(PWN_VERSION).sha256 pwnagotchi-rpi-os-lite-$(PWN_VERSION).img

clean:
	rm -rf /tmp/packer-builder-arm-image
	rm -f pwnagotchi-rpi-os-lite-*.zip pwnagotchi-rpi-os-lite-*.img pwnagotchi-rpi-os-lite-*.sha256
	rm -rf builder/output-pwnagotchi  builder/packer_cache
