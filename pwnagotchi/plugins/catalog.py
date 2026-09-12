"""Plugin catalog — the single source for "what plugins exist, installed vs
available, with versions, categories and update status", shared by the web
/plugins page and the `pwnagotchi plugins list` CLI.

This is the supported interface. The underscore helpers in ``plugins.cmd``
(_get_available/_get_installed/_extract_version/_extract_author) stay put and are
called from here to read the filesystem; nothing else should reach into them. The
pure builder (``_build``) takes already-gathered maps, so the merge/version/
category logic can be tested without touching disk, network or Flask.
"""
import os
from dataclasses import dataclass
from typing import Optional

from pwnagotchi.utils import parse_version


# Curated categories for the shipped default plugins (so the category filter is
# populated without editing each plugin file). A plugin's own __category__ wins;
# the community store catalog is a further fallback. Moved here from the web
# handler so the CLI and web share one category source.
CAT_MAP = {
    'bt-tether': 'Networking', 'grid': 'Networking',
    'gps': 'GPS', 'gps_listener': 'GPS', 'webgpsmap': 'GPS', 'pwndroid': 'GPS',
    'memtemp': 'Display', 'switcher': 'Display',
    'wpa-sec': 'Attack', 'pwncrack': 'Attack', 'ohcapi': 'Attack',
    'wigle': 'Data', 'session-stats': 'Data',
    'webcfg': 'System', 'logtail': 'System', 'auto_backup': 'System',
    'auto-update': 'System', 'fix_services': 'System',
    'gpio_buttons': 'Hardware',
    'pisugarx': 'Power', 'ups_lite': 'Power', 'ups_hat_c': 'Power', 'wittypi': 'Power',
}


@dataclass(frozen=True)
class PluginEntry:
    name: str
    installed: bool
    enabled: bool
    default: bool
    description: Optional[str]
    author: Optional[str]
    version: Optional[str]
    update_version: Optional[str]
    has_webpage: bool
    category: str
    repo: Optional[str]

    @property
    def status(self):
        """Short status string for the CLI table."""
        if not self.installed:
            return "available"
        return "installed (^)" if self.update_version else "installed"


def _resolve_category(raw, name, store_meta):
    return raw or CAT_MAP.get(name) or (store_meta.get(name) or {}).get('category') or 'Other'


def _resolve_repo(raw, name, store_meta):
    return raw or (store_meta.get(name) or {}).get('repo')


