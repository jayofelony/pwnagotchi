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

source "arm-image" "rpi-pwnagotchi" {
  iso_checksum      = "file:https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz.sha256"
  iso_url           = "https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz"
  output_filename   = "../../../pwnagotchi-raspios-bullseye-${var.pwn_version}-arm64.img"
  qemu_binary       = "qemu-aarch64-static"
  target_image_size = 9368709120
  qemu_args         = ["-r", "6.1.21-v8+"]
}
source "arm-image" "opi-pwnagotchi" {
  iso_checksum      = "file:https://doc-14-8c-docs.googleusercontent.com/docs/securesc/tmchfcq82fjjcmpsliro1lut4j8lshoa/mfl1ot33ra955uqrrcganrjb5n361oki/1698618150000/11383713845321559498/11383713845321559498/16RJKx0pGdr4AHBgnZbx63y9mtR8qxAzX?e=download&ax=AI0foUrUoJ52tCd4fIlmtmoq7S8jTw8SK2JQMa9SxMkJnVfC5JtENeSqFZDF8MLzpe-re_F3yntxgSQCO3lIkWVoP_MFQkfGAztC-bjWQptRV_5ShEUvomV0pKhQmpPYpQUVB53Z2zgPHhmvf1pwCI38AZmjUD9DPE1ualRB5vEe7B7k-P5_DdSwAQaITqiv3sEOKEHlgYF64GAuh7A80lF_VxpQfdaRfvzNpjwzdll6pWYy9AOT32xd2vSDGA3VgJwlSORxhH9pH2wPSo4QYojtyOjmbyLz76Xg8JacZDmi6AQ0bupYw01VcB4LiSL5-9eOKCRTGZOAK05eWGN5Z4roOLLkb-wgJ-Ege6ll7gapdKgYPBY4cRVom2Z-ojUfi8_kT9KshlV-LYsfr7vP66EOa02q6x2-lThWQBIN9fzjW1Me0V00P1m6sfbGJeae8oFBchBRxKvGzFwRejqiGD5ICAB2uGl6K7zTnmN2dG_CieNNXTuRqi98iQw43MtEUSv4JqCVud75lFdp9LQjxlHl1B_jem0eCfeSVCONlmaLu9nsH9qxn9LS-1bN6yQFXtMioxz-QPOt7azmYxbjKMBoM3lEGHldUr5CfkYHV3lmbwcG9ieto8ZxJqCTBdiQPK9vxl_uh1xfN-96DV474exd_VSaC6qxTbBC7_ao9KClngrg61Fx36AAVRm5b6DuvuRCbEYLMIjaMe_FGtdhVve9_epkD3OCA0omJC-lQH6j1x0yWsfVLG6RX7gmHCfNAuDWDROGQ8-9Hrd1BkzFBYuOAQMo90GXhe41GbyJTdjHbIfUmTM9n3YdI7ygcYxeubEgBDeMPUkULgTAjliKamR4AYeoPWriO4tYrkjQZlJa4A8coQKzt8WJ6fL2jvXqhD522w&uuid=8e13d075-d5a8-44ea-8f34-ce5e40146737&authuser=0&nonce=4l3o21nfe78r4&user=11383713845321559498&hash=uj6abem75hc2v133ebhrv9689onfvkef"
  iso_url           = "https://doc-14-8c-docs.googleusercontent.com/docs/securesc/tmchfcq82fjjcmpsliro1lut4j8lshoa/mfl1ot33ra955uqrrcganrjb5n361oki/1698618150000/11383713845321559498/11383713845321559498/16RJKx0pGdr4AHBgnZbx63y9mtR8qxAzX?e=download&ax=AI0foUrUoJ52tCd4fIlmtmoq7S8jTw8SK2JQMa9SxMkJnVfC5JtENeSqFZDF8MLzpe-re_F3yntxgSQCO3lIkWVoP_MFQkfGAztC-bjWQptRV_5ShEUvomV0pKhQmpPYpQUVB53Z2zgPHhmvf1pwCI38AZmjUD9DPE1ualRB5vEe7B7k-P5_DdSwAQaITqiv3sEOKEHlgYF64GAuh7A80lF_VxpQfdaRfvzNpjwzdll6pWYy9AOT32xd2vSDGA3VgJwlSORxhH9pH2wPSo4QYojtyOjmbyLz76Xg8JacZDmi6AQ0bupYw01VcB4LiSL5-9eOKCRTGZOAK05eWGN5Z4roOLLkb-wgJ-Ege6ll7gapdKgYPBY4cRVom2Z-ojUfi8_kT9KshlV-LYsfr7vP66EOa02q6x2-lThWQBIN9fzjW1Me0V00P1m6sfbGJeae8oFBchBRxKvGzFwRejqiGD5ICAB2uGl6K7zTnmN2dG_CieNNXTuRqi98iQw43MtEUSv4JqCVud75lFdp9LQjxlHl1B_jem0eCfeSVCONlmaLu9nsH9qxn9LS-1bN6yQFXtMioxz-QPOt7azmYxbjKMBoM3lEGHldUr5CfkYHV3lmbwcG9ieto8ZxJqCTBdiQPK9vxl_uh1xfN-96DV474exd_VSaC6qxTbBC7_ao9KClngrg61Fx36AAVRm5b6DuvuRCbEYLMIjaMe_FGtdhVve9_epkD3OCA0omJC-lQH6j1x0yWsfVLG6RX7gmHCfNAuDWDROGQ8-9Hrd1BkzFBYuOAQMo90GXhe41GbyJTdjHbIfUmTM9n3YdI7ygcYxeubEgBDeMPUkULgTAjliKamR4AYeoPWriO4tYrkjQZlJa4A8coQKzt8WJ6fL2jvXqhD522w&uuid=8e13d075-d5a8-44ea-8f34-ce5e40146737&authuser=0&nonce=4l3o21nfe78r4&user=11383713845321559498&hash=uj6abem75hc2v133ebhrv9689onfvkef"
  output_file       ="../../../pwnagotchi-orangepi-bullseye-${var.pwn_version}-arm64.img"
  qemu_binary       = "qemu-aarch64-static"
  target_image_size = 9368709120
  qemu_args         = ["-r", "6.1.31-sun50iw9"]
}

# a build block invokes sources and runs provisioning steps on them. The
# documentation for build blocks can be found here:
# https://www.packer.io/docs/from-1.5/blocks/build
build {
  name = "Pwnagotchi Torch 64bit"
  sources = [
    "source.arm-image.opi-pwnagotchi",
    "source.arm-image.rpi-pwnagotchi",
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
