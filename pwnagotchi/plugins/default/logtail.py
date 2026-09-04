import logging
import threading
from time import sleep
from pwnagotchi import plugins
from flask import render_template_string
from flask import abort
from flask import Response


INDEX = """
{% extends "base.html" %}
{% set active_page = "plugins" %}
{% block title %}
    Logtail
{% endblock %}

{% block styles %}
{{ super() }}
<style>
    /* Search/Control Bar */
    #divTop {
        position: -webkit-sticky;
        position: sticky;
        top: 0;
        display: flex;
        gap: 0.5rem;
        align-items: center;
        width: 100%;
        padding: 1rem;
        margin-bottom: 1.5rem;
        font-size: 0.95rem;
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        z-index: 100;
    }

    #filter {
        flex: 1;
        min-width: 200px;
    }

    #filter, #levelFilter {
        height: 44px;
        box-sizing: border-box;
        margin: 0;
    }
    #levelFilter { min-width: 150px; }

    /* Autoscroll Toggle Wrapper */
    #divTop > span {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        white-space: nowrap;
    }

    /* Separate the autoscroll toggle from the level dropdown (nudge right) */
    #divTop > span:last-child {
        margin-left: 1.5rem;
    }
    @media screen and (max-width: 768px) {
        #divTop > span:last-child { margin-left: 0; }
    }

    #autoscroll {
        width: auto;
        height: auto;
        margin: 0;
        padding: 0;
        cursor: pointer;
        accent-color: var(--accent);
    }

    label[for="autoscroll"] {
        display: inline;
        font-size: 0.85rem;
        color: var(--text-main);
        font-weight: 400;
        margin: 0;
        font-family: var(--font-main);
        cursor: pointer;
    }

    /* Floating "scroll to top" button — only shown while auto-scroll is off. */
    #scrollTopBtn {
        position: fixed;
        right: max(16px, env(safe-area-inset-right));
        bottom: calc(88px + env(safe-area-inset-bottom, 0px));
        width: 48px;
        height: 48px;
        min-width: 0;
        padding: 0;
        border-radius: 50%;
        display: none;
        align-items: center;
        justify-content: center;
        z-index: 900;
    }
    #scrollTopBtn.show { display: flex; }
    #scrollTopBtn svg { width: 22px; height: 22px; }

    /* Table Container */
    .table-container {
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        overflow: hidden;
        box-shadow: var(--shadow-md);
        margin-bottom: 2rem;
    }

    table {
        table-layout: auto;
        width: 100%;
        border-collapse: collapse;
        background-color: var(--card-bg);
    }

    thead {
        background-color: var(--card-bg);
    }

    th {
        padding: 14px 16px;
        text-align: left;
        color: var(--accent);
        font-weight: 600;
        font-family: var(--font-pixel);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 0.85rem;
        border-bottom: 2px solid var(--border-color);
    }

    td {
        padding: 12px 16px;
        text-align: left;
        border-bottom: 1px solid var(--border-color);
        color: var(--text-body);
        font-size: 0.9rem;
    }

    tbody tr:hover {
        background-color: rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.05);
        transition: background-color 0.2s ease;
    }

    tbody tr:last-child td {
        border-bottom: none;
    }

    /* Time column */
    td:nth-child(1) {
        width: 130px;
        font-family: var(--font-pixel);
        color: var(--text-muted);
        font-size: 0.85rem;
    }

    /* Level column */
    td:nth-child(2) {
        width: 80px;
        text-align: center;
        font-weight: 600;
        font-family: var(--font-pixel);
    }

    /* Message column */
    td:nth-child(3) {
        flex: 1;
        word-break: break-word;
        overflow-wrap: break-word;
        white-space: pre-wrap;
    }

    /* Log Level Coloring */
    tr.default td:nth-child(2) {
        color: var(--text-main);
    }

    tr.info td:nth-child(2) {
        color: var(--info);
    }

    tr.warning td:nth-child(2) {
        color: #ffa500;
    }

    tr.error td:nth-child(2) {
        color: var(--danger);
    }

    tr.debug td:nth-child(2) {
        color: #b39ddb;
    }

    /* Responsive Design */
    @media screen and (max-width: 768px) {
        #divTop {
            flex-direction: column;
            align-items: stretch;
        }

        #filter {
            min-width: 100%;
        }

        th, td {
            padding: 10px 12px;
            font-size: 0.85rem;
        }

        td:nth-child(1) {
            width: 100px;
        }

        td:nth-child(2) {
            width: 65px;
        }
    }

    @media screen and (max-width: 480px) {
        #divTop {
            padding: 0.75rem;
            margin-bottom: 1rem;
        }

        th, td {
            padding: 8px 10px;
            font-size: 0.8rem;
        }

        th {
            font-size: 0.75rem;
        }

        td:nth-child(1) {
            width: 75px;
        }

        td:nth-child(2) {
            width: 55px;
        }

        .table-container {
            margin-bottom: 2rem;
            border: none;
            box-shadow: none;
            border-radius: 0;
            background: transparent;
            overflow: visible;
        }

        /* Mobile table display */
        table, tr, td {
            padding: 0;
            border: none;
        }

        table {
            border: none;
        }

        thead, th {
            display: none;
            border: none;
        }

        tr {
            float: left;
            width: 100%;
            margin-bottom: 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background-color: var(--card-bg);
            padding: 0.75rem;
        }

        td {
            float: left;
            width: 100%;
            padding: 0.5rem 0;
            margin-bottom: 0.25rem;
            border: none;
        }

        td::before {
            content: attr(data-label);
            display: block;
            color: var(--accent);
            font-weight: 600;
            font-family: var(--font-pixel);
            font-size: 0.8rem;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
            letter-spacing: 0.5px;
        }
    }
</style>
{% endblock %}

{% block script %}
    var table = document.getElementById("table").querySelector("tbody");
    var filter = document.getElementById("filter");
    var levelFilter = document.getElementById("levelFilter");
    var filterVal = filter.value.toUpperCase();
    var levelVal = "";

    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/plugins/logtail/stream");
    xhr.send();
    var position = 0;
    var data;
    var time;
    var level;
    var msg;
    var colorClass;

    function handleNewData() {
        var messages = xhr.responseText.split('\\n');
        filterVal = filter.value.toUpperCase();
        messages.slice(position, -1).forEach(function(value) {

            if (value.charAt(0) != "[") {
                msg = value;
                time = "";
                level = "";
            } else {
                data = value.split("]");
                time = data.shift() + "]";
                level = data.shift() + "]";
                msg = data.join("]");

                switch(level) {
                    case " [INFO]":
                        colorClass = "info";
                        break;
                    case " [WARNING]":
                        colorClass = "warning";
                        break;
                    case " [ERROR]":
                        colorClass = "error";
                        break;
                    case " [DEBUG]":
                        colorClass = "debug";
                        break;
                    default:
                        colorClass = "default";
                        break;
                }
            }

            var tr = document.createElement("tr");
            var td1 = document.createElement("td");
            var td2 = document.createElement("td");
            var td3 = document.createElement("td");

            td1.textContent = time;
            td2.textContent = level;
            td3.textContent = msg;

            tr.appendChild(td1);
            tr.appendChild(td2);
            tr.appendChild(td3);

            tr.className = colorClass;

            var txtOk = (filterVal.length === 0 || value.toUpperCase().indexOf(filterVal) > -1);
            var lvlOk = (levelVal === "" || colorClass === levelVal);
            if (!(txtOk && lvlOk)) {
                tr.style.display = "none";
            }

            table.appendChild(tr);
        });
        position = messages.length - 1;
    }

    var scrollingElement = document.querySelector(".page-content") || document.scrollingElement || document.body;
    function scrollToBottom () {
       scrollingElement.scrollTop = scrollingElement.scrollHeight;
    }

    var timer;
    var scrollElm = document.getElementById("autoscroll");
    timer = setInterval(function() {
        handleNewData();
        if (scrollElm.checked) {
            scrollToBottom();
        }
        if (xhr.readyState == XMLHttpRequest.DONE) {
            clearInterval(timer);
        }
    }, 1000);

    // Floating "scroll to top" button: visible only when auto-scroll is off,
    // since with auto-scroll on you're always pinned to the bottom anyway.
    var scrollTopBtn = document.getElementById("scrollTopBtn");
    function updateScrollTopBtn() {
        if (scrollElm.checked) { scrollTopBtn.classList.remove("show"); }
        else { scrollTopBtn.classList.add("show"); }
    }
    scrollElm.addEventListener("change", updateScrollTopBtn);
    updateScrollTopBtn();
    scrollTopBtn.addEventListener("click", function () {
        scrollingElement.scrollTo({ top: 0, behavior: "smooth" });
    });

    var typingTimer;
    var doneTypingInterval = 300;

    // Combined filter: free-text (name/message) AND selected log level.
    function applyFilters() {
        filterVal = filter.value.toUpperCase();
        var tr = table.getElementsByTagName("tr");
        for (var i = 0; i < tr.length; i++) {
            var txtValue = (tr[i].textContent || tr[i].innerText || "").toUpperCase();
            var txtOk = (filterVal.length === 0 || txtValue.indexOf(filterVal) > -1);
            var lvlOk = (levelVal === "" || tr[i].className === levelVal);
            tr[i].style.display = (txtOk && lvlOk) ? "table-row" : "none";
        }
    }

    filter.onkeyup = function() {
        clearTimeout(typingTimer);
        typingTimer = setTimeout(applyFilters, doneTypingInterval);
    }

    filter.onkeydown = function() {
        clearTimeout(typingTimer);
    }

    levelFilter.onchange = function() {
        levelVal = this.value;
        applyFilters();
    }
{% endblock %}

{% block content %}
    <div class="plugin-page-header">
        <div class="header-nav"><a href="/plugins" class="btn ghost">← Plugins</a><span class="header-version">v0.1.0</span></div>
        <h2>System Log</h2>
        <p>Real-time log viewer with filtering and auto-scroll capabilities</p>
    </div>

    <div id="divTop">
        <input type="text" id="filter" placeholder="Filter logs..." title="Type to filter log messages" autocomplete="off">
        <span><select id="levelFilter" title="Filter by log level">
            <option value="">All levels</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
            <option value="debug">Debug</option>
        </select></span>
        <span>
            <input type="checkbox" id="autoscroll" checked>
            <label for="autoscroll">Auto-scroll</label>
        </span>
    </div>

    <div class="table-container">
        <table id="table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Level</th>
                    <th>Message</th>
                </tr>
            </thead>
            <tbody>
            </tbody>
        </table>
    </div>

    <button type="button" id="scrollTopBtn" class="btn" title="Scroll to top" aria-label="Scroll to top"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg></button>

    <div class="plugin-footer">Built by <a href="https://github.com/dadav" target="_blank" rel="noopener">dadav</a> &middot; UI by <a href="https://github.com/wsvdmeer" target="_blank" rel="noopener">wsvdmeer</a></div>
{% endblock %}
"""


class Logtail(plugins.Plugin):
    __author__ = "33197631+dadav@users.noreply.github.com"
    __version__ = "0.1.0"
    __license__ = "GPL3"
    __description__ = "This plugin tails the logfile."

    def __init__(self):
        self.lock = threading.Lock()
        self.options = dict()
        self.ready = False

    def on_config_changed(self, config):
        self.config = config
        self.ready = True

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        logging.info("Logtail plugin loaded.")

    def on_webhook(self, path, request):
        if not self.ready:
            return "Plugin not ready"

        if not path or path == "/":
            return render_template_string(INDEX)

        if path == "stream":

            def generate():
                with open(self.config["main"]["log"]["path"]) as f:
                    yield "".join(f.readlines()[-self.options.get("max-lines", 4096) :])
                    while True:
                        yield f.readline()

            return Response(generate(), mimetype="text/plain")

        abort(404)
