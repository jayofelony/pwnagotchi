import os
import re
import logging
import subprocess
import requests
import platform
import shutil
import glob
import filecmp
from threading import Lock
import time

import pwnagotchi
import pwnagotchi.plugins as plugins
from pwnagotchi.utils import StatusFile, parse_version as version_to_tuple

# Non-Python system files that live outside the pip-installed package (scripts under
# /usr/bin, systemd units) but still ship in the pwnagotchi repo under stage3/06-patches/files.
# A pip install can never reach these (it's confined to the venv), so they're synced here
# instead, whitelisted deliberately: config/secrets/boot-critical files (sudoers,
# config.txt, user-data, dphys-swapfile) are intentionally excluded and must never be added here.
SYSTEM_FILES = [
    # (path within the downloaded repo archive, absolute destination, mode)
    ("stage3/06-patches/files/pwnlib", "/usr/bin/pwnlib", 0o755),
    ("stage3/06-patches/files/bettercap-launcher", "/usr/bin/bettercap-launcher", 0o755),
    ("stage3/06-patches/files/pwnagotchi-launcher", "/usr/bin/pwnagotchi-launcher", 0o755),
    ("stage3/06-patches/files/auto-update.sh", "/usr/bin/auto-update.sh", 0o755),
    ("stage3/06-patches/files/01-motd", "/etc/update-motd.d/01-motd", 0o755),
    ("stage3/06-patches/files/pwnagotchi.service", "/etc/systemd/system/pwnagotchi.service", 0o644),
    ("stage3/06-patches/files/bettercap.service", "/etc/systemd/system/bettercap.service", 0o644),
    ("stage3/06-patches/files/pwngrid-peer.service", "/etc/systemd/system/pwngrid-peer.service", 0o644),
    ("stage3/06-patches/files/auto-update.service", "/etc/systemd/system/auto-update.service", 0o644),
    ("stage3/06-patches/files/auto-update.timer", "/etc/systemd/system/auto-update.timer", 0o644),
    ("stage3/06-patches/files/profile", "/etc/profile", 0o644)
]


def sync_system_files(repo_root):
    """
    Copies the whitelisted system files (scripts, systemd units) out of a freshly
    downloaded pwnagotchi repo archive onto the real filesystem, so fixes to them
    reach existing installations without a reflash. Relies on the caller (install()) to
    reboot afterward, which is what actually picks up changed systemd units / re-execs
    launcher scripts - this function only ever copies files, it never restarts anything.
    """
    changed = 0
    reload_units = False

    for rel_src, dest, mode in SYSTEM_FILES:
        src = os.path.join(repo_root, rel_src)
        if not os.path.isfile(src):
            logging.warning("[update] system file %s missing from downloaded archive, skipping" % rel_src)
            continue

        try:
            if os.path.exists(dest) and filecmp.cmp(src, dest, shallow=False):
                continue

            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp_dest = "%s.tmp" % dest
            shutil.copyfile(src, tmp_dest)
            os.chmod(tmp_dest, mode)
            os.replace(tmp_dest, dest)
            changed += 1
            if dest.endswith(".service"):
                reload_units = True
            logging.info("[update] synced system file %s -> %s" % (rel_src, dest))
        except OSError:
            logging.exception("[update] failed to sync system file %s -> %s" % (rel_src, dest))

    if reload_units:
        subprocess.run(["systemctl", "daemon-reload"], check=True)

    if changed:
        logging.info("[update] synced %d system file(s)" % changed)

    return changed > 0


def check(version, repo, native=True, token=""):
    logging.debug("checking remote version for %s, local is %s" % (repo, version))
    info = {
        'repo': repo,
        'current': version,
        'available': None,
        'url': None,
        'native': native,
        'arch': platform.machine()
    }

    headers = {}
    if token != "":
        headers['Authorization'] = f'token {token}'
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", headers=headers)
    else:
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases/latest")


    if resp.status_code != 200:
        logging.error(f"[Auto-Update] Failed to get latest release for {repo}: {resp.status_code}")
        return info

    remaining_requests = resp.headers.get('X-RateLimit-Remaining')
    logging.debug(f"[Auto-Update] Requests remaining: {remaining_requests}")

    latest = resp.json()
    info['available'] = latest_ver = latest['tag_name'].replace('v', '')
    is_armhf = info['arch'].startswith('arm')
    is_aarch = info['arch'].startswith('aarch')

    local = version_to_tuple(info['current'])
    remote = version_to_tuple(latest_ver)
    if remote > local:
        if not native:
            info['url'] = "https://github.com/%s/archive/%s.zip" % (repo, latest['tag_name'])
        else:
            if is_armhf:
                # check if this release is compatible with armhf
                for asset in latest['assets']:
                    download_url = asset['browser_download_url']
                    if (download_url.endswith('.zip') and
                            (info['arch'] in download_url or (is_armhf and 'armhf' in download_url))):
                        info['url'] = download_url
                        break
            elif is_aarch:
                # check if this release is compatible with arm64/aarch64
                for asset in latest['assets']:
                    download_url = asset['browser_download_url']
                    if (download_url.endswith('.zip') and
                            (info['arch'] in download_url or (is_aarch and 'aarch' in download_url))):
                        info['url'] = download_url
                        break

    return info


def make_path_for(name):
    path = os.path.join("/opt/", name)
    if os.path.exists(path):
        logging.debug("[update] deleting %s" % path)
        shutil.rmtree(path, ignore_errors=True, onerror=None)
    os.makedirs(path)
    return path


