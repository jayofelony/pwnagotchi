import logging
import subprocess
import re
import time
from flask import abort, render_template_string
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "bt-tether" %}
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
        /* BT-Tether Header */
        .bt-tether-header {
            margin-bottom: 2rem;
            padding: 1.5rem 0;
            border-bottom: 1px solid var(--border-color);
        }

        .bt-tether-header h2 {
            margin: 0 0 0.5rem 0;
            color: var(--accent);
            font-family: var(--font-pixel);
            font-size: 1.8rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .bt-tether-header p {
            margin: 0;
            color: var(--text-muted);
            font-size: 0.9rem;
        }

        /* Search Bar */
        #searchText {
            width: 100%;
            padding: 12px 16px;
            margin-bottom: 1.5rem;
            background-color: #1a1a1a;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-main);
            font-family: var(--font-main);
            font-size: 0.95rem;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }

        #searchText:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 15px rgba(76, 175, 80, 0.1);
            background-color: #1e1e1e;
        }

        /* Table Container */
        .table-container {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: var(--shadow-md);
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

        /* Responsive Mobile Design */
        @media screen and (max-width: 768px) {
            th, td {
                padding: 10px 12px;
                font-size: 0.85rem;
            }

            #searchText {
                font-size: 0.9rem;
                padding: 10px 14px;
            }
        }

        @media screen and (max-width: 480px) {
            .bt-tether-header h2 {
                font-size: 1.4rem;
            }

            #searchText {
                font-size: 0.85rem;
                padding: 10px 12px;
                margin-bottom: 1rem;
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
                margin-bottom: 1.5em;
                border: 1px solid var(--border-color);
                border-radius: 6px;
                background-color: var(--card-bg);
                padding: 1rem;
            }

            td {
                float: left;
                width: 100%;
                padding: 0.75em 0;
                margin-bottom: 0.5em;
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
                margin-bottom: 0.25em;
                letter-spacing: 0.5px;
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
    <div class="bt-tether-header">
        <h2>Bluetooth Tether</h2>
        <p>Configure Bluetooth tethering settings for your device</p>
    </div>

    <input type="text" id="searchText" placeholder="Search for ..." title="Type in a filter">
    <div class="table-container">
        <table id="tableOptions">
            <thead>
                <tr>
                    <th>Item</th>
                    <th>Configuration</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td data-label="bluetooth">Bluetooth</td>
                    <td>{{bluetooth|safe}}</td>
                </tr>
                <tr>
                    <td data-label="device">Device</td>
                    <td>{{device|safe}}</td>
                </tr>
                <tr>
                    <td data-label="connection">Connection</td>
                    <td>{{connection|safe}}</td>
                </tr>
            </tbody>
        </table>
    </div>
{% endblock %}
"""

# We all love crazy regex patterns
MAC_PTTRN = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
IP_PTTRN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
DNS_PTTRN = r"^\s*((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]\s*)+((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]?\s*)$"


class BTTether(plugins.Plugin):
    __author__ = "Jayofelony, modified by fmatray and wsvdmeer"
    __version__ = "1.4"
    __license__ = "GPL3"
    __description__ = "A new BT-Tether plugin"

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.phone_name = None
        self.mac = None

    @staticmethod
    def exec_cmd(cmd, args, pattern=None):
        try:
            result = subprocess.run(
                [cmd] + args, check=True, capture_output=True, text=True
            )
            if pattern:
                return result.stdout.find(pattern)
            return result
        except Exception as exp:
            logging.error(f"[BT-Tether] Error with {cmd}")
            logging.error(f"[BT-Tether] Exception : {exp}")
            raise exp

    def bluetoothctl(self, args, pattern=None):
        return self.exec_cmd("bluetoothctl", args, pattern)

    def nmcli(self, args, pattern=None):
        return self.exec_cmd("nmcli", args, pattern)

    def _get_bt_connection_name(self):
        # Get bluetooth connections that contains the phone-name
        bt_connections = [
            connection.split(":")[0].strip()
            for connection in self.nmcli(
                ["-t", "-f", "NAME,TYPE", "connection", "show"]
            ).stdout.splitlines()
            if connection.endswith(":bluetooth")
            and self.options["phone-name"] in connection
        ]

        if len(bt_connections) == 1:
            return bt_connections[0]

        if len(bt_connections) > 1:
            # Multiple matches found: check the MAC
            for bt_connection in bt_connections:
                if (
                    self.nmcli(
                        ["-f", "bluetooth.bdaddr", "connection", "show", bt_connection],
                        self.options["mac"].upper(),
                    )
                    != -1
                ):
                    return bt_connection

        # Fallback to the old logic
        logging.error(
            f"[BT-Tether] Connection not found for {self.options['phone-name']}git"
        )
        return self.options["phone-name"] + " Network"

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded.")

    def on_config_changed(self, config):
        if "phone-name" not in self.options:
            logging.error("[BT-Tether] Phone name not provided")
            return
        if not ("mac" in self.options and re.match(MAC_PTTRN, self.options["mac"])):
            logging.error("[BT-Tether] Error with mac address")
            return

        if not (
            "phone" in self.options
            and self.options["phone"].lower() in ["android", "ios"]
        ):
            logging.error("[BT-Tether] Phone type not supported")
            return
        if self.options["phone"].lower() == "android":
            address = self.options.get("ip", "192.168.44.2")
            gateway = self.options.get("gateway", "192.168.44.1")
        elif self.options["phone"].lower() == "ios":
            address = self.options.get("ip", "172.20.10.2")
            gateway = self.options.get("gateway", "172.20.10.1")
        if not re.match(IP_PTTRN, address):
            logging.error(f"[BT-Tether] IP error: {address}")
            return

        self.phone_name = self._get_bt_connection_name()
        self.mac = self.options["mac"].upper()
        dns = self.options.get("dns", "8.8.8.8 1.1.1.1")
        if not re.match(DNS_PTTRN, dns):
            if dns == "":
                logging.error(f"[BT-Tether] Empty DNS setting")
            else:
                logging.error(f"[BT-Tether] Wrong DNS setting: '{dns}'")
            return
        dns = re.sub("[\s,;]+", " ", dns).strip()  # DNS cleaning

        try:
            # Configure connection. Metric is set to 200 to prefer connection over USB
            self.nmcli(
                [
                    "connection",
                    "modify",
                    f"{self.phone_name}",
                    "connection.type",
                    "bluetooth",
                    "bluetooth.type",
                    "panu",
                    "bluetooth.bdaddr",
                    f"{self.mac}",
                    "connection.autoconnect",
                    "yes",
                    "connection.autoconnect-retries",
                    "0",
                    "ipv4.method",
                    "manual",
                    "ipv4.dns",
                    f"{dns}",
                    "ipv4.addresses",
                    f"{address}/24",
                    "ipv4.gateway",
                    f"{gateway}",
                    "ipv4.route-metric",
                    "200",
                ]
            )
            # Configure Device to autoconnect
            self.nmcli(
                ["device", "set", f"{self.mac}", "autoconnect", "yes", "managed", "yes"]
            )
            self.nmcli(["connection", "reload"])
            self.ready = True
            logging.info(f"[BT-Tether] Connection {self.phone_name} configured")
        except Exception as e:
            logging.error(f"[BT-Tether] Error while configuring: {e}")
            return
        try:
            time.sleep(5)  # Give some delay to configure before going up
            self.nmcli(["connection", "up", f"{self.phone_name}"])
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to connect to device: {e}")
            logging.error(
                f"[BT-Tether] Failed to connect to device: have you enabled bluetooth tethering on your phone?"
            )

    def on_ready(self, agent):
        try:
            logging.info(f"[BT-Tether] Disabling bettercap's BLE module")
            agent.run("ble.recon off", verbose_errors=False)
        except Exception as e:
            logging.info(f"[BT-Tether] Bettercap BLE was already off.")

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element("bluetooth")
        try:
            self.nmcli(["connection", "down", f"{self.phone_name}"])
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to disconnect from device: {e}")

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element(
                "bluetooth",
                LabeledValue(
                    color=BLACK,
                    label="BT",
                    value="-",
                    position=(ui.width() / 2 - 10, 0),
                    label_font=fonts.Bold,
                    text_font=fonts.Medium,
                ),
            )

    def on_ui_update(self, ui):
        if not self.ready:
            return
        with ui._lock:
            status = ""
            try:
                # Checking connection
                if (
                    self.nmcli(
                        [
                            "-w",
                            "0",
                            "-g",
                            "GENERAL.STATE",
                            "connection",
                            "show",
                            self.phone_name,
                        ],
                        "activated",
                    )
                    != -1
                ):
                    ui.set("bluetooth", "U")
                    return
                else:
                    ui.set("bluetooth", "D")
                    status = "BT Conn. down"

                # Checking device
                if (
                    self.nmcli(
                        ["-w", "0", "-g", "GENERAL.STATE", "device", "show", self.mac],
                        "(connected)",
                    )
                    != -1
                ):
                    ui.set("bluetooth", "C")
                    status += "\nBT dev conn."
                else:
                    ui.set("bluetooth", "-")
                    status += "\nBT dev disconn."
                ui.set("status", status)
            except Exception as e:
                logging.error(f"[BT-Tether] Error on update: {e}")

    def on_webhook(self, path, request):
        if not self.ready:
            return """<html>
                        <head><title>BT-tether: Error</title></head>
                        <body><code>Plugin not ready</code></body>
                    </html>"""
        if path == "/" or not path:
            try:
                bluetooth = self.bluetoothctl(["info", self.mac])
                bluetooth = bluetooth.stdout.replace("\n", "<br>")
            except Exception as e:
                bluetooth = "Error while checking bluetoothctl"

            try:
                device = self.nmcli(["-w", "0", "device", "show", self.mac])
                device = device.stdout.replace("\n", "<br>")
            except Exception as e:
                device = "Error while checking nmcli device"

            try:
                connection = self.nmcli(
                    ["-w", "0", "connection", "show", self.phone_name]
                )
                connection = connection.stdout.replace("\n", "<br>")
            except Exception as e:
                connection = "Error while checking nmcli connection"

            logging.debug(device)
            return render_template_string(
                TEMPLATE,
                title="BT-Tether",
                bluetooth=bluetooth,
                device=device,
                connection=connection,
            )
        abort(404)
