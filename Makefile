# Set an absolute path in the config file for WORK_DIR and DEPLOY_DIR
# DEPLOY_DIR is where the final image will be stored
# WORK_DIR is where all the data is stored before merged into an image
# WORK_DIR can use up to 20GB of storage space
# refer to https://github.com/RPi-Distro/pi-gen/blob/master/README.md
# sudo apt-get install -y make git quilt qemu-user-static debootstrap zerofree libarchive-tools curl pigz arch-test qemu-utils qemu-system-arm qemu-user
# gcc-aarch64-linux-gnu gcc-arm-linux-gnueabihf

BUILD_USER ?= $(shell whoami)
BUILD_HOME ?= $(shell eval echo ~$(BUILD_USER))
IMAGE_DIR ?= $(BUILD_HOME)/images

# clone pi-gen into pi-gen-32bit folder
32bit:
	[ -d pi-gen-32bit ] || git clone "https://github.com/jayofelony/pi-gen.git" pi-gen-32bit
	[ -d pi-gen-32bit ] && cd pi-gen-32bit && git pull
	rm -rf pi-gen-32bit/stage2/EXPORT_IMAGE
	sed -i "s|WORK_DIR=.*|WORK_DIR=\"$(BUILD_HOME)/work-32bit\"|" config-32bit
	sed -i "s|DEPLOY_DIR=.*|DEPLOY_DIR=\"$(IMAGE_DIR)\"|" config-32bit
	sudo ./pi-gen-32bit/build.sh -c config-32bit
	mkdir -p $(IMAGE_DIR)
	sudo chown $(BUILD_USER):$(BUILD_USER) -R $(IMAGE_DIR)

# clone pi-gen arm64 branch into pi-gen-64bit folder
64bit:
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
