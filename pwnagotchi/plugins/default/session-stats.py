import os
import logging
import threading
from time import sleep
from datetime import datetime, timedelta
from pwnagotchi import plugins
from pwnagotchi.utils import StatusFile
from flask import render_template_string
from flask import jsonify

TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "plugins" %}
{% block title %}
    Session Stats
{% endblock %}

{% block styles %}
    {{ super() }}
    <style>
        /* Session Stats Header */
        .stats-header {
            margin-bottom: 2rem;
            padding: 1.5rem 0;
            border-bottom: 1px solid var(--border-color);
        }

        /* Session Selector */
        .session-selector {
            display: flex;
            gap: 1rem;
            align-items: center;
            margin-bottom: 2rem;
            background-color: var(--card-bg);
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }

        .session-selector label {
            display: inline;
            font-size: 0.9rem;
            color: var(--accent);
            font-weight: 600;
            text-transform: uppercase;
            margin: 0;
            font-family: var(--font-pixel);
        }

        #session {
            flex: 1;
            min-width: 200px;
        }

        /* Stats Container */
        .stats-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 3rem;
        }

        .stat-card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1.5rem;
            text-align: center;
            transition: all 0.3s ease;
            box-shadow: var(--shadow-md);
        }

        .stat-card:hover {
            border-color: var(--accent);
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.1);
        }

        .stat-label {
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-family: var(--font-pixel);
            font-weight: 600;
            margin-bottom: 0.5rem;
        }

        .stat-value {
            font-size: 2.2rem;
            font-weight: bold;
            color: var(--accent);
            font-family: var(--font-pixel);
            line-height: 1;
            letter-spacing: 1px;
        }

        /* Charts Container */
        .charts-section {
            margin-top: 3rem;
        }

        .charts-section h3 {
            margin: 0 0 2rem 0;
            color: var(--accent);
            font-family: var(--font-pixel);
            font-size: 1.4rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 2rem;
        }

        div.chart {
            height: 300px;
            width: 100%;
            position: relative;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: var(--shadow-md);
            transition: all 0.3s ease;
            overflow-x: auto;
            overflow-y: hidden;
        }

        div.chart:hover {
            border-color: var(--accent);
            box-shadow: 0 8px 25px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.1);
        }

        div.chart canvas {
            max-height: 250px;
            display: block;
            min-width: 100%;
        }

        .chart-hint {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-align: center;
            margin-top: 0.5rem;
            font-family: var(--font-main);
        }

        /* Responsive Design */
        @media (max-width: 768px) {
            .stats-container {
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            }

            .stat-card {
                padding: 1rem;
            }

            .stat-value {
                font-size: 1.8rem;
            }

            .stat-label {
                font-size: 0.8rem;
            }

            .charts-grid {
                grid-template-columns: 1fr;
            }

            div.chart {
                height: 250px;
            }
        }

        @media (max-width: 480px) {
            .session-selector {
                flex-direction: column;
                align-items: stretch;
            }

            .session-selector label {
                display: block;
                margin-bottom: 0.5rem;
            }

            #session {
                width: 100%;
            }

            .stats-container {
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }

            .stat-card {
                padding: 0.75rem;
            }

            .stat-value {
                font-size: 1.5rem;
            }

            .stat-label {
                font-size: 0.75rem;
            }

            .charts-grid {
                gap: 1rem;
            }

            div.chart {
                height: 200px;
                padding: 0.75rem;
            }
        }
    </style>
{% endblock %}

{% block scripts %}
    {{ super() }}
    <script src="/js/plugins/chart.min.js"></script>
{% endblock %}

