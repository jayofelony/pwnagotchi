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

# always install whatever the latest stable release is, per https://go.dev/doc/install,
# instead of hand-pinning a version that has to be bumped every time go.mod moves on
version="$(curl -fsSL 'https://go.dev/VERSION?m=text' | head -1)"

FILE=${version}.linux-${FOUNDARCH}.tar.gz

echo -e "\e[32m=== GOlang $FILE ===\e[0m"

if ! /usr/local/go/bin/go version 2>/dev/null | grep -qF "${version}"; then
    echo -e "\e[32m=== Installing ${version} ===\e[0m"

    pushd /tmp
    if curl -OL "https://go.dev/dl/${FILE}" && sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf "${FILE}"; then
	    echo -e "\e[32m=== Go is installed ===\e[0m"
    else
	    echo -e "\e[32m=== No go. lang. ===\e[0m"
    fi
    rm -f ${FILE}
    popd
fi

# make sure it's usable by every user (root during this build, "pi" afterwards),
# not just whoever originally extracted the tarball
chmod -R a+rX /usr/local/go

# reachable in login shells...
tee /etc/profile.d/golang.sh > /dev/null <<'EOF'
export PATH=$PATH:/usr/local/go/bin
EOF
chmod 644 /etc/profile.d/golang.sh

# ...and in non-login/non-interactive shells too (e.g. `ssh pi@host some-command`),
# which don't source /etc/profile at all
ln -sf /usr/local/go/bin/go /usr/local/bin/go
ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt