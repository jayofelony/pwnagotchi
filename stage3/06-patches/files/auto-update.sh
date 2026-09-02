#!/usr/bin/env bash
# Standalone updater for pwnagotchi itself, independent of the running
# pwnagotchi process (see pwnagotchi/plugins/default/auto-update.py for the
# in-process updater that still handles bettercap/pwngrid). Runs from
# auto-update.timer so a fatal bug that crash-loops pwnagotchi.service can
# still be fixed by a later update, without needing the Python process to
# ever come up.
#
# Scope: this script updates *only* the pwnagotchi package, and only when the
# repo publishes a release tag newer than what's installed. When it does
# update, it also refreshes the device-side system files (scripts, systemd
# units) that ship alongside the package but live outside the venv, because a
# pip install alone would leave them at the old version.

REPO_DIR="/opt/pwnagotchi"
REPO_URL="https://github.com/jayofelony/pwnagotchi.git"

if ! wget -q --spider https://github.com; then
  echo "no internet access, skipping update check"
  exit 0
fi

# pwnagotchi ships pre-installed on the image, but the repo checkout used to
# build it is deleted afterward (see stage3/04-install-pwnagotchi), so
# $REPO_DIR/.git may not exist even on an up-to-date, fully installed system.
# Check the installed version against the latest published GitHub release
# (not the raw branch tip, which can already be bumped ahead of the last
# actual release for in-progress work) and only clone/pull when an update
# to that release is actually needed.
current_version=$(pwnagotchi --version 2>/dev/null)
latest_tag=$(wget -qO- "https://api.github.com/repos/jayofelony/pwnagotchi/releases/latest" | sed -n 's/.*"tag_name": *"\(v[^"]*\)".*/\1/p')

if [ -z "$latest_tag" ]; then
  echo "could not determine latest pwnagotchi release, skipping update check"
  exit 0
fi

remote_version="${latest_tag#v}"

# true if $1 is a newer-or-equal version than $2 (GNU sort -V version compare)
version_ge() {
  [ "$1" = "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1)" ]
}

if [ -n "$current_version" ] && version_ge "$current_version" "$remote_version"; then
  if [ "$current_version" = "$remote_version" ]; then
    echo "pwnagotchi is already up to date ($current_version)"
  else
    echo "installed pwnagotchi ($current_version) is newer than the latest release ($remote_version), not downgrading"
  fi
  exit 0
fi

echo "updating pwnagotchi ($current_version -> $remote_version) ..."

if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR" || exit 1
  git fetch --quiet --tags
  git reset --quiet --hard "$latest_tag"
else
  git clone --quiet --branch "$latest_tag" "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR" || exit 1
fi

echo "installing updated pwnagotchi ..."
source /opt/.pwn/bin/activate
pip3 install "$REPO_DIR" --no-cache-dir
deactivate

# Sync the same non-Python system files the in-process updater whitelists
# (see SYSTEM_FILES in pwnagotchi/plugins/default/auto-update.py) - a pip
# install only reaches the venv, so scripts/units living outside it need to
# be copied out of the freshly pulled repo separately.
SYSTEM_FILES_DIR="$REPO_DIR/stage3/06-patches/files"
reload_units=0

sync_file() {
  src="$SYSTEM_FILES_DIR/$1"
  dest="$2"
  mode="$3"
  if [ ! -f "$src" ]; then
    echo "system file $1 missing from repo, skipping"
    return
  fi
  if ! cmp -s "$src" "$dest"; then
    tmp="$(mktemp "${dest}.XXXXXX")"
    cp -f "$src" "$tmp"
    chmod "$mode" "$tmp"
    mv -f "$tmp" "$dest"
    echo "synced $1 -> $dest"
    case "$dest" in
      *.service|*.timer) reload_units=1 ;;
    esac
  fi
}

sync_file "pwnlib" "/usr/bin/pwnlib" 755
sync_file "bettercap-launcher" "/usr/bin/bettercap-launcher" 755
sync_file "pwnagotchi-launcher" "/usr/bin/pwnagotchi-launcher" 755
sync_file "auto-update.sh" "/usr/bin/auto-update.sh" 755
sync_file "brcmfmac-watchdog.sh" "/usr/bin/brcmfmac-watchdog.sh" 755
sync_file "01-motd" "/etc/update-motd.d/01-motd" 755
sync_file "pwnagotchi.service" "/etc/systemd/system/pwnagotchi.service" 644
sync_file "pwnagotchi-usb-gadget.service" "/etc/systemd/system/pwnagotchi-usb-gadget.service" 644
sync_file "bettercap.service" "/etc/systemd/system/bettercap.service" 644
sync_file "pwngrid-peer.service" "/etc/systemd/system/pwngrid-peer.service" 644
sync_file "auto-update.service" "/etc/systemd/system/auto-update.service" 644
sync_file "auto-update.timer" "/etc/systemd/system/auto-update.timer" 644
sync_file "brcmfmac-watchdog.service" "/etc/systemd/system/brcmfmac-watchdog.service" 644
sync_file "profile" "/etc/profile" 644

if [ "$reload_units" -eq 1 ]; then
  systemctl daemon-reload
fi

# Devices imaged before brcmfmac-watchdog.service existed will have just had
# the unit file synced in above for the first time, but a plain file on disk
# doesn't start on boot unless it's enabled - only fresh images get that for
# free, via stage3/06-patches/01-run-chroot.sh at build time. `enable` is
# idempotent, so this is safe to run unconditionally on every update rather
# than trying to detect "is this the first time" - it converges an
# already-enabled or even a previously-half-applied device to the same state.
systemctl enable brcmfmac-watchdog.service pwnagotchi-usb-gadget.service

# pip install already copied the package into the venv and sync_file copied
# out the system files it needs, so the clone itself is just clutter now.
rm -rf "$REPO_DIR"

echo "pwnagotchi updated, rebooting ..."
sync
reboot