{% block script %}
    const charts = {};

    async function fetchData(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`Failed to fetch ${url}:`, error);
            return { values: [], labels: [] };
        }
    }

    function getTransparentColor(color) {
        // Convert rgb() to rgba() with 0.2 opacity, or append hex opacity
        if (color.startsWith('rgb(')) {
            return color.replace('rgb(', 'rgba(').replace(')', ', 0.2)');
        }
        return color + '33'; // hex format
    }

    function createChart(elementId, title, data) {
        const container = document.getElementById(elementId);
        if (!container || !data.values || data.values.length === 0) return;

        if (charts[elementId]) charts[elementId].destroy();

        const allLabels = new Set();
        data.values.forEach(values => {
            values.forEach(([ts]) => allLabels.add(ts));
        });
        const labels = Array.from(allLabels).sort();

        const datasets = data.values.map((values, index) => {
            const color = getChartColor(index);
            const valueMap = Object.fromEntries(values);
            const chartData = labels.map(ts => valueMap[ts] ?? null);
            
            return {
                label: data.labels[index],
                data: chartData,
                borderColor: color,
                backgroundColor: getTransparentColor(color),
                borderWidth: 2,
                fill: true,
                tension: 0.1,
                pointRadius: 1,
                pointHoverRadius: 4
            };
        });

        let canvas = container.querySelector('canvas');
        if (!canvas) {
            canvas = document.createElement('canvas');
            container.appendChild(canvas);
        }

        // Calculate required width based on number of data points
        const dataPointCount = labels.length;
        const minPixelsPerPoint = 50; // minimum pixels for each data point
        const calculatedWidth = Math.max(container.clientWidth, dataPointCount * minPixelsPerPoint);
        
        // Set canvas dimensions explicitly
        canvas.width = calculatedWidth;
        canvas.height = 250;

        charts[elementId] = new Chart(canvas, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: false,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: title,
                        font: { size: 16, family: 'var(--font-pixel)', weight: 'bold' },
                        color: '#fff',
                        padding: 20
                    },
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: { 
                            color: '#fff', 
                            font: { family: 'var(--font-main)', size: 12, weight: 'bold' },
                            padding: 15,
                            boxHeight: 4
                        }
                    },
                    tooltip: {
                        backgroundColor: '#000',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: 'var(--accent)',
                        borderWidth: 1
                    }
                },
                scales: {
                    x: {
                        grid: { 
                            color: '#333',
                            display: true
                        },
                        ticks: { 
                            color: '#fff',
                            font: { family: 'var(--font-main)', size: 11, weight: 'bold' },
                            maxTicksLimit: 8
                        }
                    },
                    y: {
                        grid: { 
                            color: '#333',
                            display: true
                        },
                        ticks: { 
                            color: '#fff',
                            font: { family: 'var(--font-main)', size: 11, weight: 'bold' }
                        }
                    }
                }
            }
        });

        // Add hint text if it doesn't exist
        if (!container.querySelector('.chart-hint')) {
            const hint = document.createElement('div');
            hint.className = 'chart-hint';
            hint.textContent = 'Scroll left/right to view more data';
            container.appendChild(hint);
        }
    }

    function getChartColor(index) {
        // Get accent color from CSS root variables
        const root = document.documentElement;
        const r = getComputedStyle(root).getPropertyValue('--accent-r').trim();
        const g = getComputedStyle(root).getPropertyValue('--accent-g').trim();
        const b = getComputedStyle(root).getPropertyValue('--accent-b').trim();
        const accentColor = `rgb(${r},${g},${b})`;
        // Use accent color as first chart color, then secondary colors
        const colors = [accentColor, '#ff9800', '#2196f3', '#f44336', '#9c27b0', '#00bcd4'];
        return colors[index % colors.length];
    }

    async function updateStats() {
        const sessionSelect = document.getElementById("session");
        const session = sessionSelect?.options[sessionSelect.selectedIndex]?.text || 'Current';
        const params = session === 'Current' ? '' : '?session=' + encodeURIComponent(session);

        // Fetch summary stats
        const summary = await fetchData('/plugins/session-stats/summary' + params);
        if (summary.networks !== undefined) {
            document.getElementById('stat_networks').textContent = summary.networks;
            document.getElementById('stat_handshakes').textContent = summary.handshakes;
            document.getElementById('stat_deauths').textContent = summary.deauths;
            document.getElementById('stat_duration').textContent = summary.duration;
            document.getElementById('stat_temp').textContent = summary.temp || '0°C';
            document.getElementById('stat_mem').textContent = summary.mem || '0%';
            document.getElementById('stat_cpu').textContent = summary.cpu || '0%';
        }

        // Fetch chart data
        const chartConfigs = [
            { endpoint: 'networks', id: 'chart_networks', title: 'Networks Captured' },
            { endpoint: 'handshakes', id: 'chart_handshakes', title: 'Handshakes Captured' },
            { endpoint: 'deauths', id: 'chart_deauths', title: 'Deauthentications Sent' },
            { endpoint: 'temp', id: 'chart_temp', title: 'Temperature (°C)' },
            { endpoint: 'mem', id: 'chart_mem', title: 'Memory Usage (%)' },
            { endpoint: 'cpu', id: 'chart_cpu', title: 'CPU Load (%)' }
        ];

        for (const config of chartConfigs) {
            const data = await fetchData('/plugins/session-stats/' + config.endpoint + params);
            createChart(config.id, config.title, data);
        }
    }

    async function loadSessionFiles() {
        const data = await fetchData('/plugins/session-stats/sessions');
        const select = document.getElementById("session");
        data.files?.forEach(file => {
            const option = document.createElement("option");
            option.text = file;
            select.appendChild(option);
        });
        select.addEventListener('change', updateStats);
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadSessionFiles();
        updateStats();
        setInterval(updateStats, 30000);
    });
{% endblock %}

