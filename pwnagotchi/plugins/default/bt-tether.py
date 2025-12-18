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
            <th>Item</th>
            <th>Configuration</th>
        </tr>
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
    </table>
{% endblock %}
"""

# We all love crazy regex patterns
MAC_PTTRN = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
IP_PTTRN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
DNS_PTTRN = r"^\s*((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]\s*)+((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]?\s*)$"


class BTTether(plugins.Plugin):
    __author__ = "Jayofelony, modified my fmatray"
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
            result = subprocess.run([cmd] + args, check=True, capture_output=True, text=True)
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

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded.")

    def on_config_changed(self, config):
        if "phone-name" not in self.options:
            logging.error("[BT-Tether] Phone name not provided")
            return
        if not ("mac" in self.options and re.match(MAC_PTTRN, self.options["mac"])):
            logging.error("[BT-Tether] Error with mac address")
            return
        if not ("phone" in self.options and self.options["phone"].lower() in ["android", "ios"]):
            logging.error("[BT-Tether] Phone type not supported")
            return

        # Get IP configuration options
        # Supports: 'static' for static IP, 'dhcp' for DHCP
        ip_method = self.options.get("ip-method", "").lower()
        ip_address = self.options.get("ip", "")
        gateway = self.options.get("gateway", "")

        # Normalize empty strings and whitespace
        ip_address = ip_address.strip() if ip_address else ""
        gateway = gateway.strip() if gateway else ""

        # Determine IP mode based on configuration
        # Priority: explicit ip+gateway > ip-method setting > phone-type defaults
        if ip_address and gateway:
            # Case 1: Both ip and gateway explicitly provided = static mode
            use_static = True
            if ip_method == "dhcp":
                logging.warning(
                    "[BT-Tether] ip and gateway provided, ignoring ip-method='dhcp', using static IP"
                )
            logging.info(f"[BT-Tether] Using static IP: {ip_address}, gateway: {gateway}")

        elif ip_method == "dhcp" and not ip_address and not gateway:
            # Case 2: DHCP explicitly requested with no static config
            use_static = False
            logging.info("[BT-Tether] Using DHCP mode for IP configuration")

        elif ip_method == "static":
            # Case 3: Static mode explicitly requested - use defaults if ip/gateway not fully provided
            use_static = True
            if self.options["phone"].lower() == "android":
                ip_address = ip_address or "192.168.44.2"
                gateway = gateway or "192.168.44.1"
            else:  # iOS
                ip_address = ip_address or "172.20.10.2"
                gateway = gateway or "172.20.10.1"
            logging.info(f"[BT-Tether] Using static IP with defaults: {ip_address}, gateway: {gateway}")

        else:
            # Case 4: No explicit config - fall back to static IP defaults (backwards compatible)
            use_static = True
            if self.options["phone"].lower() == "android":
                ip_address = "192.168.44.2"
                gateway = "192.168.44.1"
            else:  # iOS uses consistent 172.20.10.0/28 subnet
                ip_address = "172.20.10.2"
                gateway = "172.20.10.1"
            logging.info(f"[BT-Tether] Using static IP defaults: {ip_address}, gateway: {gateway}")

        # Validate IP addresses for static mode
        if use_static:
            if not re.match(IP_PTTRN, ip_address):
                logging.error(f"[BT-Tether] Invalid IP address: {ip_address}")
                return
            if not re.match(IP_PTTRN, gateway):
                logging.error(f"[BT-Tether] Invalid gateway: {gateway}")
                return

        self.phone_name = self.options["phone-name"] + " Network"
        self.mac = self.options["mac"]

        # DNS handling - required for static mode, optional for DHCP mode
        dns = self.options.get("dns", "8.8.8.8 1.1.1.1")
        if use_static:
            if not dns or not re.match(DNS_PTTRN, dns):
                logging.error(f"[BT-Tether] DNS required for static IP mode: '{dns}'")
                return
            dns = re.sub(r"[\s,;]+", " ", dns).strip()
        elif dns:
            # DHCP mode - DNS override is optional
            if re.match(DNS_PTTRN, dns):
                dns = re.sub(r"[\s,;]+", " ", dns).strip()
            else:
                dns = ""  # Invalid/empty DNS in DHCP mode = use phone's DNS

        try:
            # Configure connection. Metric is set to 200 to prefer connection over USB
            if not use_static:
                # DHCP configuration - let NetworkManager handle IP assignment
                nmcli_args = [
                    "connection", "modify", f"{self.phone_name}",
                    "connection.type", "bluetooth",
                    "bluetooth.type", "panu",
                    "bluetooth.bdaddr", f"{self.mac}",
                    "connection.autoconnect", "yes",
                    "connection.autoconnect-retries", "0",
                    "ipv4.method", "auto",
                    "ipv4.addresses", "",  # Clear any stale static addresses
                    "ipv4.gateway", "",    # Clear any stale gateway
                    "ipv4.route-metric", "200",
                ]
                # Allow optional DNS override even in DHCP mode
                if dns:
                    nmcli_args.extend(["ipv4.dns", f"{dns}"])
                else:
                    nmcli_args.extend(["ipv4.dns", ""])  # Clear stale DNS, use DHCP-provided
                self.nmcli(nmcli_args)
                logging.info("[BT-Tether] NetworkManager configured for DHCP")
            else:
                # Static IP configuration
                self.nmcli(
                    [
                        "connection", "modify", f"{self.phone_name}",
                        "connection.type", "bluetooth",
                        "bluetooth.type", "panu",
                        "bluetooth.bdaddr", f"{self.mac}",
                        "connection.autoconnect", "yes",
                        "connection.autoconnect-retries", "0",
                        "ipv4.method", "manual",
                        "ipv4.dns", f"{dns}",
                        "ipv4.addresses", f"{ip_address}/24",
                        "ipv4.gateway", f"{gateway}",
                        "ipv4.route-metric", "200",
                    ]
                )
                logging.info(f"[BT-Tether] NetworkManager configured for static IP: {ip_address}")
            # Configure Device to autoconnect
            self.nmcli([
                "device", "set", f"{self.mac}",
                "autoconnect", "yes",
                "managed", "yes"
            ])
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
            logging.info(f"[BT-Tether] Disconnecting from {self.phone_name}")

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
                    self.nmcli(["-w", "0", "-g", "GENERAL.STATE", "connection", "show", self.phone_name],
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
                connection = self.nmcli(["-w", "0", "connection", "show", self.phone_name])
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