class PluginCatalog:
    """Catalog of plugins for a given environment.

    Build it with :meth:`from_environment`, then read ``.entries`` (a sorted
    ``list[PluginEntry]``) and ``.restart_pending`` (bool).
    """

    def __init__(self, entries, restart_pending=False):
        self.entries = entries
        self.restart_pending = restart_pending

    # ---- pure core (the test surface): no filesystem, network or Flask ----
    @staticmethod
    def _build(installed, available, loaded_names, config_enabled, store_meta, default_names):
        """Merge installed + available into one sorted list of PluginEntry.

        installed:      name -> {version, description, author, category, repo, has_webpage}
        available:      name -> {version, description, author, category, repo}
        loaded_names:   set of running plugin names, or None to derive "enabled" from config
        config_enabled: set of names enabled in config (used when loaded_names is None)
        store_meta:     name -> {'category', 'repo'} from the community store catalog
        default_names:  set of names that are shipped default plugins
        """
        store_meta = store_meta or {}
        entries = []

        for name, info in installed.items():
            iv = info.get('version')
            av = (available.get(name) or {}).get('version')
            update_version = av if (av and iv and parse_version(av) > parse_version(iv)) else None
            enabled = (name in loaded_names) if loaded_names is not None else (name in config_enabled)
            entries.append(PluginEntry(
                name=name, installed=True, enabled=enabled, default=name in default_names,
                description=info.get('description'), author=info.get('author'),
                version=iv, update_version=update_version,
                has_webpage=bool(info.get('has_webpage')),
                category=_resolve_category(info.get('category'), name, store_meta),
                repo=_resolve_repo(info.get('repo'), name, store_meta),
            ))

        for name, info in available.items():
            if name in installed:
                continue
            entries.append(PluginEntry(
                name=name, installed=False, enabled=False, default=False,
                description=info.get('description'), author=info.get('author'),
                version=info.get('version'), update_version=None, has_webpage=False,
                category=_resolve_category(info.get('category'), name, store_meta),
                repo=_resolve_repo(info.get('repo'), name, store_meta),
            ))

        # Installed first, then available; alpha within each group.
        entries.sort(key=lambda e: (not e.installed, e.name.lower()))
        return entries

    @staticmethod
    def _restart_pending(disk_names, registered_names, disk_versions, loaded_versions):
        """True when the plugins on disk differ from what's loaded (install/uninstall/
        upgrade needs a restart to apply). Pure: name sets + name->version maps in."""
        if set(disk_names) != set(registered_names):
            return True
        for name, lv in loaded_versions.items():
            dv = disk_versions.get(name)
            if dv and lv and parse_version(dv) != parse_version(lv):
                return True
        return False

    # ---- adapter: reads the world, then calls the pure core ----
    @classmethod
    def from_environment(cls, config, installed_paths=None, loaded=None, store_meta=None):
        """Build a catalog for the current environment.

        config:         the pwnagotchi config (for config-derived "enabled").
        installed_paths: name -> path of installed plugins. Defaults to
                        ``cmd._get_installed`` (disk). The web passes
                        ``plugins.database`` (the daemon's registered set).
        loaded:         name -> plugin instance (``plugins.loaded``) in the daemon,
                        or None in the CLI (where "enabled" comes from config).
        store_meta:     name -> {category, repo} from the community store. Injected
                        so no network happens here; the CLI passes None/{}.
        """
        from pwnagotchi.plugins import cmd as _cmd
        from pwnagotchi import plugins as _plugins

        try:
            available_paths = _cmd._get_available()
        except Exception:
            available_paths = {}
        if installed_paths is None:
            installed_paths = _cmd._get_installed(config)

        default_dir = os.path.join(os.path.dirname(os.path.realpath(_plugins.__file__)), "default")
        default_names = {n for n, p in installed_paths.items() if p and p.startswith(default_dir)}

        def _ver_str(path):
            try:
                v = _cmd._extract_version(path)
                return '.'.join(v) if v else None
            except Exception:
                return None

        def _meta(path):
            try:
                return _plugins.get_plugin_metadata(path) or {}
            except Exception:
                return {}

        # Installed: prefer a loaded instance's live attributes, else file metadata.
        installed = {}
        loaded_versions = {}
        for name, path in installed_paths.items():
            inst = loaded.get(name) if loaded else None
            if inst is not None:
                installed[name] = {
                    'version': _ver_str(path),
                    'description': getattr(inst, '__description__', None),
                    'author': getattr(inst, '__author__', None),
                    'category': getattr(inst, '__category__', None),
                    'repo': getattr(inst, '__github__', None) or getattr(inst, '__url__', None),
                    'has_webpage': hasattr(inst, 'on_webhook'),
                }
                lv = getattr(inst, '__version__', None)
                if lv:
                    loaded_versions[name] = lv
            else:
                m = _meta(path)
                installed[name] = {
                    'version': _ver_str(path),
                    'description': m.get('__description__'),
                    'author': m.get('__author__'),
                    'category': m.get('__category__'),
                    'repo': m.get('__github__') or m.get('__url__'),
                    'has_webpage': False,
                }

        # Available (catalog) plugins. Installed ones keep only a version, for the
        # update-available comparison; the rest carry full metadata.
        available = {}
        for name, path in available_paths.items():
            if name in installed_paths:
                available[name] = {'version': _ver_str(path)}
                continue
            m = _meta(path)
            author = None
            try:
                author = _cmd._extract_author(path)
            except Exception:
                author = None
            available[name] = {
                'version': _ver_str(path),
                'description': m.get('__description__'),
                'author': author or m.get('__author__'),
                'category': m.get('__category__'),
                'repo': m.get('__github__') or m.get('__url__'),
            }

        loaded_names = set(loaded.keys()) if loaded is not None else None
        config_enabled = _config_enabled_names(config)

        entries = cls._build(installed, available, loaded_names, config_enabled,
                             store_meta or {}, default_names)

        # Restart-pending only makes sense in the daemon (it compares disk vs the
        # startup-loaded snapshot); the CLI has no running set.
        restart_pending = False
        if loaded is not None:
            try:
                disk = _cmd._get_installed(config)
                disk_versions = {n: _ver_str(p) for n, p in disk.items()}
                restart_pending = cls._restart_pending(
                    set(disk.keys()), set(installed_paths.keys()),
                    disk_versions, loaded_versions,
                )
            except Exception:
                restart_pending = False

        return cls(entries, restart_pending=restart_pending)


def _config_enabled_names(config):
    """Names with ``[main.plugins.<name>].enabled = true`` in config."""
    out = set()
    try:
        plugins_cfg = config['main']['plugins']
    except (KeyError, TypeError):
        return out
    for name, opts in plugins_cfg.items():
        if isinstance(opts, dict) and opts.get('enabled'):
            out.add(name)
    return out
