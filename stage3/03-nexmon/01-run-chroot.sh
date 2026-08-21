#!/bin/bash -e

cd /home/pi
wget https://kali.download/kali/pool/non-free-firmware/f/firmware-nexmon/firmware-nexmon_0.2_all.deb

NEXMON_REPO="jayofelony/brcmfmac-nexmon-dkms"
latest_tag=$(wget -qO- "https://api.github.com/repos/${NEXMON_REPO}/releases/latest" | sed -n 's/.*"tag_name": *"\(v[^"]*\)".*/\1/p')
if [ -z "$latest_tag" ]; then
  echo "could not determine latest nexmon driver release" >&2
  exit 1
fi
latest_ver="${latest_tag#v}"
nexmon_deb="brcmfmac-nexmon-dkms_${latest_ver}_all.deb"
wget "https://github.com/${NEXMON_REPO}/releases/download/${latest_tag//+/%2B}/${nexmon_deb}"

apt-get remove -y firmware-brcm80211
apt-get install -y /home/pi/firmware-nexmon_0.2_all.deb "/home/pi/${nexmon_deb}"
rm -r firmware-nexmon_0.2_all.deb "${nexmon_deb}"