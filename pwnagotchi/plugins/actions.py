"""Plugin actions (install/uninstall/upgrade/refresh) shared in-process by the CLI
and the web /plugins route, so the web no longer shells out to the CLI. Each
returns a Result(ok, message); refresh is the only network op.
"""
import os
import glob
import shutil
import logging
from dataclasses import dataclass

from pwnagotchi.utils import download_file, unzip, save_config, md5

DEFAULT_CONFIG_PATH = '/etc/pwnagotchi/config.toml'


@dataclass(frozen=True)
class Result:
    ok: bool
    message: str


def _cmd():
    from pwnagotchi.plugins import cmd  # lazy: cmd imports this module (circular otherwise)
    return cmd


def _copy_with_config(src, dst):
    """Copy a plugin .py and any sibling .yml/.yaml config next to it, backing up
    a locally-modified config first (shared by install and upgrade)."""
    shutil.copyfile(src, dst)
    dst_dir = os.path.dirname(dst)
    for conf in glob.glob(src.replace('.py', '.y?ml')):
        conf_dst = os.path.join(dst_dir, os.path.basename(conf))
        if os.path.exists(conf_dst) and md5(conf_dst) != md5(conf):
            logging.info('Backing up config: %s', os.path.basename(conf))
            shutil.move(conf_dst, conf_dst + '.bak')
        shutil.copyfile(conf, conf_dst)


def install(name, config, config_path=DEFAULT_CONFIG_PATH):
    """Install an available plugin into the custom-plugins dir (local copy)."""
    cmd = _cmd()
    available = cmd._get_available()
    installed = cmd._get_installed(config)

    if name not in available:
        return Result(False, f"{name} not found.")

    install_path = config['main']['custom_plugins']
    if not install_path:
        install_path = cmd.DEFAULT_INSTALL_PATH
        config['main']['custom_plugins'] = install_path
        save_config(config, config_path)

    os.makedirs(install_path, exist_ok=True)
    _copy_with_config(available[name], os.path.join(install_path, os.path.basename(available[name])))

    if name in installed:
        return Result(True, f"Reinstalled {name}.")
    return Result(True, f"Installed {name}.")


def uninstall(name, config):
    """Remove an installed plugin's file."""
    cmd = _cmd()
    installed = cmd._get_installed(config)
    if name not in installed:
        return Result(False, f"Plugin {name} is not installed.")
    os.remove(installed[name])
    return Result(True, f"Uninstalled {name}.")


def upgrade(name, config):
    """Upgrade a single installed plugin from the available catalog, if newer."""
    cmd = _cmd()
    available = cmd._get_available()
    installed = cmd._get_installed(config)

    if name not in installed:
        return Result(False, f"Plugin {name} is not installed.")
    if name not in available:
        return Result(False, f"{name} is not in the available catalog.")

    available_version = cmd._extract_version(available[name])
    installed_version = cmd._extract_version(installed[name])
    if not (installed_version and available_version) or available_version <= installed_version:
        return Result(True, f"{name} is already up to date.")

    logging.info('Upgrade %s from %s to %s', name,
                 '.'.join(installed_version), '.'.join(available_version))
    _copy_with_config(available[name], installed[name])
    return Result(True, f"Upgraded {name} to {'.'.join(available_version)}.")


def refresh(config):
    """Refresh the available-plugins catalog from the configured repos (network,
    bounded by download_file's timeout)."""
    cmd = _cmd()

    if not cmd._check_internet():
        return Result(False, "No internet / DNS. See the Connecting wiki page.")

    urls = config['main']['custom_plugin_repos']
    if not urls:
        return Result(False, "No plugin repositories configured.")

    save_dir = cmd.SAVE_DIR
    new_files = 0
    changed_files = 0
    for idx, repo_url in enumerate(urls):
        dest = os.path.join(save_dir, 'plugins%d.zip' % idx)
        logging.info('Downloading plugins from %s to %s', repo_url, dest)
        try:
            os.makedirs(save_dir, exist_ok=True)
            before = cmd._analyse_dir(save_dir)
            download_file(repo_url, dest)
            unzip(dest, save_dir, strip_dirs=1)
            after = cmd._analyse_dir(save_dir)
            new_files += max(0, len(after) - len(before))
            for filename, filehash in after.items():
                if filename in before and filehash != before[filename]:
                    changed_files += 1
        except Exception as ex:
            logging.error('Error while updating plugins: %s', ex)
            return Result(False, f"Error updating from {repo_url}: {ex}")

    return Result(True, f"Catalog refreshed ({new_files} new, {changed_files} changed).")
