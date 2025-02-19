import logging
import subprocess
import re
import time
from threading import Lock
from datetime import datetime, UTC
from enum import Enum, auto
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
            <td data-label="bluetooth"><strong>Bluetooth</strong><br>{{bluetooth_header}}</td>
            <td>
                {% for item in bluetooth_config %}
                    {% if item[0] %}<strong>{{item[0]}}</strong>: {{item[1]}}<br>{% endif %}
                {% endfor %}
            </td>
        </tr>
        <tr>
            <td data-label="device"><strong>Device</strong><br>{{device_header}}</td>
            <td>
                {% for item in device_config %}
                    {% if item[0] %}<strong>{{item[0]}}</strong>: {{item[1]}}<br>{% endif %}
                {% endfor %}
            </td>
        </tr>
        <tr>
            <td data-label="connection"><strong>Connection</strong><br>{{connection_header}}</td>
            <td>
                {% for item in connection_config %}
                    {% if item[0] %}<strong>{{item[0]}}</strong>: {{item[1]}}<br>{% endif %}
                {% endfor %}
            </td>
        </tr>
    </table>
{% endblock %}
"""

# We all love crazy regex patterns
MAC_PTTRN = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
IP_PTTRN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
DNS_PTTRN = r"^\s*((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]\s*)+((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]?\s*)$"


class ConfigError(Exception):
    pass


class BTState(Enum):
    ERROR = auto()
    NOTCONFIGURED = auto()
    PAIRED = auto()
    TRUSTED = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()


class DevState(Enum):
    ERROR = auto()
    DOWN = auto()
    CONNECTING = auto()
    UP = auto()


class ConnectionState(Enum):
    ERROR = auto()
    DOWN = auto()
    ACTIVATING = auto()
    UP = auto()


class BTTether(plugins.Plugin):
    __author__ = "Jayofelony, modified my fmatray"
    __version__ = "1.5.2"
    __license__ = "GPL3"
    __description__ = "A new BT-Tether plugin"

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.lock = Lock()
        self.last_reconnect = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)

    @staticmethod
    def exec_cmd(cmd, args, pattern=None, log=True):
        try:
            result = subprocess.run([cmd] + args, check=True, capture_output=True, text=True)
            if pattern:
                return result.stdout.find(pattern)
            return result
        except Exception as exp:
            if log:
                logging.debug(f"[BT-Tether] Error with {cmd}: {exp}")
            raise exp

    def bluetoothctl(self, args, pattern=None):
        return self.exec_cmd("bluetoothctl", args, pattern)

    def nmcli(self, args, pattern=None):
        return self.exec_cmd("nmcli", args, pattern)

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded")

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
        if self.options["phone"].lower() == "android":
            self.address = self.options.get("ip", "192.168.44.2")
            self.gateway = "192.168.44.1"
        elif self.options["phone"].lower() == "ios":
            self.address = self.options.get("ip", "172.20.10.2")
            self.gateway = "172.20.10.1"
        if not re.match(IP_PTTRN, self.address):
            logging.error(f"[BT-Tether] IP error: {self.address}")
            return

        self.phone_name = self.options["phone-name"] + " Network"
        self.mac = self.options["mac"]

        self.dns = self.options.get("dns", "8.8.8.8 1.1.1.1")
        if not re.match(DNS_PTTRN, self.dns):
            if self.dns == "":
                logging.error(f"[BT-Tether] Empty DNS setting")
            else:
                logging.error(f"[BT-Tether] Wrong DNS setting: '{self.dns}'")
            return
        self.dns = re.sub("[\s,;]+", " ", self.dns).strip()  # DNS cleaning

        self.autoconnect = self.options.get("autoconnect", True)
        self.metric = self.options.get("metric", 200)

        match self.check_bluetooth():  # Checking BT pairing
            case BTState.CONNECTED | BTState.DISCONNECTED:
                pass
            case BTState.TRUSTED:
                logging.info(
                    f"[BT-Tether] BT device ({self.mac}) paired, trusted but not connected"
                )
            case BTState.PAIRED:
                logging.error(f"[BT-Tether] BT device ({self.mac}) paired but not trusted")
                return
            case BTState.NOTCONFIGURED:
                logging.error(f"[BT-Tether] BT device ({self.mac}) not configured")
                return
            case BTState.ERROR:
                logging.error(f"[BT-Tether] Error with BT device ({self.mac})")
                return
        try:
            self.connect_bluetooth()
            self.configure_connection()
            self.configure_device()
            self.reload_connection()
            self.ready = True
            logging.info(f"[BT-Tether] Plugin configured")
            time.sleep(2)
            self.up_device()
            time.sleep(2)
            self.up_connection()
        except ConfigError:
            logging.error(f"[BT-Tether] Error while configuring connection or device")

    def on_ready(self, agent):
        try:
            logging.info(f"[BT-Tether] Disabling bettercap's BLE module")
            agent.run("ble.recon off", verbose_errors=False)
        except Exception as e:
            logging.info(f"[BT-Tether] Bettercap BLE was already off")

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

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element("bluetooth")
        with self.lock:
            logging.info("[BT-Tether] Unloading connection")
            self.down_connection()
            self.down_device()
            self.disconnect_bluetooth()
        logging.info("[BT-Tether] plugin unloaded")

    # ---------- BLUETOOTH ----------
    def check_bluetooth(self):
        try:
            result = self.bluetoothctl(["--timeout", "1", "info", self.mac]).stdout
            trusted = result.find(r"Trusted: yes") != -1
            paired = result.find(r"Paired: yes") != -1

            match paired, trusted:
                case True, True:
                    if result.find(r"Connected: yes") != -1:
                        return BTState.CONNECTED
                    if result.find(r"Connected: no") != -1:
                        return BTState.DISCONNECTED
                case True, False:
                    return BTState.PAIRED
                case False, True:
                    return BTState.TRUSTED
                case False, False:
                    return BTState.NOTCONFIGURED
        except Exception as e:
            return BTState.ERROR

    def connect_bluetooth(self):
        match self.check_bluetooth():
            case BTState.CONNECTED:
                logging.info(f"[BT-Tether] Bluetooth already up")
                return
            case BTState.DISCONNECTED:
                try:
                    args = ["--timeout", "10", "connect", self.mac]
                    if self.bluetoothctl(args, "Connection successful") != -1:
                        logging.info(f"[BT-Tether] BT device({self.mac}) connected")
                    else:
                        logging.info(f"[BT-Tether] Failed to connect to BT device({self.mac})")
                        logging.info(f"[BT-Tether] Let's try later")
                except Exception as e:
                    logging.error(
                        f"[BT-Tether] Failed to up device. Is bluetooth tethering enabled on your phone?"
                    )
            case BTState.ERROR | BTState.TRUSTED | BTState.PAIRED | BTState.NOTCONFIGURED:
                logging.error(f"[BT-Tether] Error with BT device ({self.mac})")
                return

    def disconnect_bluetooth(self):
        try:
            self.bluetoothctl(["disconnect", f"{self.mac}"])
        except Exception as e:
            pass

    # ---------- DEVICE ----------
    def check_device(self):
        try:
            args = ["-w", "0", "-g", "GENERAL.STATE", "device", "show", self.mac]
            result = self.nmcli(args).stdout
            if result.find("(connected)") != -1:
                return DevState.UP
            if result.find("(connecting (prepare))") != -1:
                return DevState.CONNECTING
            if result.find("(disconnected)") != -1:
                return DevState.DOWN
            return DevState.ERROR
        except Exception as e:
            return DevState.ERROR

    def configure_device(self):
        try:
            if self.autoconnect:
                self.nmcli(["device", "set", f"{self.mac}", "autoconnect", "yes", "managed", "yes"])
            else:
                self.nmcli(["device", "set", f"{self.mac}", "autoconnect", "no", "managed", "yes"])
            logging.info(f"[BT-Tether] Device ({self.mac}) configured")
        except Exception as e:
            logging.error(f"[BT-Tether] Error while configuring device: {e}")
            raise ConfigError()

    def up_device(self):
        match self.check_device():
            case DevState.UP:
                logging.info(f"[BT-Tether] Device already up")
                return
            case DevState.CONNECTING:
                logging.info(f"[BT-Tether] Device already trying to up")
                return
            case DevState.DOWN:
                try:
                    self.nmcli(["device", "up", f"{self.mac}"])
                    logging.info(f"[BT-Tether] Device {self.mac} up")
                except Exception as e:
                    logging.error(
                        f"[BT-Tether] Failed to up device. Is bluetooth tethering enabled on your phone?"
                    )
            case DevState.ERROR:
                logging.error(f"[BT-Tether] Error with device ({self.mac})")
                return

    def down_device(self):
        try:
            self.nmcli(["device", "down", f"{self.mac}"])
        except Exception as e:
            pass

    # ---------- CONNECTION ----------
    def check_connection(self):
        try:
            args = ["-w", "0", "-g", "GENERAL.STATE", "connection", "show", self.phone_name]
            result = self.nmcli(args).stdout
            if result.find("activated") != -1:
                return ConnectionState.UP
            if result.find("activating") != -1:
                return ConnectionState.ACTIVATING
            return ConnectionState.DOWN
        except Exception as e:
            return ConnectionState.ERROR

    def configure_connection(self):
        try:
            args = [
                "connection",
                "modify",
                f"{self.phone_name}",
                "connection.type",
                "bluetooth",
                "bluetooth.type",
                "panu",
                "bluetooth.bdaddr",
                f"{self.mac}",
                "ipv4.method",
                "manual",
                "ipv4.dns",
                f"{self.dns}",
                "ipv4.addresses",
                f"{self.address}/24",
                "ipv4.gateway",
                f"{self.gateway}",
                "ipv4.route-metric",
                f"{self.metric}",
            ]
            if self.autoconnect:
                args += [
                    "connection.autoconnect",
                    "yes",
                    "connection.autoconnect-retries",
                    "0",
                ]
            else:
                args += [
                    "connection.autoconnect",
                    "no",
                ]

            self.nmcli(args)
            logging.info(f"[BT-Tether] Connection ({self.phone_name}) configured")
        except Exception as e:
            logging.error(f"[BT-Tether] Error while configuring connection: {e}")
            raise ConfigError()

    def reload_connection(self):
        try:
            self.nmcli(["connection", "reload"])
            logging.info(f"[BT-Tether] Connection reloaded")
        except Exception as e:
            logging.error(f"[BT-Tether] Error with connection reload")

    def up_connection(self):
        match self.check_connection():
            case ConnectionState.UP:
                logging.info(f"[BT-Tether] Connection already up")
                return
            case ConnectionState.ACTIVATING:
                logging.info(f"[BT-Tether] Connection already trying to up")
                return
            case ConnectionState.DOWN:
                try:
                    self.nmcli(["connection", "up", f"{self.phone_name}"])
                    logging.info(f"[BT-Tether] Connection {self.phone_name} up")
                except Exception as e:
                    logging.error(
                        f"[BT-Tether] Failed to up connection. Is bluetooth tethering enabled on your phone?"
                    )
            case ConnectionState.ERROR:
                logging.error(f"[BT-Tether] Error with connection ({self.phone_name})")

    def down_connection(self):
        try:
            self.nmcli(["connection", "down", f"{self.phone_name}"])
        except Exception as e:
            pass

    def reconnect(self):
        if (datetime.now(tz=UTC) - self.last_reconnect).total_seconds() < 30:
            return
        logging.info(f"[BT-Tether] Trying to connect to {self.phone_name}")
        self.last_reconnect = datetime.now(tz=UTC)
        with self.lock:
            self.connect_bluetooth()
            time.sleep(2)
            self.up_device()
            time.sleep(2)
            self.up_connection()

    # ---------- UI ----------
    def on_ui_update(self, ui):
        if not self.ready:
            return
        state, con_status, dev_status = "", "", ""
        # Checking connection
        match self.check_connection():
            case ConnectionState.UP:
                with ui._lock:
                    ui.set("bluetooth", "U")
                return
            case ConnectionState.ACTIVATING:
                state, con_status = "A", "Conn. activationg"
            case ConnectionState.DOWN:
                state, con_status = "-", "Conn. down"
            case ConnectionState.ERROR:
                state, con_status = "E", "Conn. error"
                logging.error(f"[BT-Tether] Error with connection ({self.phone_name})")

        # Checking device
        match self.check_device():
            case DevState.UP:
                dev_status = "Dev connected"
            case DevState.CONNECTING:
                dev_status = "Dev connecting"
            case DevState.DOWN:
                dev_status = "Dev disconnected"
            case DevState.ERROR:
                dev_status = "Dev error"
                logging.error(f"[BT-Tether] Error with device ({self.mac})")
        with ui._lock:
            ui.set("bluetooth", state)
            if any([con_status, dev_status]):
                ui.set("status", f"{con_status}\n{dev_status}")
        if not self.autoconnect:
            self.reconnect()

    # ---------- WEB ----------
    def on_webhook(self, path, request):
        if not self.ready:
            return """<html>
                        <head><title>BT-tether: Error</title></head>
                        <body><code>Plugin not ready</code></body>
                    </html>"""
        if path == "/" or not path:
            try:
                bluetooth = self.bluetoothctl(["info", self.mac]).stdout
                bluetooth_config = [
                    tuple(i.split(": ")) for i in bluetooth.replace("\t", "").split("\n")[1:]
                ]
                bluetooth_header = bluetooth.replace("\t", "").split("\n")[0]
            except Exception as e:
                bluetooth_header = "Error while checking bluetoothctl"
                bluetooth_config = []

            try:
                device = self.nmcli(["-w", "0", "device", "show", self.mac]).stdout
                device_config = [
                    tuple(i.split(": ")) for i in device.replace("\t", "").split("\n")[1:]
                ]
                device_header = device.replace("\t", "").split("\n")[0]
            except Exception as e:
                logging.error(e)
                device_header = "Error while checking nmcli device"
                device_config = []

            try:
                connection = self.nmcli(["-w", "0", "connection", "show", self.phone_name]).stdout
                connection_config = [
                    tuple(i.split(": ")) for i in connection.replace("\t", "").split("\n")[1:]
                ]
                connection_header = connection.replace("\t", "").split("\n")[0]
            except Exception as e:
                logging.error(e)
                connection_header = "Error while checking nmcli connection"
                connection_config = []

            return render_template_string(
                TEMPLATE,
                title="BT-Tether",
                bluetooth_header=bluetooth_header,
                bluetooth_config=bluetooth_config,
                device_header=device_header,
                device_config=device_config,
                connection_header=connection_header,
                connection_config=connection_config,
            )
        abort(404)
