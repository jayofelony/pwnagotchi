packer {
  required_plugins {
    ansible = {
      source  = "github.com/hashicorp/ansible"
      version = ">= 1.1.1"
    }
  }
}

variable "pwn_hostname" {
  type = string
}

variable "pwn_version" {
  type = string
}

source "arm-image" "rpi64-pwnagotchi" {
  image_type      = "raspberrypi"
  iso_url         = "https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2024-03-15/2024-03-15-raspios-bookworm-arm64-lite.img.xz"
  iso_checksum    = "sha256:58a3ec57402c86332e67789a6b8f149aeeb4e7bb0a16c9388a66ea6e07012e45"
  output_filename = "../../../pwnagotchi-64bit.img"
  qemu_binary     = "qemu-aarch64-static"
  target_image_size =  9969908736
  last_partition_extra_size = 9221225472
}

source "arm-image" "rpi32-pwnagotchi" {
  image_type      = "raspberrypi"
  iso_url         = "https://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2024-03-15/2024-03-15-raspios-bookworm-armhf-lite.img.xz"
  iso_checksum    = "sha256:4fa99737265ac338a9ed0643f502246b97b928e5dfffa92939242e26e290638d"
  output_filename = "../../../pwnagotchi-32bit.img"
  qemu_binary     = "qemu-arm-static"
  qemu_args       = ["-cpu", "arm1176"]
  image_arch      = "arm"
  target_image_size = 9969908736
  last_partition_extra_size = 9221225472
}

# a build block invokes sources and runs provisioning steps on them. The
# documentation for build blocks can be found here:
# https://www.packer.io/docs/from-1.5/blocks/build
build {
  name = "Raspberry Pi 64 Pwnagotchi"
  sources = ["source.arm-image.rpi64-pwnagotchi"]

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
  provisioner "shell" {
    inline = ["mkdir -p /usr/local/src/pwnagotchi"]
  }
  provisioner "file" {
    destination = "/usr/local/src/pwnagotchi/"
    source = "../"
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
    playbook_file   = "raspberrypi64.yml"
  }
}

build {
  name = "Raspberry Pi 32 Pwnagotchi"
  sources = ["source.arm-image.rpi32-pwnagotchi"]
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
    inline = ["mkdir -p /usr/local/src/pwnagotchi"]
  }
  provisioner "file" {
    destination = "/usr/local/src/pwnagotchi/"
    source = "../"
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
    playbook_file   = "raspberrypi32.yml"
  }
}