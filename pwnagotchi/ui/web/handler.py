import logging
import os
import subprocess
import base64
import threading  # FIX B5: replaced _thread with threading
import secrets
import json
from functools import wraps

import flask

# https://stackoverflow.com/questions/14888799/disable-console-messages-in-flask-server
logging.getLogger("werkzeug").setLevel(logging.ERROR)
os.environ["WERKZEUG_RUN_MAIN"] = "false"

import pwnagotchi
import pwnagotchi.grid as grid
import pwnagotchi.ui.web as web
from pwnagotchi import plugins

from flask import send_file
from flask import Response
from flask import request
from flask import jsonify
from flask import abort
from flask import redirect
from flask import render_template, render_template_string


# Category + repo metadata for store/available plugins comes from the community store
# catalog (each entry has "category" and a "download_url"). Cached so /plugins doesn't
# refetch on every load, and fails soft (offline -> empty map -> falls back gracefully).
_STORE_CAT_URL = "https://raw.githubusercontent.com/wpa-2/pwnagotchi-store/main/plugins.json"
_store_cache = {"ts": 0.0, "map": {}}


def _store_meta():
    """name -> {'category': str, 'repo': url} from the community store catalog."""
    import time
    now = time.time()
    if _store_cache["map"] and now - _store_cache["ts"] < 3600:
        return _store_cache["map"]
    try:
        import requests
        import re as _re
        data = requests.get(_STORE_CAT_URL, timeout=6).json()
        m = {}
        for e in data:
            n = e.get("name")
            if not n:
                continue
            url = e.get("download_url")
            repo = None
            if url:
                mm = _re.match(r'(https?://github\.com/[^/]+/[^/]+)', url)
                repo = mm.group(1) if mm else url
            m[n] = {"category": e.get("category"), "repo": repo}
        if m:
            _store_cache["map"] = m
            _store_cache["ts"] = now
    except Exception:
        pass
    return _store_cache["map"]


