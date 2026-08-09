#!/bin/bash -e
echo -e "\e[32m### Verifying PwnStore CLI ###\e[0m"
if [ ! -f /usr/bin/pwnstore ]; then
    echo -e "\e[31m[!] pwnstore CLI not found!\e[0m"
    exit 1
fi
echo -e "\e[32m### PwnStore OK ###\e[0m"
