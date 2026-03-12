import logging, json, os, glob, pwnagotchi
import pwnagotchi.plugins as plugins
from flask import abort, send_from_directory, render_template_string

TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "passwordsList" %}
{% block title %}
    {{ title }}
{% endblock %}
{% block meta %}
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, user-scalable=0" />
{% endblock %}
{% block styles %}
{{ super() }}
    <style>
        #searchText {
            width: 100%;
        }
        table {
            table-layout: auto;
            width: 100%;
        }
        table, th, td {
            border: 1px solid;
            border-collapse: collapse;
        }
        th, td {
            padding: 15px;
            text-align: left;
        }
        @media screen and (max-width:700px) {
            table, tr, td {
                padding:0;
                border:1px solid;
            }
            table {
                border:none;
            }
            tr:first-child, thead, th {
                display:none;
                border:none;
            }
            tr {
                float: left;
                width: 100%;
                margin-bottom: 2em;
            }
            td {
                float: left;
                width: 100%;
                padding:1em;
            }
            td::before {
                content:attr(data-label);
                word-wrap: break-word;
                color: white;
                border-right:2px solid;
                width: 20%;
                float:left;
                padding:1em;
                font-weight: bold;
                margin:-1em 1em -1em -1em;
            }
        }
    </style>
{% endblock %}
{% block script %}
    var searchInput = document.getElementById("searchText");
    searchInput.onkeyup = function() {
        var filter, table, tr, td, i, txtValue;
        filter = searchInput.value.toUpperCase();
        table = document.getElementById("tableOptions");
        if (table) {
            tr = table.getElementsByTagName("tr");

            for (i = 0; i < tr.length; i++) {
                td = tr[i].getElementsByTagName("td")[0];
                if (td) {
                    txtValue = td.textContent || td.innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {
                        tr[i].style.display = "";
                    }else{
                        tr[i].style.display = "none";
                    }
                }
            }
        }
    }
{% endblock %}
{% block content %}
    <input type="text" id="searchText" placeholder="Search for ..." title="Type in a filter">
    <table id="tableOptions">
        <tr>
            <th>SSID</th>
            <th>BSSID</th>
            <th>Password</th>
        </tr>
        {% for p in passwords %}
            <tr>
                <td data-label="SSID">{{p["ssid"]}}</td>
                <td data-label="BSSID">{{p["bssid"]}}</td>
                <td data-label="Password">{{p["password"]}}</td>
            </tr>
        {% endfor %}
    </table>
{% endblock %}
"""

class WpaSecList(plugins.Plugin):
    __author__ = 'edited by neonlightning'
    __version__ = '1.0.2'
    __license__ = 'GPL3'
    __description__ = 'List cracked passwords from wpa-sec'

    def __init__(self):
        self.ready = False

    def on_loaded(self):
        logging.info("[wpa-sec-list] plugin loaded")

    def on_config_changed(self, config):
        self.config = config
        self.ready = True

    def on_webhook(self, path, request):
        if not self.ready:
            return "Plugin not ready"
        if path == "/" or not path:
            try:
                handshakes_dir = self.config.get('bettercap', {}).get('handshakes', '/root/handshakes')
                potfile = os.path.join(handshakes_dir, "wpa-sec.cracked.potfile")
                if not os.path.exists(potfile):
                    return render_template_string(TEMPLATE,
                                            title="Passwords list",
                                            passwords=[])
                passwords = []
                with open(potfile, 'r') as file_in:
                    lines = file_in.readlines()
                lines = [line.strip() for line in lines if line.strip()]
                unique_lines = set()
                for line in lines:
                    fields = line.split(":")
                    if len(fields) < 4:
                        continue
                    line_tuple = (fields[0], fields[2], fields[3])
                    unique_lines.add(line_tuple)
                for line_tuple in sorted(unique_lines, key=lambda x: x[1]):
                    password = {
                        "ssid": line_tuple[1],
                        "bssid": line_tuple[0],
                        "password": line_tuple[2]
                    }
                    passwords.append(password)
                return render_template_string(TEMPLATE,
                                        title="Passwords list",
                                        passwords=passwords)
            except Exception as e:
                logging.error("[wpa-sec-list] error while loading passwords: %s" % e)
                logging.debug(e, exc_info=True)
                return "Error loading passwords"
