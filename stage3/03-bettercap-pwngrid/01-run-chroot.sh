#!/bin/bash -e

export PATH=$PATH:/usr/local/go/bin

FOUNDARCH="armv6l"
if [ $(uname -m) = "armv6l" -o $(uname -m) = "armv7l" ]; then
    export FOUNDARCH=armv6l
elif [ $(uname -m) = "aarch64" ]; then
    export FOUNDARCH=arm64
elif [ $(uname -m) = "x86_64" ]; then
    export FOUNDARCH=amd64
fi

export version=1.22.5

FILE=go${version}.linux-${FOUNDARCH}.tar.gz

echo -e "\e[32m=== GOlang $FILE ===\e[0m"

if ! /usr/local/go/bin/go version | grep ${version}; then
    echo -e "\e[32m=== Installing ===\e[0m"

    pushd /tmp
    if curl -OL "https://go.dev/dl/${FILE}" && rm -rf /usr/local/go && tar -C /usr/local -xzf "${FILE}"; then
	    echo -e "\e[32m=== Go is installed ===\e[0m"
    else
	    echo -e "\e[32m=== No go. lang. ===\e[0m"
    fi
    rm ${FILE}
    popd
fi

echo "export PATH=$PATH:/usr/local/go/bin" > /etc/profile