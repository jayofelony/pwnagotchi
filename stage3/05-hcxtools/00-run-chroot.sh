#!/bin/bash -e

cd /usr/local/src/

echo -e "\e[32m=== Installing hcxtools ===\e[0m"
if [ ! -f /usr/bin/hcxpcapngtool ]; then
    git clone https://github.com/ZerBea/hcxtools.git hcxtools
    cd hcxtools
    make
    make install
    rm -r /usr/local/src/hcxtools
fi
