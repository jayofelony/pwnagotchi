packer {
  required_plugins {
    arm-image = {
      version = ">= 0.2.7"
      source  = "github.com/solo-io/arm-image"
    }
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

source "rpi-pwnagotchi" {
  iso_checksum      = "file:https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz.sha256"
  iso_url           = "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz"
  output_filename   = "../../../pwnagotchi-raspios-bullseye-${var.pwn_version}-arm64.img"
  qemu_binary       = "qemu-aarch64-static"
  target_image_size = 9368709120
  qemu_args         = ["-r", "6.1.21-v8+"]
  image_type        = "raspberrypi"
}
source "opi-pwnagotchi" {
  iso_checksum      = "5d04108012535f9158c414df65ae011f76fced8b49b58edef330d06650326683"
  iso_url           = "https://drive.usercontent.google.com/download?id=13w2L3aJo5kBrJ0obTnYlQsqFWzfEV-F7&export=download&authuser=0&confirm=t&uuid=577e6671-3b0a-4a29-8172-6ee16bbd7247&at=APZUnTVwVS-jUEVayHulBfPkzWkp:1698620550044"
  output_filename   = "../../../pwnagotchi-orangepi-jammy-${var.pwn_version}-arm64.img"
  qemu_binary       = "qemu-aarch64-static"
  target_image_size = 9368709120
  qemu_args         = ["-r", "6.1.31-sun50iw9"]
  image_type        = "ubuntu"
}

# a build block invokes sources and runs provisioning steps on them. The
# documentation for build blocks can be found here:
# https://www.packer.io/docs/from-1.5/blocks/build
build {
  name = "Pwnagotchi Torch 64bit"
  sources = [
    "source.rpi-pwnagotchi",
    "source.opi-pwnagotchi",
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
