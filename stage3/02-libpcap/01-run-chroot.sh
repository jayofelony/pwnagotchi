#!/bin/bash -e
#
# 03-old-libpcap
#
# Install version 1.9 of libpcap for backwards compatibility

if [ -e /usr/local/lib/libpcap.so.1.9.1 ]; then
    echo -e "\e[32m=== Libpcap already installed ===\e[0m"
else
    echo -e "\e[32m=== Installing libpcap 1.9 ===\e[0m"
    cd /usr/local/src
    if [ ! -d libpcap ]; then
	    git clone -b libpcap-1.9 https://github.com/the-tcpdump-group/libpcap.git
    fi
    cd libpcap
    ./configure && make && make install
    LIBPCAPOK=$?

    if [ "$LIBPCAPOK" ]; then
        rm -rf libpcap
        echo -e "\e[32m=== Linking libpcap-1.9.1 to libpcap.so.0.8 ===\e[0m"
        ln -sf /usr/local/lib/libpcap.so.1.9.1 /usr/local/lib/libpcap.so.0.8
    else
	    echo -e "\e[32m=== Not deleting libpcap ===\e[0m"
    fi
    echo
    echo -e "\e[32m=== Libpcap installed ===\e[0m"
fi
