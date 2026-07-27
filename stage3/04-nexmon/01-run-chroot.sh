#!/bin/bash -e

cd /home/pi
wget https://kali.download/kali/pool/non-free-firmware/f/firmware-nexmon/firmware-nexmon_0.2_all.deb
wget https://http.kali.org/kali/pool/contrib/b/brcmfmac-nexmon-dkms/brcmfmac-nexmon-dkms_6.12.2_all.deb

apt-get remove firmware-brcm80211

dpkg -i firmware-nexmon_0.2_all.deb brcmfmac-nexmon-dkms_6.12.2_all.deb
rm -r firmware-nexmon_0.2_all.deb brcmfmac-nexmon-dkms_6.12.2_all.deb