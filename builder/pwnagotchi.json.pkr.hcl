# This is not working quite yet
# https://github.com/mkaczanowski/packer-builder-arm/pull/172
packer {
  required_plugins {
    #arm = {
    #  version = "~> 1"
    #  source  = "github.com/cdecoux/builder-arm"
    #}
    ansible = {
      source  = "github.com/hashicorp/ansible"
      version = "~> 1"
    }
  }
}

variable "pwn_hostname" {
  type = string
}

variable "pwn_version" {
  type = string
}

source "arm" "rpi64-pwnagotchi" {
  file_checksum_url             = "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-12-11/2023-12-11-raspios-bookworm-arm64-lite.img.xz.sha256"
  file_urls                     = ["https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-12-11/2023-12-11-raspios-bookworm-arm64-lite.img.xz"]
  file_checksum_type            = "sha256"
  file_target_extension         = "xz"
  file_unarchive_cmd            = ["unxz", "$ARCHIVE_PATH"]
  image_path                    = "../../../pwnagotchi-rpi-bookworm-${var.pwn_version}-arm64.img"
  qemu_binary_source_path       = "/usr/bin/qemu-aarch64-static"
  qemu_binary_destination_path  = "/usr/bin/qemu-aarch64-static"
  image_build_method            = "resize"
  image_size                    = "9G"
  image_type                    = "dos"
  image_partitions {
    name         = "boot"
    type         = "c"
    start_sector = "8192"
    filesystem   = "fat"
    size         = "256M"
    mountpoint   = "/boot/firmware"
  }
  image_partitions {
    name         = "root"
    type         = "83"
    start_sector = "532480"
    filesystem   = "ext4"
    size         = "0"
    mountpoint   = "/"
  }
}

# a build block invokes sources and runs provisioning steps on them. The
# documentation for build blocks can be found here:
# https://www.packer.io/docs/from-1.5/blocks/build
build {
  name = "Raspberry Pi 64 Pwnagotchi"
  sources = ["source.arm.rpi64-pwnagotchi"]

  provisioner "file" {
    destination = "/usr/bin/"
    sources     = [
      "data/usr/bin/bettercap-launcher",
      "data/usr/bin/hdmioff",
      "data/usr/bin/hdmion",
      "data/usr/bin/monstart",
      "data/usr/bin/monstop",
      "data/usr/bin/pwnagotchi-launcher",
      "data/usr/bin/pwnlib",
    ]
  }
  provisioner "shell" {
    inline = ["chmod +x /usr/bin/*"]
  }

  provisioner "file" {
    destination = "/etc/systemd/system/"
    sources     = [
      "data/etc/systemd/system/bettercap.service",
      "data/etc/systemd/system/pwnagotchi.service",
      "data/etc/systemd/system/pwngrid-peer.service",
    ]
  }

  provisioner "file" {
    destination = "/etc/update-motd.d/01-motd"
    source      = "data/etc/update-motd.d/01-motd"
  }
  provisioner "shell" {
    inline = ["chmod +x /etc/update-motd.d/*"]
  }
  provisioner "shell" {
    inline = ["apt-get -y --allow-releaseinfo-change update", "apt-get -y dist-upgrade", "apt-get install -y --no-install-recommends ansible"]
  }
  provisioner "ansible-local" {
    command         = "ANSIBLE_FORCE_COLOR=1 PYTHONUNBUFFERED=1 PWN_VERSION=${var.pwn_version} PWN_HOSTNAME=${var.pwn_hostname} ansible-playbook"
    extra_arguments = ["--extra-vars \"ansible_python_interpreter=/usr/bin/python3\""]
    playbook_file   = "raspberrypi64.yml"
  }
}