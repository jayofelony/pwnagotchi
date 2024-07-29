packer {
  required_plugins {
    arm-image = {
      source  = "github.com/solo-io/arm-image"
      version = ">= 0.0.1"
    }
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

source "arm-image" "rpi32-pwnagotchi" {
  image_type      = "raspberrypi"
  iso_url         = "https://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2024-07-04/2024-07-04-raspios-bookworm-armhf-lite.img.xz"
  iso_checksum    = "sha256:df9c192d66d35e1ce67acde33a5b5f2b81ff02d2b986ea52f1f6ea211d646a1b"
  output_filename = "../../../pwnagotchi-32bit.img"
  qemu_binary     = "qemu-arm-static"
  qemu_args       = ["-cpu", "arm1176"]
  image_arch      = "arm"
  image_mounts    = ["/boot/firmware","/"]
  target_image_size = 19969908736
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