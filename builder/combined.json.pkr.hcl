packer {
  required_plugins {
    arm = {
      version = "1.0.0"
      source  = "github.com/cdecoux/builder-arm"
    }
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
  image_path                    = "../../../pwnagotchi-64bit.img"
  qemu_binary_source_path       = "/usr/libexec/qemu-binfmt/aarch64-binfmt-P"
  qemu_binary_destination_path  = "/usr/libexec/qemu-binfmt/aarch64-binfmt-P"
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

source "arm" "rpi32-pwnagotchi" {
  file_checksum_url             = "https://downloads.raspberrypi.com/raspios_oldstable_lite_armhf/images/raspios_oldstable_lite_armhf-2023-12-06/2023-12-05-raspios-bullseye-armhf-lite.img.xz.sha256"
  file_urls                     = ["https://downloads.raspberrypi.com/raspios_oldstable_lite_armhf/images/raspios_oldstable_lite_armhf-2023-12-06/2023-12-05-raspios-bullseye-armhf-lite.img.xz"]
  file_checksum_type            = "sha256"
  file_target_extension         = "xz"
  file_unarchive_cmd            = ["unxz", "$ARCHIVE_PATH"]
  image_path                    = "../../pwnagotchi-32bit.img"
  qemu_binary_source_path       = "/usr/libexec/qemu-binfmt/arm-binfmt-P"
  qemu_binary_destination_path  = "/usr/libexec/qemu-binfmt/arm-binfmt-P"
  image_build_method            = "resize"
  image_size                    = "9G"
  image_type                    = "dos"
  image_partitions {
    name         = "boot"
    type         = "c"
    start_sector = "8192"
    filesystem   = "fat"
    size         = "256M"
    mountpoint   = "/boot"
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
      "data/64bit/usr/bin/bettercap-launcher",
      "data/64bit/usr/bin/hdmioff",
      "data/64bit/usr/bin/hdmion",
      "data/64bit/usr/bin/monstart",
      "data/64bit/usr/bin/monstop",
      "data/64bit/usr/bin/pwnagotchi-launcher",
      "data/64bit/usr/bin/pwnlib",
    ]
  }
  provisioner "shell" {
    inline = ["chmod +x /usr/bin/*"]
  }

  provisioner "file" {
    destination = "/etc/systemd/system/"
    sources     = [
      "data/64bit/etc/systemd/system/bettercap.service",
      "data/64bit/etc/systemd/system/pwnagotchi.service",
      "data/64bit/etc/systemd/system/pwngrid-peer.service",
    ]
  }
  provisioner "file" {
    destination = "/etc/update-motd.d/01-motd"
    source      = "data/64bit/etc/update-motd.d/01-motd"
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
    playbook_file   = "data/64bit/raspberrypi64.yml"
  }
}

build {
  name = "Raspberry Pi 32 Pwnagotchi"
  sources = ["source.arm.rpi32-pwnagotchi"]
  provisioner "file" {
    destination = "/usr/bin/"
    sources     = [
      "data/32bit/usr/bin/bettercap-launcher",
      "data/32bit/usr/bin/hdmioff",
      "data/32bit/usr/bin/hdmion",
      "data/32bit/usr/bin/monstart",
      "data/32bit/usr/bin/monstop",
      "data/32bit/usr/bin/pwnagotchi-launcher",
      "data/32bit/usr/bin/pwnlib",
    ]
  }
  provisioner "shell" {
    inline = ["chmod +x /usr/bin/*"]
  }

  provisioner "file" {
    destination = "/etc/systemd/system/"
    sources     = [
      "data/32bit/etc/systemd/system/bettercap.service",
      "data/32bit/etc/systemd/system/pwnagotchi.service",
      "data/32bit/etc/systemd/system/pwngrid-peer.service",
    ]
  }
  provisioner "file" {
    destination = "/etc/update-motd.d/01-motd"
    source      = "data/32bit/etc/update-motd.d/01-motd"
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
    playbook_dir    = "data/32bit/extras/"
    playbook_file   = "data/32bit/pwnagotchi.yml"
  }
}