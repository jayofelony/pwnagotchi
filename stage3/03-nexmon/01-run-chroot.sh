#!/bin/bash -e

cd /home/pi
wget https://kali.download/kali/pool/non-free-firmware/f/firmware-nexmon/firmware-nexmon_0.2_all.deb
wget https://github.com/jayofelony/brcmfmac-nexmon-dkms/releases/download/v6.12.2%2Bndevfix3/brcmfmac-nexmon-dkms_6.12.2%2Bndevfix3_all.deb

dpkg -i firmware-nexmon_0.2_all.deb brcmfmac-nexmon-dkms_6.12.2+ndevfix3_all.deb
rm -r firmware-nexmon_0.2_all.deb brcmfmac-nexmon-dkms_6.12.2+ndevfix3_all.deb

apt-get remove -y firmware-brcm80211