{% block content %}
    <div class="stats-header">
        <h2>Session Statistics</h2>
        <p>Real-time monitoring of WiFi capture metrics and system performance</p>
    </div>

    <div class="session-selector">
        <label for="session">Session:</label>
        <select id="session">
            <option selected>Current</option>
        </select>
    </div>
    
    <div class="stats-container">
        <div class="stat-card">
            <div class="stat-label">Networks Captured</div>
            <div class="stat-value" id="stat_networks">0</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Handshakes</div>
            <div class="stat-value" id="stat_handshakes">0</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Deauths Sent</div>
            <div class="stat-value" id="stat_deauths">0</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Session Duration</div>
            <div class="stat-value" id="stat_duration">0s</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Temperature</div>
            <div class="stat-value" id="stat_temp">0°C</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Memory Usage</div>
            <div class="stat-value" id="stat_mem">0%</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">CPU Load</div>
            <div class="stat-value" id="stat_cpu">0%</div>
        </div>
    </div>

    <div class="charts-section">
        <h3>Trend Charts</h3>
        <div class="charts-grid">
            <div id="chart_networks" class="chart"><canvas></canvas></div>
            <div id="chart_handshakes" class="chart"><canvas></canvas></div>
            <div id="chart_deauths" class="chart"><canvas></canvas></div>
            <div id="chart_temp" class="chart"><canvas></canvas></div>
            <div id="chart_mem" class="chart"><canvas></canvas></div>
            <div id="chart_cpu" class="chart"><canvas></canvas></div>
        </div>
    </div>
{% endblock %}
"""


class SessionStats(plugins.Plugin):
    __author__ = "33197631+dadav@users.noreply.github.com modified by wsvdmeer"
    __version__ = "0.2.0"
    __license__ = "GPL3"
    __description__ = (
        "Displays WiFi capture stats including networks, handshakes, and deauths."
    )
    DEFAULT_UPDATE_INTERVAL = 15  # RPi-friendly: 15 sec = 4 disk writes/min
    DEFAULT_SAVE_PATH = (
        "/etc/pwnagotchi/sessions/"  # Standard location for user data
    )

    def __init__(self):
        self.lock = threading.Lock()
        self.options = dict()
        self.stats = dict()
        self.initialized = False
        self.running = False
        self.agent = None
        self.realtime_thread = None

    def on_loaded(self):
        # Use default save path if not configured
        save_dir = self.options.get("save_directory", self.DEFAULT_SAVE_PATH)
        os.makedirs(save_dir, exist_ok=True)
        self.session_name = "stats_{}.json".format(
            datetime.now().strftime("%Y_%m_%d_%H_%M")
        )
        self.session = StatusFile(
            os.path.join(save_dir, self.session_name),
            data_format="json",
        )

        logging.info(f"Session-stats plugin loaded. Saving to: {save_dir}")

        # Try to load historical data from the most recent previous session
        try:
            session_files = sorted(
                [
                    f
                    for f in os.listdir(save_dir)
                    if f.startswith("stats_") and f.endswith(".json")
                ]
            )
            if len(session_files) > 1:  # More than just the current session
                last_session_file = session_files[
                    -2
                ]  # Second to last is the previous session
                last_session_path = os.path.join(save_dir, last_session_file)
                last_session = StatusFile(last_session_path, data_format="json")
                historical_data = last_session.data_field_or("data", default=dict())
                if historical_data:
                    self.stats.update(historical_data)
                    logging.info(
                        f"Loaded {len(historical_data)} historical data points from {last_session_file}"
                    )
        except Exception as e:
            logging.warning(f"Could not load historical session data: {e}")

        self.running = True
        self.realtime_thread = threading.Thread(
            target=self._realtime_loop, daemon=True, name="session-stats-realtime"
        )
        self.realtime_thread.start()
        logging.info("Session-stats realtime collection thread started.")

    def on_ready(self, agent):
        """Called when the agent is ready - store reference for realtime stats"""
        self.agent = agent
        logging.debug("Session-stats agent reference captured")

    def on_ui_setup(self, ui):
        """Get agent reference from UI when UI is set up"""
        if hasattr(ui, "_agent") and not self.agent:
            self.agent = ui._agent
            logging.debug("Session-stats agent reference captured from UI")

    def on_unload(self):
        self.running = False
        if self.realtime_thread and self.realtime_thread.is_alive():
            self.realtime_thread.join(timeout=5)
        logging.info("Session-stats plugin unloaded.")

    def _collect_stats(self):
        """Collect current stats from agent (called both from realtime loop and epochs)"""
        if not self.agent:
            return None

        try:
            networks = len(self.agent._access_points)
            handshakes = len(self.agent._handshakes)

            stats_entry = {
                "num_peers": networks,
                "num_handshakes": handshakes,
                "num_deauths": 0,  # Will be updated if on_epoch is called
                "temperature": 0,  # Will be updated from system or epoch data
                "mem_usage": 0,
                "cpu_load": 0,
            }
            return stats_entry
        except Exception as e:
            logging.warning(f"Could not collect stats: {e}")
            return None

    def _realtime_loop(self):
        """Background thread that collects stats periodically without waiting for epochs"""
        update_interval = self.options.get(
            "update_interval", self.DEFAULT_UPDATE_INTERVAL
        )
        agent_acquired = False

        while self.running:
            try:
                sleep(update_interval)

                if not self.agent:
                    if not agent_acquired:
                        logging.debug(
                            "Session-stats realtime loop: waiting for agent reference..."
                        )
                    continue

                if not agent_acquired:
                    logging.info(
                        "Session-stats realtime loop: agent acquired, starting stats collection"
                    )
                    agent_acquired = True

                with self.lock:
                    stats_entry = self._collect_stats()
                    if stats_entry:
                        # Use high-resolution timestamp
                        current_time = datetime.now()
                        timestamp = current_time.strftime("%H:%M:%S.%f")[:-3]

                        # Only update if this is new data or initialized
                        if not self.initialized:
                            self.stats[timestamp] = stats_entry
                            self.initialized = True
                            self.session.update(data={"data": self.stats})
                            logging.info(
                                f"Session-stats initialized (realtime): {stats_entry['num_peers']} networks, "
                                f"{stats_entry['num_handshakes']} handshakes"
                            )
                        else:
                            # Add to stats if data changed
                            last_stats = (
                                list(self.stats.values())[-1] if self.stats else None
                            )
                            if last_stats and (
                                stats_entry["num_peers"]
                                != last_stats.get("num_peers", 0)
                                or stats_entry["num_handshakes"]
                                != last_stats.get("num_handshakes", 0)
                            ):
                                self.stats[timestamp] = stats_entry
                                self.session.update(data={"data": self.stats})

            except Exception as e:
                logging.warning(f"Error in realtime stats loop: {e}")

    def on_epoch(self, agent, epoch, epoch_data):
        # Store agent reference if not already set
        if not self.agent:
            self.agent = agent
            logging.debug("Session-stats agent reference captured from epoch callback")
        else:
            self.agent = agent

        with self.lock:
            # Collect epoch-specific system metrics
            stats_entry = {
                "num_peers": len(agent._access_points),
                "num_handshakes": len(agent._handshakes),
                "num_deauths": epoch_data.get("num_deauths", 0),
                "temperature": epoch_data.get("temperature", 0),
                "mem_usage": epoch_data.get("mem_usage", 0),
                "cpu_load": epoch_data.get("cpu_load", 0),
            }

            # Add epoch data with high-resolution timestamp
            current_time = datetime.now()
            timestamp = current_time.strftime("%H:%M:%S.%f")[:-3]
            self.stats[timestamp] = stats_entry
            self.session.update(data={"data": self.stats})

            if not self.initialized:
                self.initialized = True
                logging.info(
                    f"Session-stats epoch update: {len(agent._access_points)} networks, "
                    f"{len(agent._handshakes)} handshakes"
                )

    def on_webhook(self, path, request):
        if not path or path == "/":
            return render_template_string(TEMPLATE)

        session_param = request.args.get("session")
        save_dir = self.options.get("save_directory", self.DEFAULT_SAVE_PATH)

        with self.lock:
            data = self.stats
            if session_param and session_param != "Current":
                file_stats = StatusFile(
                    os.path.join(save_dir, session_param),
                    data_format="json",
                )
                data = file_stats.data_field_or("data", default=dict())

        if path == "summary":
            total_networks = len(set(d.get("num_peers", 0) for d in data.values()))
            total_handshakes = sum(d.get("num_handshakes", 0) for d in data.values())
            total_deauths = sum(d.get("num_deauths", 0) for d in data.values())
            duration = len(data) if data else 0
            temp = max([d.get("temperature", 0) for d in data.values()], default=0)
            mem = max([d.get("mem_usage", 0) for d in data.values()], default=0)
            cpu = max([d.get("cpu_load", 0) for d in data.values()], default=0)

            return jsonify(
                {
                    "networks": total_networks,
                    "handshakes": total_handshakes,
                    "deauths": total_deauths,
                    "duration": f"{duration}s",
                    "temp": f"{temp:.1f}°C",
                    "mem": f"{mem:.1f}%",
                    "cpu": f"{cpu:.1f}%",
                }
            )

        elif path == "networks":
            return jsonify(self._extract_key_values(data, ["num_peers"]))
        elif path == "handshakes":
            return jsonify(self._extract_key_values(data, ["num_handshakes"]))
        elif path == "deauths":
            return jsonify(self._extract_key_values(data, ["num_deauths"]))
        elif path == "temp":
            return jsonify(self._extract_key_values(data, ["temperature"]))
        elif path == "mem":
            return jsonify(self._extract_key_values(data, ["mem_usage"]))
        elif path == "cpu":
            return jsonify(self._extract_key_values(data, ["cpu_load"]))
        elif path == "sessions":
            return jsonify({"files": os.listdir(save_dir)})

        return jsonify({"error": "Unknown path"})

    @staticmethod
    def _extract_key_values(data, subkeys):
        result = {"values": [], "labels": subkeys}
        for plot_key in subkeys:
            v = [[ts, d.get(plot_key, 0)] for ts, d in data.items()]
            result["values"].append(v)
        return result
