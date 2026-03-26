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
    /* Logtail-specific styles - plugin header */
    .logtail-header {
        margin-bottom: 2rem;
        padding: 1.5rem 0;
        border-bottom: 1px solid var(--border-color);
    }

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

    /* Autoscroll Toggle Wrapper */
    #divTop > span {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        white-space: nowrap;
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
        background-color: rgba(76, 175, 80, 0.05);
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
        }

        /* Mobile table display */
        table, tr, td {
            padding: 0;
            border: none;
        }

        table {
            border: none;
        }

        tr:first-child, thead, th {
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
    var filterVal = filter.value.toUpperCase();

    var xhr = new XMLHttpRequest();
    xhr.open("GET", "logtail/stream");
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

            if (filterVal.length > 0 && value.toUpperCase().indexOf(filterVal) == -1) {
                tr.style.display = "none";
            }

            table.appendChild(tr);
        });
        position = messages.length - 1;
    }

    var scrollingElement = (document.scrollingElement || document.body)
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

    var typingTimer;
    var doneTypingInterval = 500;

    filter.onkeyup = function() {
        clearTimeout(typingTimer);
        typingTimer = setTimeout(doneTyping, doneTypingInterval);
    }

    filter.onkeydown = function() {
        clearTimeout(typingTimer);
    }

    function doneTyping() {
        var tr, tds, td, i, txtValue;
        filterVal = filter.value.toUpperCase();
        tr = table.getElementsByTagName("tr");
        for (i = 0; i < tr.length; i++) {
            txtValue = tr[i].textContent || tr[i].innerText;
            if (filterVal.length === 0 || txtValue.toUpperCase().indexOf(filterVal) > -1) {
                tr[i].style.display = "table-row";
            } else {
                tr[i].style.display = "none";
            }
        }
    }
{% endblock %}

{% block content %}
    <div class="logtail-header">
        <h2>System Log</h2>
        <p>Real-time log viewer with filtering and auto-scroll capabilities</p>
    </div>

    <div id="divTop">
        <input type="text" id="filter" placeholder="Filter logs..." title="Type to filter log messages">
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
