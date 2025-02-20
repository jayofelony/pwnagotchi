import logging
import subprocess
import re
import time
import os
from threading import Lock
from datetime import datetime, UTC
from enum import Enum, auto
from flask import abort, render_template_string
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK


# We all love crazy regex patterns
MAC_PTTRN = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
IP_PTTRN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
DNS_PTTRN = r"^\s*((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]\s*)+((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]?\s*)$"

KERN_ERROR_PTTRN = r"^\[(\d+\.\d+)\]\s+Bluetooth:\shci0:\s.+"


class ConfigError(Exception):
    pass


class DriverState(Enum):
    ERROR = auto()
    OK = auto()


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
    __version__ = "1.6.0"
    __license__ = "GPL3"
    __description__ = "A new BT-Tether plugin"

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.lock = Lock()
        self.last_reconnect = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        self.last_timestamp = None
        self.driver_error = False
        try:
            template_file = os.path.dirname(os.path.realpath(__file__)) + "/" + "bt-tether.html"
            with open(template_file, "r") as fb:
                self.template = fb.read()
        except Exception as error:
            logging.error(
                f"[BT-Tether] error loading template file {template_file} - error: {error}"
            )

    @staticmethod
    def exec_cmd(cmd, args, pattern=None, silent=False):
        try:
            result = subprocess.run(
                [cmd] + args, check=True, capture_output=True, text=True, timeout=10
            )
            if pattern:
                return result.stdout.find(pattern)
            return result
        except Exception as exp:
            if not silent:
                logging.debug(f"[BT-Tether] Error with {cmd}: {exp}")
                raise exp

    def bluetoothctl(self, args, pattern=None):
        return self.exec_cmd("bluetoothctl", args, pattern)

    def nmcli(self, args, pattern=None):
        return self.exec_cmd("nmcli", args, pattern)

    def rmmod(self, module):
        return self.exec_cmd("rmmod", ["-f", module], silent=True)

    def modprobe(self, module):
        return self.exec_cmd("modprobe", [module])

    def hciconfig(self, command):
        return self.exec_cmd("hciconfig", ["hci0", command])

    def systemctl(self, command, service):
        return self.exec_cmd("systemctl", [command, service])

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
        self.internet = self.options.get("internet", True)
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

        match self.check_driver():
            case DriverState.OK:
                logging.info("[BT-Tether] Drivers OK")
            case DriverState.ERROR:
                logging.info("[BT-Tether] Drivers ERROR: reloading drivers")
                self.reload_drivers()

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
            try:
                ui.remove_element("bluetooth")
            except KeyError:
                pass
        with self.lock:
            logging.info("[BT-Tether] Unloading connection")
            self.down_connection()
            self.down_device()
            self.disconnect_bluetooth()
        logging.info("[BT-Tether] plugin unloaded")

    # ---------- KERNEL DRIVER ----------
    def get_last_timestamp(self):
        result = self.exec_cmd("dmesg", ["-l", "err", "-k"]).stdout
        try:
            last_error = [l for l in result.split("\n") if l.find("Bluetooth: hci0") != -1][-1]
            return re.match(KERN_ERROR_PTTRN, last_error).groups()[0]
        except IndexError:
            return None

    def check_driver(self):
        if self.driver_error:
            return DriverState.ERROR
        last_timestamp = self.get_last_timestamp()
        if last_timestamp != self.last_timestamp:
            self.last_timestamp = last_timestamp
            self.driver_error = True
            return DriverState.ERROR
        return DriverState.OK

    def reload_drivers(self):
        logging.info("[BT-Tether] Reloading kernel modules")
        logging.info("[BT-Tether] Connection down")
        self.down_connection()
        self.down_device()
        self.disconnect_bluetooth()
        logging.info("[BT-Tether] Stoping bluetooth daemon")
        self.systemctl("stop", "bluetooth")
        logging.info("[BT-Tether] Downing hci0")
        self.hciconfig("down")
        for module in ["hci_uart", "btbcm", "bnep", "bluetooth"]:
            logging.info(f"[BT-Tether] Removing {module}")
            self.rmmod(module)
        for module in ["btbcm", "hci_uart", "bnep", "bluetooth"]:
            logging.info(f"[BT-Tether] Loading {module}")
            self.modprobe(module)
        logging.info("[BT-Tether] Uping and reseting hci0")
        self.hciconfig("up")
        self.hciconfig("reset")
        logging.info("[BT-Tether] Starting bluetooth daemon")
        self.systemctl("start", "bluetooth")
        logging.info("[BT-Tether] Restarting NetworkManager daemon")
        self.systemctl("restart", "NetworkManager")
        logging.info("[BT-Tether] Bluetooth agent on")
        self.bluetoothctl(["agent", "on"])
        self.driver_error = False

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
            self.bluetoothctl(["--timeout", "10", "disconnect", f"{self.mac}"])
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
                "ipv4.route-metric",
                f"{self.metric}",
            ]
            if self.internet:
                args += [
                    "ipv4.gateway",
                    f"{self.gateway}",
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

    # ---------- RECONNECT (autoconnect=False) ----------
    def reconnect(self):
        if (datetime.now(tz=UTC) - self.last_reconnect).total_seconds() < 30 or self.lock.locked():
            return
        self.last_reconnect = datetime.now(tz=UTC)
        with self.lock:
            logging.info(f"[BT-Tether] Trying to connect to {self.phone_name}")
            if self.check_driver() != DriverState.OK:
                logging.error(f"[BT-Tether] Error with bluetooth driver")
                return
            self.connect_bluetooth()
            time.sleep(2)
            if self.check_bluetooth() != BTState.CONNECTED:
                return
            self.up_device()
            if self.check_device() != DevState.UP:
                return
            time.sleep(2)
            self.up_connection()

    # ---------- UI ----------
    def on_ui_update(self, ui):
        if not self.ready:
            return
        state, con_status, dev_status, drv_status = "", "", "", ""
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

        # Checking drivers
        match self.check_driver():
            case DriverState.OK:
                pass
            case DriverState.ERROR:
                state, drv_status = "K", "Mod error"
                logging.info("[BT-Tether] Drivers ERROR: reloading drivers")
                self.reload_drivers()

        with ui._lock:
            ui.set("bluetooth", state)
            if lines := list(filter(lambda x: x, [con_status, dev_status, drv_status])):
                ui.set("status", "\n".join(lines))
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
                self.template,
                title="BT-Tether",
                bluetooth_header=bluetooth_header,
                bluetooth_config=bluetooth_config,
                device_header=device_header,
                device_config=device_config,
                connection_header=connection_header,
                connection_config=connection_config,
            )
        abort(404)
