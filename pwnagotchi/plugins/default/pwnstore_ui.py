"""
PwnStore - Plugin Store for Pwnagotchi
Browse and install plugins directly from the web UI

Author: WPA2
Version: 3.2.6
"""

import logging
import json
import subprocess
import requests
import os
import re
import _thread
from flask import render_template_string, request, jsonify, Response

import pwnagotchi.plugins as plugins

# Try to import csrf_exempt if available
try:
    from flask_wtf.csrf import CSRFProtect
    from flask_wtf import csrf
    CSRF_AVAILABLE = True
except ImportError:
    CSRF_AVAILABLE = False


class PwnStoreUI(plugins.Plugin):
    __author__ = 'WPA2'
    __version__ = '1.2.6'
    __license__ = 'GPL3'
    __description__ = 'Plugin store with web interface for browsing and installing plugins'

    def __init__(self):
        self.ready = False
        self.store_url = "https://raw.githubusercontent.com/wpa-2/pwnagotchi-store/main/plugins.json"
        
    def on_loaded(self):
        import shutil
        if not shutil.which('pwnstore'):
            logging.warning("[pwnstore_ui] pwnstore CLI not found — install/uninstall will not work")
            self._cli_available = False
        else:
            self._cli_available = True
        logging.info("[pwnstore_ui] Plugin loaded (cli_available=%s)", self._cli_available)
        self.ready = True

    def on_webhook(self, path, request):
        """Handle web requests to /plugins/pwnstore_ui/"""
        if path == "/" or path == "" or not path:
            html = self._render_store()
            return Response(html, mimetype='text/html')
        elif path == "api/plugins":
            return self._get_plugins()
        elif path == "api/install":
            return self._install_plugin(request)
        elif path == "api/uninstall":
            return self._uninstall_plugin(request)
        elif path == "api/installed":
            return self._get_installed()
        elif path == "api/configure":
            return self._configure_plugin(request)
        elif path == "api/restart":
            return self._restart_pwnagotchi()
        return Response("Not found", status=404)

    def _render_store(self):
        """Render the main store interface"""
        csrf_token = ''
        try:
            from flask_wtf.csrf import generate_csrf
            csrf_token = generate_csrf()
        except: pass
        
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="csrf-token" content="__CSRF_TOKEN__">
    <title>PwnStore - Plugin Gallery</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Courier New', monospace; background: #000; color: #0f0; padding: 10px; overflow-x: hidden; }
        .header { text-align: center; padding: 15px 10px; border-bottom: 2px solid #0f0; margin-bottom: 20px; }
        .ascii-logo { font-size: 10px; line-height: 1.2; white-space: pre; color: #0f0; margin-bottom: 10px; }
        h1 { font-size: 20px; margin: 10px 0; color: #0f0; }
        .donate-btn { display: inline-block; margin: 10px 0; padding: 8px 16px; background: #0f0; color: #000; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 12px; transition: all 0.3s; }
        .donate-btn:hover { background: #fff; transform: scale(1.05); }
        .search-bar { width: 100%; max-width: 500px; margin: 15px auto; display: block; padding: 10px; background: #111; border: 2px solid #0f0; color: #0f0; font-family: 'Courier New', monospace; font-size: 14px; }
        .filters { text-align: center; margin: 15px 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
        .filter-btn { padding: 8px 15px; background: #111; border: 2px solid #0f0; color: #0f0; cursor: pointer; font-family: 'Courier New', monospace; font-size: 12px; transition: all 0.3s; }
        .filter-btn:hover, .filter-btn.active { background: #0f0; color: #000; }
        .stats { text-align: center; margin: 15px 0; font-size: 12px; color: #0f0; }
        .plugins-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; padding: 10px; }
        @media (max-width: 600px) { .plugins-grid { grid-template-columns: 1fr; } }
        .plugin-card { background: #111; border: 2px solid #0f0; padding: 15px; transition: all 0.3s; position: relative; }
        .plugin-card:hover { border-color: #fff; box-shadow: 0 0 15px #0f0; }
        .plugin-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px; }
        .plugin-name { font-size: 16px; font-weight: bold; color: #0f0; }
        .plugin-category { font-size: 10px; padding: 3px 8px; background: #0f0; color: #000; border-radius: 3px; }
        .plugin-author { font-size: 11px; color: #0a0; margin: 5px 0; }
        .plugin-description { font-size: 12px; color: #0f0; margin: 10px 0; line-height: 1.4; }
        .plugin-actions { display: flex; gap: 8px; margin-top: 10px; }
        .btn { flex: 1; padding: 8px; border: 1px solid #0f0; background: #000; color: #0f0; cursor: pointer; font-family: 'Courier New', monospace; font-size: 11px; transition: all 0.3s; }
        .btn:hover { background: #0f0; color: #000; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-uninstall { border-color: #f00; color: #f00; }
        .btn-uninstall:hover { background: #f00; color: #000; }
        .btn-info { flex: 0 0 auto; padding: 8px 12px; }
        .status-badge { position: absolute; top: 10px; right: 10px; font-size: 10px; padding: 3px 8px; border-radius: 3px; font-weight: bold; }
        .installed { background: #0f0; color: #000; }
        .loading { text-align: center; padding: 40px; font-size: 16px; color: #0f0; }
        .message { position: fixed; top: 20px; right: 20px; padding: 15px 20px; border: 2px solid #0f0; background: #000; color: #0f0; font-size: 12px; z-index: 6000; max-width: 300px; animation: slideIn 0.3s; }
        @keyframes slideIn { from { transform: translateX(400px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        .footer { text-align: center; padding: 20px; margin-top: 30px; border-top: 2px solid #0f0; font-size: 11px; }
        
        .config-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.9); display: flex; align-items: center; justify-content: center; z-index: 8000; padding: 20px; }
        .config-modal { background: #000; border: 3px solid #0f0; padding: 25px; max-width: 500px; width: 100%; max-height: 90vh; overflow-y: auto; box-shadow: 0 0 30px #0f0; }
        .config-header h2 { font-size: 20px; color: #0f0; margin-bottom: 10px; text-align: center; }
        .config-header p { font-size: 13px; color: #0a0; text-align: center; margin-bottom: 20px; }
        .config-field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 15px; }
        .config-field label { color: #0f0; font-size: 13px; font-weight: bold; }
        .config-field input { padding: 10px; background: #111; border: 2px solid #0f0; color: #0f0; font-family: 'Courier New', monospace; }
        .config-btn { padding: 12px; border: 2px solid #0f0; background: #000; color: #0f0; cursor: pointer; font-family: 'Courier New', monospace; width: 100%; margin-top: 10px; }
        .config-btn:hover { background: #0f0; color: #000; }
        .config-btn-secondary { border-color: #555; color: #888; }
        .repo-link { display: block; text-align: center; color: #0f0; font-size: 12px; text-decoration: underline; margin-top: 20px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="header">
        <div class="ascii-logo">(◕‿‿◕)</div>
        <h1>🛒 PwnStore</h1>
        <p style="font-size: 12px;">Plugin Gallery & Manager</p>
        <div style="display: flex; justify-content: center; gap: 10px;">
            <a href="https://buymeacoffee.com/wpa2" target="_blank" class="donate-btn">☕ Support Dev</a>
            <button class="donate-btn" style="background: #f00;" onclick="restartService()">🔄 Restart Service</button>
        </div>
    </div>

    <input type="text" id="searchBox" class="search-bar" placeholder="🔍 Search plugins...">

    <div class="filters">
        <button class="filter-btn active" data-category="all">All</button>
        <button class="filter-btn" data-category="Display">Display</button>
        <button class="filter-btn" data-category="GPS">GPS</button>
        <button class="filter-btn" data-category="Attack">Attack</button>
        <button class="filter-btn" data-category="System">System</button>
    </div>

    <div class="stats"><span id="pluginCount">Loading plugins...</span></div>
    <div id="pluginsContainer" class="plugins-grid"></div>

    <div class="footer">Built by <strong>WPA2</strong> • v3.2.6 • <a href="https://github.com/wpa-2/pwnagotchi-store" style="color: #0f0;">GitHub</a></div>

    <script>
        let allPlugins = [];
        let installedPlugins = [];
        let currentCategory = 'all';
        let searchTerm = '';

        function getCSRFToken() {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        }

        async function apiRequest(url, options = {}) {
            const headers = { 'Content-Type': 'application/json', ...options.headers };
            if (options.method === 'POST') {
                const token = getCSRFToken();
                if (token) headers['X-CSRFToken'] = token;
            }
            const response = await fetch(url, { ...options, headers });
            return await response.json();
        }

        async function restartService() {
            if (!confirm('Restart Pwnagotchi service to apply all changes?')) return;
            showMessage('Restarting service... please wait.', 'success');
            await apiRequest('/plugins/pwnstore_ui/api/restart', { method: 'POST' });
            setTimeout(() => { location.reload(); }, 5000);
        }

        async function loadData() {
            try {
                allPlugins = await apiRequest('/plugins/pwnstore_ui/api/plugins');
                installedPlugins = await apiRequest('/plugins/pwnstore_ui/api/installed');
                renderPlugins();
            } catch (e) { showMessage('Load failed', 'error'); }
        }

        function renderPlugins() {
            const container = document.getElementById('pluginsContainer');
            let filtered = allPlugins.filter(p => {
                const cat = currentCategory === 'all' || p.category === currentCategory;
                const search = !searchTerm || p.name.toLowerCase().includes(searchTerm) || p.description.toLowerCase().includes(searchTerm);
                return cat && search;
            });
            document.getElementById('pluginCount').textContent = `Showing ${filtered.length} plugins`;
            container.innerHTML = filtered.map(p => {
                const isInst = installedPlugins.includes(p.name);
                return `
                    <div class="plugin-card" data-name="${p.name}">
                        ${isInst ? '<span class="status-badge installed">✓ INSTALLED</span>' : ''}
                        <div class="plugin-header"><div class="plugin-name">${p.name}</div></div>
                        <div class="plugin-author">by ${p.author}</div>
                        <div class="plugin-description">${p.description || ''}</div>
                        <div class="plugin-actions">
                            ${isInst ? 
                                `<button class="btn btn-uninstall" onclick="uninstallPlugin('${p.name}')">Uninstall</button>` :
                                `<button class="btn" onclick="installPlugin('${p.name}')">Install</button>`
                            }
                            <button class="btn btn-info" onclick="showInfo('${p.name}')">ℹ️</button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function installPlugin(name) {
            showMessage(`Installing ${name}...`, 'success');
            const res = await apiRequest('/plugins/pwnstore_ui/api/install', { method: 'POST', body: JSON.stringify({ plugin: name }) });
            if (res.success) {
                if (!installedPlugins.includes(name)) installedPlugins.push(name);
                renderPlugins();
                if (res.repo_url) {
                    showConfigModal(name, res.repo_url);
                } else {
                    showMessage(`${name} installed! Restart Pwnagotchi to activate.`, 'success');
                }
            } else { showMessage('Install failed', 'error'); }
        }

        async function uninstallPlugin(name) {
            if (!confirm(`Remove ${name}?`)) return;
            const res = await apiRequest('/plugins/pwnstore_ui/api/uninstall', { method: 'POST', body: JSON.stringify({ plugin: name }) });
            if (res.success) {
                installedPlugins = installedPlugins.filter(p => p !== name);
                renderPlugins();
                showMessage('Removed', 'success');
            }
        }

        function showConfigModal(name, repoUrl) {
            const overlay = document.createElement('div');
            overlay.className = 'config-overlay'; overlay.id = 'configOverlay';
            overlay.innerHTML = `
                <div class="config-modal">
                    <div class="config-header">
                        <h2>⚙️ ${name} installed!</h2>
                        <p>Configuration may be required</p>
                    </div>
                    <div style="margin: 20px 0; text-align: center;">
                        <p style="margin-bottom: 15px;">Edit <code>/etc/pwnagotchi/config.toml</code> to configure this plugin.</p>
                        ${repoUrl ? `<a href="${repoUrl}" target="_blank" class="config-btn" style="display: inline-block; text-decoration: none;">📖 View Setup Instructions</a>` : ''}
                        <button type="button" class="config-btn config-btn-secondary" onclick="document.getElementById('configOverlay').remove()">Close</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }

        function showInfo(name) {
            const p = allPlugins.find(x => x.name === name);
            alert(`Plugin: ${p.name}\\nAuthor: ${p.author}\\n\\n${p.description}`);
        }

        function showMessage(text, type) {
            const m = document.createElement('div');
            m.className = `message ${type}`;
            m.textContent = text;
            document.body.appendChild(m);
            setTimeout(() => m.remove(), 4000);
        }

        document.getElementById('searchBox').oninput = (e) => { searchTerm = e.target.value.toLowerCase(); renderPlugins(); };
        document.querySelectorAll('.filter-btn').forEach(b => {
            b.onclick = () => {
                document.querySelectorAll('.filter-btn').forEach(x => x.classList.remove('active'));
                b.classList.add('active');
                currentCategory = b.dataset.category;
                renderPlugins();
            };
        });
        loadData();
    </script>
</body>
</html>
        """
        return html.replace('__CSRF_TOKEN__', csrf_token)

    def _restart_pwnagotchi(self):
        """Triggers a service restart in a separate thread"""
        def run_restart():
            import time
            time.sleep(1)
            subprocess.run(['systemctl', 'restart', 'pwnagotchi'])
        
        _thread.start_new_thread(run_restart, ())
        return Response(json.dumps({'success': True}), mimetype='application/json')

    def _configure_plugin(self, request):
        try:
            data = request.get_json(force=True)
            name, vals = data.get('plugin'), data.get('config', {})
            config_file = "/etc/pwnagotchi/config.toml"
            with open(config_file, 'r') as f: lines = f.readlines()
            prefix = f"main.plugins.{name}."
            new_lines = [l for l in lines if not l.strip().startswith(prefix)]
            if new_lines and not new_lines[-1].endswith('\n'): new_lines[-1] += '\n'
            new_lines.append(f"\n# PwnStore Configuration: {name}\n")
            new_lines.append(f"{prefix}enabled = true\n")
            for k, v in vals.items():
                if k == 'enabled': continue
                v_str = str(v).strip()
                if v_str.lower() in ['true', 'false'] or v_str.isdigit() or (v_str.startswith('[') and v_str.endswith(']')):
                    new_lines.append(f"{prefix}{k} = {v_str.lower() if v_str.lower() in ['true', 'false'] else v_str}\n")
                else:
                    new_lines.append(f'{prefix}{k} = "{v_str}"\n')
            with open(config_file, 'w') as f: f.writelines(new_lines)
            return Response(json.dumps({'success': True}), mimetype='application/json')
        except Exception as e:
            return Response(json.dumps({'success': False, 'error': str(e)}), status=500)

    def _get_plugins(self):
        try: return Response(requests.get(self.store_url, timeout=10).text, mimetype='application/json')
        except: return Response("[]", mimetype='application/json')

    def _get_installed(self):
        path = "/usr/local/share/pwnagotchi/custom-plugins"
        if not os.path.exists(path): return Response("[]", mimetype='application/json')
        files = [f.replace('.py', '') for f in os.listdir(path) if f.endswith('.py')]
        return Response(json.dumps(files), mimetype='application/json')

    def _install_plugin(self, request):
        if not getattr(self, '_cli_available', False):
            return Response(json.dumps({'success': False, 'error': 'pwnstore CLI not installed'}),
                            status=503, mimetype='application/json')
        data = request.get_json(force=True)
        name = data.get('plugin')
        result = subprocess.run(['pwnstore', 'install', name], capture_output=True, text=True)
        
        # Get repo URL
        repo_url = ''
        try:
            r = requests.get(self.store_url, timeout=10)
            plugins = r.json()
            plugin_data = next((p for p in plugins if p['name'] == name), None)
            if plugin_data:
                repo_url = plugin_data.get('download_url', '')
                if '/archive/' in repo_url:
                    repo_url = repo_url.split('/archive/')[0]
        except:
            pass
        
        return Response(json.dumps({
            'success': result.returncode == 0,
            'repo_url': repo_url
        }), mimetype='application/json')

    def _uninstall_plugin(self, request):
        if not getattr(self, '_cli_available', False):
            return Response(json.dumps({'success': False, 'error': 'pwnstore CLI not installed'}),
                            status=503, mimetype='application/json')
        data = request.get_json(force=True)
        subprocess.run(['pwnstore', 'uninstall', data.get('plugin')])
        return Response(json.dumps({'success': True}), mimetype='application/json')
