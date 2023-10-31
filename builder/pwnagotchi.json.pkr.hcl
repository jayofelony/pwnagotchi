packer {
  required_plugins {
    ansible = {
      version = ">= 1.1.0"
      source  = "github.com/hashicorp/ansible"
    }
  }
}

variable "pwn_hostname" {
  type = string
}

variable "pwn_version" {
  type = string
}

source "arm" "rpi-pwnagotchi" {
  file_checksum_url             = "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz.sha256"
  file_urls                     = ["https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz"]
  file_checksum_type            = "sha256"
  image_path                    = "../../../pwnagotchi-raspios-bullseye-${var.pwn_version}-arm64.img"
  qemu_binary_source_path       = "/usr/bin/qemu-aarch64-static"
  qemu_binary_destination_path  = "/usr/bin/qemu-aarch64-static"
  image_build_method            = "reuse"
  image_size                    = "9G"
  image_type                    = "dos"
}
source "arm" "opi-pwnagotchi" {
  file_checksum_url             = "../../images/pwnagotchi-orangepi-raspios.img.xz.sha256"
  file_urls                     = ["../../images/pwnagotchi-orangepi-raspios.img.xz"]
  file_checksum_type            = "sha256"
  image_path                    = "../../../pwnagotchi-orangepi-bullseye-${var.pwn_version}-arm64.img"
  qemu_binary_source_path       = "/usr/bin/qemu-aarch64-static"
  qemu_binary_destination_path  = "/usr/bin/qemu-aarch64-static"
  image_build_method            = "reuse"
  image_size                    = "9G"
  image_type                    = "dos"
  image_partitions {
    name         = "root"
    type         = "83"
    start_sector = "8192"
    filesystem   = "ext4"
    size         = "0"
    mountpoint   = "/"
  }
}

# a build block invokes sources and runs provisioning steps on them. The
# documentation for build blocks can be found here:
# https://www.packer.io/docs/from-1.5/blocks/build
build {
  name = "Pwnagotchi Torch 64bit"
  sources = [
    "source.arm.rpi-pwnagotchi",
    "source.arm.opi-pwnagotchi",
  ]

  provisioner "file" {
    destination = "/usr/bin/"
    sources     = [
      "../builder/data/usr/bin/pwnlib",
      "../builder/data/usr/bin/bettercap-launcher",
      "../builder/data/usr/bin/pwnagotchi-launcher",
      "../builder/data/usr/bin/monstop",
      "../builder/data/usr/bin/monstart",
      "../builder/data/usr/bin/hdmion",
      "../builder/data/usr/bin/hdmioff",
    ]
  }
  provisioner "shell" {
    inline = ["chmod +x /usr/bin/*"]
  }

  provisioner "file" {
    destination = "/etc/systemd/system/"
    sources     = [
      "../builder/data/etc/systemd/system/pwngrid-peer.service",
      "../builder/data/etc/systemd/system/pwnagotchi.service",
      "../builder/data/etc/systemd/system/bettercap.service",
    ]
  }
  provisioner "file" {
    destination = "/etc/update-motd.d/01-motd"
    source      = "../builder/data/etc/update-motd.d/01-motd"
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
    playbook_file   = "../builder/pwnagotchi.yml"
  }
}
