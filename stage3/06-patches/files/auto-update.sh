#!/usr/bin/env bash
# Standalone updater for pwnagotchi itself, independent of the running
# pwnagotchi process (see pwnagotchi/plugins/default/auto-update.py for the
# in-process updater that still handles bettercap/pwngrid). Runs from
# auto-update.timer so a fatal bug that crash-loops pwnagotchi.service can
# still be fixed by a later git pull, without needing the Python process to
# ever come up.

REPO_DIR="/opt/pwnagotchi"

if ! wget -q --spider https://github.com; then
  echo "no internet access, skipping update check"
  exit 0
fi

if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR" || exit 1
  git fetch --quiet
  local_rev=$(git rev-parse HEAD)
  remote_rev=$(git rev-parse '@{u}')
  if [ "$local_rev" = "$remote_rev" ]; then
    echo "pwnagotchi is already up to date"
    exit 0
  fi
  git pull --quiet
else
  git clone --quiet https://github.com/jayofelony/pwnagotchi.git "$REPO_DIR"
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
    cp -f "$src" "$dest"
    chmod "$mode" "$dest"
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
sync_file "01-motd" "/etc/update-motd.d/01-motd" 755
sync_file "pwnagotchi.service" "/etc/systemd/system/pwnagotchi.service" 644
sync_file "bettercap.service" "/etc/systemd/system/bettercap.service" 644
sync_file "pwngrid-peer.service" "/etc/systemd/system/pwngrid-peer.service" 644
sync_file "auto-update.service" "/etc/systemd/system/auto-update.service" 644
sync_file "auto-update.timer" "/etc/systemd/system/auto-update.timer" 644
sync_file "profile" "/etc/profile" 644

if [ "$reload_units" -eq 1 ]; then
  systemctl daemon-reload
fi

echo "pwnagotchi updated, rebooting ..."
reboot