class Handler:
    def __init__(self, config, agent, app):
        self._config = config
        self._agent = agent
        self._app = app

        # Dynamic theme CSS route
        self._app.add_url_rule("/css/theme.css", "dynamic_theme", self.dynamic_theme)

        self._app.add_url_rule("/", "index", self.with_auth(self.index))
        self._app.add_url_rule("/ui", "ui", self.with_auth(self.ui))

        self._app.add_url_rule(
            "/shutdown", "shutdown", self.with_auth(self.shutdown), methods=["POST"]
        )
        self._app.add_url_rule(
            "/reboot", "reboot", self.with_auth(self.reboot), methods=["POST"]
        )
        self._app.add_url_rule(
            "/restart", "restart", self.with_auth(self.restart), methods=["POST"]
        )

        # inbox
        self._app.add_url_rule("/inbox", "inbox", self.with_auth(self.inbox))
        self._app.add_url_rule(
            "/inbox/profile", "inbox_profile", self.with_auth(self.inbox_profile)
        )
        self._app.add_url_rule(
            "/inbox/peers", "inbox_peers", self.with_auth(self.inbox_peers)
        )
        self._app.add_url_rule(
            "/inbox/<id>", "show_message", self.with_auth(self.show_message)
        )
        self._app.add_url_rule(
            "/inbox/<id>/<mark>", "mark_message", self.with_auth(self.mark_message)
        )
        self._app.add_url_rule(
            "/inbox/new", "new_message", self.with_auth(self.new_message)
        )
        self._app.add_url_rule(
            "/inbox/send",
            "send_message",
            self.with_auth(self.send_message),
            methods=["POST"],
        )

        # plugins
        plugins_with_auth = self.with_auth(self.plugins)
        self._app.add_url_rule('/plugins', 'plugins', plugins_with_auth, strict_slashes=False,
                               defaults={'name': None, 'subpath': None})
        self._app.add_url_rule('/plugins/<name>', 'plugins', plugins_with_auth, strict_slashes=False,
                               methods=['GET', 'POST'], defaults={'subpath': None})
        self._app.add_url_rule('/plugins/<name>/<path:subpath>', 'plugins', plugins_with_auth, methods=['GET', 'POST'])

    def _check_creds(self, u, p):
        # trying to be timing attack safe
        return secrets.compare_digest(
            u, self._config["username"]
        ) and secrets.compare_digest(p, self._config["password"])

    def with_auth(self, f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not self._config["auth"]:
                return f(*args, **kwargs)
            else:
                auth = request.authorization
                if (
                    not auth
                    or not auth.username
                    or not auth.password
                    or not self._check_creds(auth.username, auth.password)
                ):
                    return Response(
                        "Unauthorized",
                        401,
                        {"WWW-Authenticate": 'Basic realm="Unauthorized"'},
                    )
                return f(*args, **kwargs)

        return wrapper

    def index(self):
        return render_template(
            "index.html",
            title=pwnagotchi.name(),
            other_mode="AUTO" if self._agent.mode == "manual" else "MANU",
            fingerprint=self._agent.fingerprint(),
        )

    def inbox(self):
        page = request.args.get("p", default=1, type=int)
        inbox = {"pages": 1, "records": 0, "messages": []}
        error = None

        try:
            if not grid.is_connected():
                raise Exception("not connected")

            inbox = grid.inbox(page, with_pager=True)
        except Exception as e:
            logging.exception("error while reading pwnmail inbox")
            error = str(e)

        return render_template(
            "inbox.html", name=pwnagotchi.name(), page=page, error=error, inbox=inbox
        )

    def inbox_profile(self):
        data = {}
        error = None

        try:
            data = grid.get_advertisement_data()
        except Exception as e:
            logging.exception("error while reading pwngrid data")
            error = str(e)

        return render_template(
            "profile.html",
            name=pwnagotchi.name(),
            fingerprint=self._agent.fingerprint(),
            data=json.dumps(data, indent=2),
            error=error,
        )

    def inbox_peers(self):
        peers = {}
        error = None

        try:
            peers = grid.memory()
        except Exception as e:
            logging.exception("error while reading pwngrid peers")
            error = str(e)

        return render_template(
            "peers.html", name=pwnagotchi.name(), peers=peers, error=error
        )

    def show_message(self, id):
        message = {}
        error = None

        try:
            if not grid.is_connected():
                raise Exception("not connected")

            message = grid.inbox_message(id)
            if message["data"]:
                message["data"] = base64.b64decode(message["data"]).decode("utf-8")
        except Exception as e:
            logging.exception("error while reading pwnmail message %d" % int(id))
            error = str(e)

        return render_template(
            "message.html", name=pwnagotchi.name(), error=error, message=message
        )

    def new_message(self):
        to = request.args.get("to", default="")
        return render_template("new_message.html", to=to)

    def send_message(self):
        to = request.form["to"]
        message = request.form["message"]
        error = None

        try:
            if not grid.is_connected():
                raise Exception("not connected")

            grid.send_message(to, message)
        except Exception as e:
            error = str(e)

        return jsonify({"error": error})

    def mark_message(self, id, mark):
        if not grid.is_connected():
            abort(200)

        logging.info("marking message %d as %s" % (int(id), mark))
        grid.mark_message(id, mark)
        return redirect("/inbox")

    def plugins(self, name, subpath):
        if name is None:
            # Unified plugins page: installed plugins + the installable catalog (from core's
            # available-plugins dir, refreshed by `pwnagotchi plugins update`). This folds the
            # old PwnStore browse/install flow into /plugins so a separate store plugin isn't
            # needed. Each card is state-aware (installed/enabled vs available-to-install) and
            # exposes an "Open" link only when the plugin actually has a web page (on_webhook).
            from pwnagotchi.plugins import cmd as plugins_cmd

            default_path = os.path.join(os.path.dirname(os.path.realpath(plugins.__file__)), "default")
            default_plugins = {n for n, p in plugins.database.items() if p.startswith(default_path)}

            # Curated categories for the shipped default plugins (so the category filter is
            # populated without editing each plugin file). A plugin's own __category__ still
            # wins when it declares one, so community plugins can self-categorise.
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
            store = _store_meta()  # name -> {category, repo} from the community store catalog

            try:
                available = plugins_cmd._get_available()  # name -> catalog .py path
            except Exception:
                available = {}

            def _ver(v):
                return '.'.join(v) if v else None

            cards = []
            # Installed plugins (loaded = enabled).
            for plugin_name, plugin_path in plugins.database.items():
                instance = plugins.loaded.get(plugin_name)
                if instance is not None:
                    desc = getattr(instance, '__description__', None)
                    author = getattr(instance, '__author__', None)
                    version = getattr(instance, '__version__', None)
                    cat = getattr(instance, '__category__', None)
                    repo = getattr(instance, '__github__', None) or getattr(instance, '__url__', None)
                else:
                    meta = plugins.get_plugin_metadata(plugin_path) or {}
                    desc, author, version = (meta.get('__description__'),
                                             meta.get('__author__'), meta.get('__version__'))
                    cat = meta.get('__category__')
                    repo = meta.get('__github__') or meta.get('__url__')
                update_version = None
                if plugin_name in available:
                    try:
                        av = plugins_cmd._extract_version(available[plugin_name])
                        iv = plugins_cmd._extract_version(plugin_path)
                        if av and iv and av > iv:
                            update_version = _ver(av)
                    except Exception:
                        pass
                cards.append({
                    'name': plugin_name,
                    'installed': True,
                    'enabled': plugin_name in plugins.loaded,
                    'default': plugin_name in default_plugins,
                    'description': desc,
                    'author': author,
                    'version': version,
                    'has_webpage': instance is not None and hasattr(instance, 'on_webhook'),
                    'update_version': update_version,
                    # Functional category for everyone (default status is a separate axis below).
                    'category': cat or CAT_MAP.get(plugin_name) or (store.get(plugin_name) or {}).get('category') or 'Other',
                    'repo': repo or (store.get(plugin_name) or {}).get('repo'),
                })
            # Available-but-not-installed (the store catalog).
            for plugin_name, plugin_path in available.items():
                if plugin_name in plugins.database:
                    continue
                try:
                    av = plugins_cmd._extract_version(plugin_path)
                    author = plugins_cmd._extract_author(plugin_path)
                except Exception:
                    av, author = None, None
                meta = plugins.get_plugin_metadata(plugin_path) or {}
                cards.append({
                    'name': plugin_name,
                    'installed': False,
                    'enabled': False,
                    'default': False,
                    'description': meta.get('__description__'),
                    'author': author or meta.get('__author__'),
                    'version': _ver(av),
                    'has_webpage': False,
                    'update_version': None,
                    'category': meta.get('__category__') or CAT_MAP.get(plugin_name) or (store.get(plugin_name) or {}).get('category') or 'Other',
                    'repo': meta.get('__github__') or meta.get('__url__') or (store.get(plugin_name) or {}).get('repo'),
                })
            # Installed first, then available; alpha within each group.
            cards.sort(key=lambda c: (not c['installed'], c['name'].lower()))

            # A restart is required to apply plugin file changes because plugins.database /
            # plugins.loaded are snapshotted at startup. Detect this by diffing the plugins
            # actually on disk now against the startup snapshot: a name added (install), a
            # name removed (uninstall), or a changed __version__ (upgrade) all mean "pending".
            restart_pending = False
            try:
                from pwnagotchi.utils import parse_version
                installed_now = plugins_cmd._get_installed(self._agent.config())
                if set(installed_now.keys()) != set(plugins.database.keys()):
                    restart_pending = True
                else:
                    for pname, ppath in installed_now.items():
                        inst = plugins.loaded.get(pname)
                        if inst is None:
                            continue
                        disk_v = plugins_cmd._extract_version(ppath)
                        loaded_raw = getattr(inst, '__version__', None)
                        loaded_v = parse_version(loaded_raw) if loaded_raw else None
                        if disk_v and loaded_v and disk_v != loaded_v:
                            restart_pending = True
                            break
            except Exception:
                restart_pending = False

            return render_template("plugins.html", cards=cards, restart_pending=restart_pending)

        if name == "toggle" and request.method == "POST":
            checked = True if "enabled" in request.form else False
            return (
                "success"
                if plugins.toggle_plugin(request.form["plugin"], checked)
                else "failed"
            )

        if name == "upgrade" and request.method == "POST":
            plugin_name = request.form["plugin"]
            logging.info(f"Upgrading plugin: {plugin_name}")
            subprocess.run(["pwnagotchi", "plugins", "update"], check=False)
            subprocess.run(["pwnagotchi", "plugins", "upgrade", plugin_name], check=False)
            return redirect("/plugins")

        if name == "install" and request.method == "POST":
            plugin_name = request.form["plugin"]
            logging.info(f"Installing plugin: {plugin_name}")
            subprocess.run(["pwnagotchi", "plugins", "install", plugin_name], check=False)
            return redirect("/plugins")

        if name == "uninstall" and request.method == "POST":
            plugin_name = request.form["plugin"]
            logging.info(f"Uninstalling plugin: {plugin_name}")
            subprocess.run(["pwnagotchi", "plugins", "uninstall", plugin_name], check=False)
            return redirect("/plugins")

        if name == "refresh" and request.method == "POST":
            # Refresh the installable catalog (pulls custom_plugin_repos into available-plugins/).
            logging.info("Refreshing plugin catalog")
            subprocess.run(["pwnagotchi", "plugins", "update"], check=False)
            return redirect("/plugins")

        if (
            name in plugins.loaded
            and plugins.loaded[name] is not None
            and hasattr(plugins.loaded[name], "on_webhook")
        ):
            try:
                return plugins.loaded[name].on_webhook(subpath, request)
            except Exception:
                abort(500)
        else:
            abort(404)

    # serve a message and shuts down the unit
    def shutdown(self):
        try:
            return render_template(
                "status.html",
                title=pwnagotchi.name(),
                go_back_after=60,
                message="Shutting down ...",
            )
        finally:
            # FIX B5: replaced _thread.start_new_thread with threading.Thread
            threading.Thread(target=pwnagotchi.shutdown, daemon=True).start()

    # serve a message and reboot the unit
    def reboot(self):
        try:
            return render_template(
                "status.html",
                title=pwnagotchi.name(),
                go_back_after=60,
                message="Rebooting ...",
            )
        finally:
            # FIX B5: replaced _thread.start_new_thread with threading.Thread
            threading.Thread(target=pwnagotchi.reboot, daemon=True).start()

    # serve a message and restart the unit in the other mode
    def restart(self):
        mode = request.form["mode"]
        if mode not in ("AUTO", "MANU"):
            mode = "MANU"

        try:
            return render_template(
                "status.html",
                title=pwnagotchi.name(),
                go_back_after=30,
                message="Restarting in %s mode ..." % mode,
            )
        finally:
            # FIX B5: replaced _thread.start_new_thread with threading.Thread
            threading.Thread(
                target=pwnagotchi.restart, args=(mode,), daemon=True
            ).start()

    # serve dynamic CSS with accent color from config
    def dynamic_theme(self):
        """Generate CSS accent RGB variables from config [ui.web.theme] section"""
        # Get RGB values from already-loaded config, fallback to default green
        r = self._config.get("theme", {}).get("accent_r", 76)
        g = self._config.get("theme", {}).get("accent_g", 175)
        b = self._config.get("theme", {}).get("accent_b", 80)

        css = f":root {{\n  --accent: rgb({r}, {g}, {b});\n  --accent-r: {r};\n  --accent-g: {g};\n  --accent-b: {b};\n}}"
        return Response(css, mimetype="text/css")

    # serve the PNG file with the display image
    def ui(self):
        with web.frame_lock:
            return send_file(web.frame_path, mimetype="image/png")
