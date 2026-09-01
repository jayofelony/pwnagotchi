#!/bin/bash -e
export PATH=$PATH:/usr/local/go/bin:/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin


# Under QEMU emulation (cross-building arm64 on x86), Go's signal-based async
# preemption deadlocks and the multi-threaded compiler hangs. Constrain Go only
# when emulated so native arm64 builders keep full parallelism.
if [ -e /usr/bin/qemu-aarch64-static ] || [ -e /usr/bin/qemu-aarch64 ] || \
   [ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
    echo "[build] QEMU emulation detected - constraining Go build (asyncpreempt off, single-thread)"
    export GODEBUG=asyncpreemptoff=1
    export GOMAXPROCS=1
fi

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
            git checkout pcapng
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
            git clone --recurse-submodules --branch pcapng https://github.com/jayofelony/bettercap.git
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
