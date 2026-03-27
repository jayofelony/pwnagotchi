#!/bin/bash -e

export PATH=$PATH:/usr/local/go/bin:/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin

# install go packages
for pkg in bettercap pwngrid; do
    if [ -d "/home/pi/"/$pkg ] ; then
        echo -e "\e[32m===> Installing $pkg ===\e[0m"
        if [ $pkg = "pwngrid" ]; then
            cd "/home/pi/pwngrid"
            git pull
            go mod tidy
            make
            make install
        elif [ $pkg = "bettercap" ]; then
            cd "/home/pi/bettercap"
            git pull
            go mod tidy
            make
            make install
        fi
    else
        echo -e "\e[32m===> Installing $pkg ===\e[0m"
        if [ $pkg = "pwngrid" ]; then
            cd "/home/pi"
            git clone https://github.com/jayofelony/pwngrid.git
            cd "/home/pi/pwngrid"
            go mod tidy
            make
            make install
        elif [ $pkg = "bettercap" ]; then
            cd "/home/pi"
            git clone --recurse-submodules https://github.com/bettercap/bettercap.git
            cd "/home/pi/bettercap"
            go mod tidy
            make
            make install
        fi
    fi
done
# install bettercap caplets
echo -e "\e[32m=== Installing bettercap caplets ===\e[0m"
cd "/home/pi/"
git clone https://github.com/jayofelony/caplets.git
cd "/home/pi/caplets"
make install
rm -rf "/home/pi/caplets"