def download_and_unzip(name, path, display, update):
    target = "%s_%s.zip" % (name, update['available'])
    target_path = os.path.join(path, target)

    logging.info("[update] downloading %s to %s ..." % (update['url'], target_path))
    display.update(force=True, new_data={'status': 'Downloading %s %s ...' % (name, update['available'])})

    subprocess.run(["wget", "-q", update['url'], "-O", target_path], check=True)

    logging.info("[update] extracting %s to %s ..." % (target_path, path))
    display.update(force=True, new_data={'status': 'Extracting %s %s ...' % (name, update['available'])})

    subprocess.run(["unzip", target_path, "-d", path], check=True)


def verify(name, path, source_path, display, update):
    display.update(force=True, new_data={'status': 'Verifying %s %s ...' % (name, update['available'])})

    checksums = glob.glob("%s/*.sha256" % path)
    if len(checksums) == 0:
        if update['native']:
            logging.warning("[update] native update without SHA256 checksum file")
            return False

    else:
        checksum = checksums[0]

        logging.info("[update] verifying %s for %s ..." % (checksum, source_path))

        with open(checksum, 'rt') as fp:
            expected = fp.read().split('=')[1].strip().lower()

        real = subprocess.getoutput('sha256sum "%s"' % source_path).split(' ')[0].strip().lower()

        if real != expected:
            logging.warning("[update] checksum mismatch for %s: expected=%s got=%s" % (source_path, expected, real))
            return False

    return True


def install(display, update):

    name = update['repo'].split('/')[1]

    path = make_path_for(name)

    download_and_unzip(name, path, display, update)

    source_path = os.path.join(path, name)
    if not verify(name, path, source_path, display, update):
        return False

    logging.info("[update] installing %s ..." % name)
    display.update(force=True, new_data={'status': 'Installing %s %s ...' % (name, update['available'])})

    if update['native']:
        dest_path = subprocess.getoutput("which %s" % name)
        if dest_path == "":
            logging.warning("[update] can't find path for %s" % name)
            return False

        logging.info("[update] stopping %s ..." % update['service'])
        subprocess.run(["service", update['service'], "stop"], check=True)
        shutil.move(source_path, dest_path)
        os.chmod("/usr/local/bin/%s" % name, 0o755)
        logging.info("[update] restarting %s ..." % update['service'])
        subprocess.run(["service", update['service'], "start"], check=True)
    else:
        if not os.path.exists(source_path):
            source_path = "%s-%s" % (source_path, update['available'])

        try:
            # Activate the virtual environment and install the package
            subprocess.run(["bash", "-c", f"source /opt/.pwn/bin/activate && pip install {source_path}"], check=True)

            # The pip install above only reaches the venv, so scripts/units living outside
            # it (e.g. /usr/bin/pwnlib) need to be synced separately from the same archive
            # before it gets cleaned up.
            try:
                sync_system_files(source_path)
            except Exception:
                logging.exception("[update] failed to sync system files")

            # Clean up the source directory
            shutil.rmtree(source_path, ignore_errors=True)

        except subprocess.CalledProcessError as e:
            logging.error(f"Installation failed: {e}")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
    return True


def parse_version(cmd):
    out = subprocess.getoutput(cmd)
    for part in out.split(' '):
        part = part.replace('v', '').strip()
        if re.search(r'^\d+\.\d+\.\d+.*$', part):
            return part
    raise Exception('could not parse version from "%s": output=\n%s' % (cmd, out))


class AutoUpdate(plugins.Plugin):
    __author__ = 'evilsocket@gmail.com'
    __version__ = '1.1.1'
    __name__ = 'auto-update'
    __license__ = 'GPL3'
    __description__ = 'This plugin checks when updates are available and applies them when internet is available.'

    def __init__(self):
        self.ready = False
        self.status = StatusFile('/root/.auto-update')
        self.lock = Lock()
        self.options = dict()

    def on_loaded(self):
        if 'interval' not in self.options or ('interval' in self.options and not self.options['interval']):
            logging.error("[update] main.plugins.auto-update.interval is not set")
            return
        self.ready = True
        logging.info("[update] plugin loaded.")

    def on_internet_available(self, agent):
        if self.lock.locked():
            return

        with self.lock:
            logging.debug("[update] internet connectivity is available (ready %s)" % self.ready)

            if not self.ready:
                return

            if self.status.newer_then_hours(self.options['interval']):
                logging.debug("[update] last check happened less than %d hours ago" % self.options['interval'])
                return

            logging.info("[update] checking for updates ...")

            display = agent.view()
            prev_status = display.get('status')

            try:
                display.update(force=True, new_data={'status': 'Checking for updates ...'})

                to_install = []
                to_check = [
                    ('jayofelony/bettercap', parse_version('bettercap -version'), True, 'bettercap'),
                    ('jayofelony/pwngrid', parse_version('pwngrid -version'), True, 'pwngrid-peer'),
                ]

                for repo, local_version, is_native, svc_name in to_check:
                    info = check(local_version, repo, is_native, self.options['token'])
                    if info['url'] is not None:

                        logging.warning(
                            "update for %s available (local version is '%s'): %s" % (
                                repo, info['current'], info['url']))
                        info['service'] = svc_name
                        to_install.append(info)

                num_updates = len(to_install)
                num_installed = 0

                if num_updates > 0:
                    if self.options['install']:
                        for update in to_install:
                            plugins.on('updating')
                            if install(display, update):
                                num_installed += 1
                    else:
                        prev_status = '%d new update%s available!' % (num_updates, 's' if num_updates > 1 else '')

                logging.info("[update] done")

                self.status.update()

                if num_installed > 0:
                    display.update(force=True, new_data={'status': 'Rebooting ...'})
                    time.sleep(3)
                    pwnagotchi.reboot()

            except Exception as e:
                logging.error("[update] %s" % e)

            display.update(force=True, new_data={'status': prev_status if prev_status is not None else ''})
