import logging
import os
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
from pwnagotchi.ui.web.gridview import GridView

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


# One-shot background catalog sync. On a fresh install the available-plugins dir is
# empty and there's nothing to browse; the moment internet is back we pull the catalog
# once so the store fills itself without the user having to hit Refresh.
_sync_lock = threading.Lock()
_sync_running = {"v": False}


def _auto_sync_worker(config):
    from pwnagotchi.plugins import actions
    try:
        r = actions.refresh(config)
        logging.info("plugin store auto-sync: %s", r.message)
    except Exception as ex:
        logging.warning("plugin store auto-sync failed: %s", ex)
    finally:
        with _sync_lock:
            _sync_running["v"] = False


def _maybe_auto_sync(config):
    """Kick a background catalog sync iff the catalog is empty (fresh install) and
    none is already running. Returns True when a sync is running/queued."""
    from pwnagotchi.plugins import cmd as _pcmd
    with _sync_lock:
        if _sync_running["v"]:
            return True
        try:
            has_catalog = bool(_pcmd._get_available())
        except Exception:
            has_catalog = True  # can't tell -> don't spam a sync
        if has_catalog:
            return False  # already synced; manual Refresh handles later updates
        _sync_running["v"] = True
    threading.Thread(target=_auto_sync_worker, args=(config,), daemon=True).start()
    return True


class Handler:
    def __init__(self, config, agent, app):
        self._config = config
        self._agent = agent
        self._app = app
        self._grid_view = GridView()

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

    # Render a chrome-only shell on a normal GET; the page fetches the (slow)
    # pwngrid data as an XHR fragment (loadFragment) so tab switches stay instant.
    def inbox(self):
        page = request.args.get("p", default=1, type=int)
        if self._is_fragment():
            inbox, error = self._grid_view.inbox(page)
            return render_template("inbox.html", name=pwnagotchi.name(), page=page,
                                   error=error, inbox=inbox, is_fragment=True)
        return render_template("inbox.html", name=pwnagotchi.name(), page=page, is_fragment=False)

    def inbox_profile(self):
        if self._is_fragment():
            data, error = self._grid_view.profile()
            return render_template("profile.html", name=pwnagotchi.name(),
                                   fingerprint=self._agent.fingerprint(),
                                   data=json.dumps(data, indent=2), error=error, is_fragment=True)
        return render_template("profile.html", name=pwnagotchi.name(),
                               fingerprint=self._agent.fingerprint(), is_fragment=False)

    def inbox_peers(self):
        if self._is_fragment():
            peers, error = self._grid_view.peers()
            return render_template("peers.html", name=pwnagotchi.name(), peers=peers,
                                   error=error, is_fragment=True)
        return render_template("peers.html", name=pwnagotchi.name(), is_fragment=False)

    def show_message(self, id):
        if self._is_fragment():
            message, error = self._grid_view.message(id)
            return render_template("message.html", name=pwnagotchi.name(),
                                   error=error, message=message, is_fragment=True)
        return render_template("message.html", name=pwnagotchi.name(), id=id, is_fragment=False)

    def new_message(self):
        to = request.args.get("to", default="")
        return render_template("new_message.html", to=to)

    def send_message(self):
        to = request.form["to"]
        message = request.form["message"]
        _, error = self._grid_view.send(to, message)
        return jsonify({"error": error})

    def mark_message(self, id, mark):
        if not grid.is_connected():
            abort(200)

        logging.info("marking message %d as %s" % (int(id), mark))
        grid.mark_message(id, mark)
        return redirect("/inbox")

    def plugins(self, name, subpath):
        if name is None:
            # Assembly lives in the shared PluginCatalog; hand it the daemon's
            # registered/loaded state + the store metadata (network kept web-side).
            from pwnagotchi.plugins.catalog import PluginCatalog
            from pwnagotchi.plugins import cmd as _pcmd

            cfg = self._agent.config()

            # Store needs internet to sync; when offline we disable it (and skip the
            # store-metadata fetch, which would otherwise hang on its timeout).
            store_online = _pcmd._check_internet()
            store_syncing = _maybe_auto_sync(cfg) if store_online else False

            catalog = PluginCatalog.from_environment(
                cfg,
                installed_paths=_pcmd._get_installed(cfg),   # on-disk: install/uninstall show at once
                loaded=plugins.loaded,
                store_meta=_store_meta() if store_online else {},
                registered_names=set(plugins.database.keys()),  # startup set: drives the restart banner
            )

            # Restart-to-apply buttons should keep the unit in its current mode
            # (the handler's restart() only accepts the uppercase "AUTO"/"MANU").
            current_mode = "MANU" if self._agent.mode == "manual" else "AUTO"
            return render_template("plugins.html", cards=catalog.entries,
                                   restart_pending=catalog.restart_pending,
                                   current_mode=current_mode,
                                   store_online=store_online, store_syncing=store_syncing)

        if name == "toggle" and request.method == "POST":
            checked = True if "enabled" in request.form else False
            plugin_name = request.form["plugin"]
            ok = bool(plugins.toggle_plugin(plugin_name, checked))
            if self._wants_json():
                verb = "Enabled" if checked else "Disabled"
                return jsonify({
                    "ok": ok,
                    "message": (f"{verb} {plugin_name}" if ok
                                else f"Failed to {'enable' if checked else 'disable'} {plugin_name}"),
                })
            return "success" if ok else "failed"

        # Actions run in-process via the shared plugins.actions interface.
        if name in ("upgrade", "install", "uninstall", "refresh") and request.method == "POST":
            from pwnagotchi.plugins import actions
            cfg = self._agent.config()

            if name == "refresh":
                r = actions.refresh(cfg)
                logging.info("plugin catalog refresh: %s", r.message)
            elif name == "install":
                plugin_name = request.form["plugin"]
                r = actions.install(plugin_name, cfg)
                logging.info("plugin install %s: %s", plugin_name, r.message)
            elif name == "uninstall":
                plugin_name = request.form["plugin"]
                r = actions.uninstall(plugin_name, cfg)
                logging.info("plugin uninstall %s: %s", plugin_name, r.message)
            else:  # upgrade: refresh the catalog first (as before), then upgrade
                plugin_name = request.form["plugin"]
                rr = actions.refresh(cfg)
                logging.info("plugin catalog refresh: %s", rr.message)
                r = actions.upgrade(plugin_name, cfg)
                logging.info("plugin upgrade %s: %s", plugin_name, r.message)

            if self._wants_json():
                return jsonify({"ok": r.ok, "message": r.message})
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

    @staticmethod
    def _wants_json():
        # AJAX calls get JSON; plain requests get the redirect/text fallback.
        return (request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in (request.headers.get("Accept") or ""))

    @staticmethod
    def _is_fragment():
        # True when loadFragment is fetching the data fragment (renders list only).
        return request.headers.get("X-Requested-With") == "XMLHttpRequest"

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
