# Pwnagotchi Torch installation
I assume you have a new image of Raspberry Pi OS lite 64-bit flashed to a micro sd-card.

# APT hold packages
```
sudo apt-mark hold raspberrypi-kernel
sudo apt install raspberrypi-kernel-headers
sudo apt-mark hold raspberrypi-kernel-headers
sudo apt -y update
sudo apt -y upgrade
```
# Downgrade libpcap
```
cd ~
wget http://ports.ubuntu.com/pool/main/libp/libpcap/libpcap0.8_1.9.1-3_arm64.deb
wget http://ports.ubuntu.com/pool/main/libp/libpcap/libpcap0.8-dev_1.9.1-3_arm64.deb
wget http://ports.ubuntu.com/pool/main/libp/libpcap/libpcap-dev_1.9.1-3_arm64.deb
sudo apt -y install ./libpcap*.deb  --allow-downgrades
sudo apt-mark hold libpcap-dev libpcap0.8 libpcap0.8-dev
```

# Set-up dependencies
```
cat > /tmp/dependencies << EOF
time
rsync
vim
wget
screen
git
build-essential
dkms
python3-pip  
python3-smbus
unzip
gawk
libopenmpi-dev
libatlas-base-dev
libelf-dev
libopenjp2-7
libtiff5
tcpdump
lsof
libgstreamer1.0-0
libavcodec58
libavformat58
libswscale5
libusb-1.0-0-dev
libnetfilter-queue-dev
libopenmpi3
dphys-swapfile
libdbus-1-dev 
libdbus-glib-1-dev
liblapack-dev 
libhdf5-dev 
libc-ares-dev 
libeigen3-dev
fonts-dejavu
fonts-dejavu-core
fonts-dejavu-extra
python3-pil
python3-smbus
libfuse-dev
libatlas-base-dev 
libopenblas-dev 
libblas-dev
bc
libgl1-mesa-glx
libncursesw5-dev 
libssl-dev 
libsqlite3-dev 
tk-dev 
libgdbm-dev 
libc6-dev 
libbz2-dev 
libffi-dev 
zlib1g-dev
fonts-freefont-ttf
fbi
python3-flask
python3-flask-cors
python3-flaskext.wtf
EOF

cat /tmp/dependencies | xargs -n5 sudo apt install -y
```

# Install Bettercap
```
cd ~
git clone https://github.com/jayofelony/bettercap.git
cd bettercap
make all
sudo make install
sudo bettercap -eval "caplets.update; ui.update; quit"
sudo nano /usr/local/share/bettercap/caplets/pwnagotchi-auto.cap # change iface to wlan0
sudo nano /usr/local/share/bettercap/caplets/pwnagotchi-manual.cap # change iface to wlan0
```

# Install PwnGrid
```
cd ~
git clone https://github.com/jayofelony/pwngrid.git
cd bettercap
make
sudo make install
sudo pwngrid -generate -keys /etc/pwnagotchi
```

# Install Pwnagotchi-Torch
```
cd ~
git clone -b pwnagotchi-torch https://github.com/jayofelony/pwnagotchi.git
cd pwnagotchi
for i in $(grep -v ^# requirements.txt | cut -d \> -f 1); do sudo apt -y install python3-$i; done
sudo pip install -r requirements.txt
sudo pip install --upgrade numpy
sudo ln -s `pwd`/bin/pwnagotchi /usr/local/bin
sudo ln -s `pwd`/pwnagotchi /usr/local/lib/python3.9/dist-packages/pwnagotchi
sudo mkdir -p /usr/local/share/pwnagotchi/custom-plugins


sudo bash -c 'cat > /etc/pwnagotchi/config.toml' << EOF
main.name = "new_ai_CHANGEME"
main.custom_plugins = "/usr/local/share/pwnagotchi/custom-plugins"

main.plugins.led.enabled = false

personality.deauth = false

ui.display.enabled = false
ui.web.username = "pwny"
ui.web.password = "pwny1234"
EOF

for file in `find builder/data -type f`; do
  dest=${file#builder/data}
  if [ -s $dest ]; then
    echo File $dest exists. Skipping
  else
    echo Copying $file to $dest
    sudo cp -p $file $dest
  fi
done
```

# Enable all services and reboot
```
sudo systemctl enable bettercap
sudo systemctl enable pwngrid-peer
sudo systemctl enable pwnagotchi

sudo sync
sudo reboot
```
