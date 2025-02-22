import logging
import subprocess
import re
import time
import os

from threading import Thread, Lock
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


# ---------- STATES ----------
class DriverState(Enum):
    """Kernel Module states"""

    ERROR = auto()
    OK = auto()


class BTState(Enum):
    """Bluetooth states"""

    ERROR = auto()
    NOTCONFIGURED = auto()
    PAIRED = auto()
    TRUSTED = auto()
    CONFIGURED = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()


class DeviceState(Enum):
    """NetworkMananger device states"""

    ERROR = auto()
    DOWN = auto()
    CONNECTING = auto()
    UP = auto()


class ConnectionState(Enum):
    """NetworkMananger conneciton states"""

    ERROR = auto()
    DOWN = auto()
    ACTIVATING = auto()
    UP = auto()


# ---------- COMMAND HELPERS ----------
def exec_cmd(cmd, args, pattern=None, silent=False):
    try:
        result = subprocess.run(
            [cmd] + args, check=True, capture_output=True, text=True, timeout=10
        )
        if pattern:
            return result.stdout.find(pattern)
        return result.stdout
    except Exception as exp:
        if not silent:
            logging.debug(f"[BT-Tether] Error with {cmd}: {exp}")
            raise exp


def bluetoothctl(args, pattern=None):
    return exec_cmd("bluetoothctl", args, pattern)


def nmcli(args, pattern=None):
    return exec_cmd("nmcli", args, pattern)


def rmmod(module):
    return exec_cmd("rmmod", ["-f", module], silent=True)


def modprobe(module):
    return exec_cmd("modprobe", [module])


def hciconfig(command):
    return exec_cmd("hciconfig", ["hci0", command])


def systemctl(command, service):
    return exec_cmd("systemctl", [command, service])


def dmesg():
    return exec_cmd("dmesg", ["-l", "err", "-k"])


class BTManager(Thread):
    """
    Thread for checking kernel, bluetooth, NetworkMananger device and NetworkMananger connection.
    If a kernel issue is detected, modules are reloaded properly.
    This thread tries to keep the connection up.
    """

    def __init__(self, phone_name, mac, address, gateway, dns, metric, internet, autoconnect):
        super().__init__()
        self.phone_name = phone_name
        self.mac = mac
        self.address = address
        self.gateway = gateway
        self.dns = dns
        self.metric = metric
        self.internet = internet
        self.autoconnect = autoconnect
        self.last_reconnect = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        # Assume the driver won't mess during loading
        self.last_timestamp = self.get_last_timestamp()
        self.driver_error = False
        self.ready = False
        self.running = True
        self.connection_state = None
        self.device_state = None
        self.bluetooth_state = None
        self.driver_state = None
        self.configure()

    def configure(self):
        """
        Check bluetooth pairing, configure NetworkMananger then tries to up all.
        """
        if not self.check_bluetooth_ready():
            logging.error(f"[BT-Tether] Bluetooth pairing error")
            return
        try:
            self.configure_connection()
            self.configure_device()
            self.reload_connection()
            self.ready = True
            logging.info(f"[BT-Tether] Plugin configured")
            self.up_all(force=True)
        except ConfigError:
            logging.error(f"[BT-Tether] Error while configuring connection or device")

    # ---------- KERNEL DRIVER ----------
    def get_last_timestamp(self):
        """
        Retreive last kernel error. Ex: Bluetooth: hci0 command XXXXX tx timeout"
        """
        result = dmesg()
        try:
            last_error = [l for l in result.split("\n") if l.find("Bluetooth: hci0") != -1][-1]
            return re.match(KERN_ERROR_PTTRN, last_error).groups()[0]
        except IndexError:
            return None

    def check_driver(self):
        """
        Checks if there is a new kernel issue.
        """
        if self.driver_error:
            self.driver_state = DriverState.ERROR
        else:
            last_timestamp = self.get_last_timestamp()
            if last_timestamp != self.last_timestamp:
                self.last_timestamp = last_timestamp
                self.driver_error = True
                self.driver_state = DriverState.ERROR
            else:
                self.driver_state = DriverState.OK
        return self.driver_state

    def reload_drivers(self):
        """
        Reload kernel drivers by downing all, stoping daemon, removing modules,
        then it reloads everything.
        Can be removed in future version is the bug doesn't happen anymore
        """
        logging.info("[BT-Tether] Reloading kernel modules")
        systemctl("stop", "bluetooth")
        hciconfig("down")
        for module in ["hci_uart", "btbcm", "bnep", "bluetooth"]:
            rmmod(module)
        for module in ["btbcm", "hci_uart", "bnep", "bluetooth"]:
            modprobe(module)
        hciconfig("up")
        hciconfig("reset")
        systemctl("start", "bluetooth")
        systemctl("restart", "NetworkManager")
        bluetoothctl(["agent", "on"])
        logging.info("[BT-Tether] Kernel modules reloaded")
        self.driver_error = False

    # ---------- BLUETOOTH ----------
    def check_bluetooth(self):
        """
        Check bluetooth config and status with bluetoothctl
        """
        try:
            result = bluetoothctl(["--timeout", "1", "info", self.mac])
        except Exception as e:
            self.bluetooth_state = BTState.ERROR
            return self.bluetooth_state

        self.bluetooth_state = BTState.NOTCONFIGURED
        if paired := result.find(r"Paired: yes") != -1:
            self.bluetooth_state = BTState.PAIRED
        if trusted := result.find(r"Trusted: yes"):
            self.bluetooth_state = BTState.TRUSTED
        if paired and trusted:
            self.bluetooth_state = BTState.CONFIGURED
            if result.find(r"Connected: yes") != -1:
                self.bluetooth_state = BTState.CONNECTED
            elif result.find(r"Connected: no") != -1:
                self.bluetooth_state = BTState.DISCONNECTED
        return self.bluetooth_state

    def check_bluetooth_ready(self):
        """
        Check bluetooth pairing for configure. If the pairing/trust is wrong, it won't start.
        """
        match self.check_bluetooth():  # Checking BT pairing
            case BTState.CONNECTED | BTState.DISCONNECTED | BTState.CONFIGURED:
                return True
            case BTState.TRUSTED:
                logging.error(f"[BT-Tether] BT device ({self.mac}) trusted but not paired")
            case BTState.PAIRED:
                logging.error(f"[BT-Tether] BT device ({self.mac}) paired but not trusted")
            case BTState.NOTCONFIGURED:
                logging.error(f"[BT-Tether] BT device ({self.mac}) not configured")
            case BTState.ERROR:
                logging.error(f"[BT-Tether] Error with BT device ({self.mac})")
        return False

    def connect_bluetooth(self):
        """
        Check bluetooth status and tries to connect if necesary.
        """
        match self.check_bluetooth():
            case BTState.CONNECTED:
                logging.info(f"[BT-Tether] Bluetooth already up")
            case BTState.DISCONNECTED | BTState.CONFIGURED:
                try:
                    if bluetoothctl(["connect", self.mac], "Connection successful") != -1:
                        logging.info(f"[BT-Tether] BT device({self.mac}) connected")
                    else:
                        logging.info(f"[BT-Tether] Failed to connect to BT device({self.mac})")
                        logging.info(f"[BT-Tether] Let's try later")
                except Exception as e:
                    logging.error("[BT-Tether] Bluetooth up failed")
                    logging.error("[BT-Tether] Is tethering enabled on your phone?")
            case BTState.ERROR | BTState.TRUSTED | BTState.PAIRED | BTState.NOTCONFIGURED:
                logging.error(f"[BT-Tether] Error with BT device ({self.mac})")

    def disconnect_bluetooth(self):
        """
        Bluetooth disconnection
        """
        if self.check_bluetooth() == BTState.CONNECTED:
            try:
                bluetoothctl(["disconnect", f"{self.mac}"])
            except Exception as e:
                pass

    # ---------- DEVICE ----------
    def check_device(self):
        """
        Check NetworkManager device state
        """
        try:
            args = ["-w", "0", "-g", "GENERAL.STATE", "device", "show", self.mac]
            result = nmcli(args)
            if result.find("(connected)") != -1:  # Parenthesis are important
                self.device_state = DeviceState.UP
            elif result.find("connecting") != -1:  # Cover several connecting states
                self.device_state = DeviceState.CONNECTING
            elif result.find("(disconnected)") != -1 or result.find("(deactivating)") != -1:
                self.device_state = DeviceState.DOWN
            else:
                self.device_state = DeviceState.ERROR
        except Exception as e:
            self.device_state = DeviceState.ERROR
        return self.device_state

    def configure_device(self):
        """
        Configure NetworkManager device autoconnect and manager options.
        Used by configure
        """
        try:
            if self.autoconnect:
                nmcli(["device", "set", f"{self.mac}", "autoconnect", "yes", "managed", "yes"])
            else:
                nmcli(["device", "set", f"{self.mac}", "autoconnect", "no", "managed", "yes"])
            logging.info(f"[BT-Tether] Device ({self.mac}) configured")
        except Exception as e:
            logging.error(f"[BT-Tether] Error while configuring device: {e}")
            raise ConfigError()

    def up_device(self):
        """
        Check NetworkManager device status and tries to up if necesary.
        """
        match self.check_device():
            case DeviceState.UP:
                logging.info(f"[BT-Tether] Device already up")
            case DeviceState.CONNECTING:
                logging.info(f"[BT-Tether] Device already trying to up")
            case DeviceState.DOWN:
                try:
                    nmcli(["device", "up", f"{self.mac}"])
                    logging.info(f"[BT-Tether] Device {self.mac} up")
                except Exception as e:
                    logging.error(f"[BT-Tether] Failed to up device.")
                self.check_device()
            case DeviceState.ERROR:
                logging.error(f"[BT-Tether] Error with device ({self.mac})")

    def down_device(self):
        """
        NetworkManager device down
        """
        if self.check_device() in [DeviceState.UP, DeviceState.CONNECTING]:
            try:
                nmcli(["device", "down", f"{self.mac}"])
            except Exception as e:
                pass

    # ---------- CONNECTION ----------
    def check_connection(self):
        """
        Check NetworkManager connection state
        """
        try:
            args = ["-w", "0", "-g", "GENERAL.STATE", "connection", "show", self.phone_name]
            result = nmcli(args)
            if result.find("activated") != -1:
                self.connection_state = ConnectionState.UP
            elif result.find("activating") != -1:
                self.connection_state = ConnectionState.ACTIVATING
            elif (
                result == ""
                or result.find("deactivated") != -1
                or result.find("deactivating") != -1
            ):
                self.connection_state = ConnectionState.DOWN
            else:
                self.connection_state = ConnectionState.ERROR
        except Exception as e:
            self.connection_state = ConnectionState.ERROR
        return self.connection_state

    def configure_connection(self):
        """
        Configure NetworkManager connection options.
        Used by configure
        """
        try:
            args = ["connection", "modify", f"{self.phone_name}"]
            args += ["connection.type", "bluetooth"]
            args += ["bluetooth.type", "panu"]
            args += ["bluetooth.bdaddr", f"{self.mac}"]
            args += ["ipv4.method", "manual"]
            args += ["ipv4.dns", f"{self.dns}"]
            args += ["ipv4.addresses", f"{self.address}/24"]
            args += ["ipv4.route-metric", f"{self.metric}"]
            if self.internet:
                args += ["ipv4.gateway", f"{self.gateway}"]
            else:
                args += ["ipv4.gateway", ""]
            if self.autoconnect:
                args += ["connection.autoconnect", "yes"]
                args += ["connection.autoconnect-retries", "0"]
            else:
                args += ["connection.autoconnect", "no"]
            nmcli(args)
            logging.info(f"[BT-Tether] Connection ({self.phone_name}) configured")
        except Exception as e:
            logging.error(f"[BT-Tether] Error while configuring connection: {e}")
            raise ConfigError()

    def reload_connection(self):
        """
        Reload  NetworkManager connection avec configuration
        Used by configure.
        """
        try:
            nmcli(["connection", "reload"])
            logging.info(f"[BT-Tether] Connection reloaded")
        except Exception as e:
            logging.error(f"[BT-Tether] Error with connection reload")

    def up_connection(self):
        """
        Check NetworkManager connection status and tries to up if necesary.
        """
        match self.check_connection():
            case ConnectionState.UP:
                logging.info(f"[BT-Tether] Connection already up")
                return
            case ConnectionState.ACTIVATING:
                logging.info(f"[BT-Tether] Connection already trying to up")
                return
            case ConnectionState.DOWN:
                try:
                    nmcli(["connection", "up", f"{self.phone_name}"])
                    logging.info(f"[BT-Tether] Connection {self.phone_name} up")
                except Exception as e:
                    logging.error(f"[BT-Tether] Failed to up connection.")
            case ConnectionState.ERROR:
                logging.error(f"[BT-Tether] Error with connection ({self.phone_name})")

    def down_connection(self):
        """
        NetworkManager connection down
        """
        if self.check_connection() in [ConnectionState.UP, ConnectionState.ACTIVATING]:
            try:
                nmcli(["connection", "down", f"{self.phone_name}"])
            except Exception as e:
                pass

    # ---------- ALL UP and DOWN ----------
    def up_all(self, force=False):
        """
        Up all elements
        """
        logging.info(f"[BT-Tether] Trying to connect to {self.phone_name}")
        if self.check_driver() != DriverState.OK:
            logging.error(f"[BT-Tether] Error with bluetooth driver")
            return
        self.connect_bluetooth()
        time.sleep(2)
        if not force and self.check_bluetooth() != BTState.CONNECTED:
            return
        self.up_device()
        if not force and self.check_device() != DeviceState.UP:
            return
        time.sleep(2)
        self.up_connection()

    def down_all(self):
        """
        Down all elements
        """
        logging.info("[BT-Tether] Unloading connection")
        self.down_connection()
        self.down_device()
        self.disconnect_bluetooth()

    def reconnect(self):
        """
        Tries to reconnect if not using autoconnect
        """
        if (datetime.now(tz=UTC) - self.last_reconnect).total_seconds() < 30:
            return
        self.last_reconnect = datetime.now(tz=UTC)
        self.up_all()

    # ---------- MAIN LOOP ----------
    def run(self):
        """
        Check kernel and NetworkManager connection state.
        """
        logging.info("[BT-Tether] Starting loop")
        if not self.ready:
            logging.error("[BT-Tether] Thread not ready. Cancelling")
            return
        while self.running:
            time.sleep(10)
            match self.check_driver():
                case DriverState.OK:
                    pass
                case DriverState.ERROR:
                    self.down_all()
                    self.reload_drivers()
                    self.up_all()
                    continue

            match self.check_connection():
                case ConnectionState.UP | ConnectionState.ACTIVATING:
                    continue
                case ConnectionState.DOWN:
                    pass
                case ConnectionState.ERROR:
                    logging.error(f"[BT-Tether] Error with connection ({self.phone_name})")
                    return

            if not self.autoconnect:  # if autoconnect=false, need to up the connection on loss
                self.reconnect()

    def join(self, timeout=None):
        """
        End main loop and down all
        """
        self.running = False  # exit main loop
        try:
            super().join(timeout)
        except RuntimeError:  # Handle coding bugs and ensure the thread exit
            pass
        self.down_all()


class BTTether(plugins.Plugin):
    """
    Pwnagotchi BT plugin. Configure and starts BTManager and handle Display (UI/Web)
    """

    __author__ = "Jayofelony, modified my fmatray"
    __version__ = "1.6.0"
    __license__ = "GPL3"
    __description__ = "A new BT-Tether plugin"

    def __init__(self):
        self.options = dict()
        self.btmanager = None
        try:
            template_file = os.path.dirname(os.path.realpath(__file__)) + "/" + "bt-tether.html"
            with open(template_file, "r") as fb:
                self.template = fb.read()
        except Exception as e:
            logging.error(f"[BT-Tether] Error loading template file {template_file}: {e}")
            self.template = None

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded")

    def on_config_changed(self, config):
        """
        Read config and starts BTManager
        """
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
            address = self.options.get("ip", "192.168.44.2")
            gateway = "192.168.44.1"
        elif self.options["phone"].lower() == "ios":
            address = self.options.get("ip", "172.20.10.2")
            gateway = "172.20.10.1"
        if not re.match(IP_PTTRN, address):
            logging.error(f"[BT-Tether] IP error: {address}")
            return
        internet = self.options.get("internet", True)
        self.phone_name = self.options["phone-name"] + " Network"
        self.mac = self.options["mac"]

        dns = self.options.get("dns", "8.8.8.8 1.1.1.1")
        if not re.match(DNS_PTTRN, dns):
            if dns == "":
                logging.error(f"[BT-Tether] Empty DNS setting")
            else:
                logging.error(f"[BT-Tether] Wrong DNS setting: '{dns}'")
            return
        dns = re.sub("[\s,;]+", " ", dns).strip()  # DNS cleaning

        autoconnect = self.options.get("autoconnect", True)
        metric = self.options.get("metric", 200)
        self.btmanager = BTManager(
            self.phone_name, self.mac, address, gateway, dns, metric, internet, autoconnect
        )
        self.btmanager.start()

    def on_ready(self, agent):
        """
        Turns bettercap ble.recon off.
        """
        try:
            logging.info(f"[BT-Tether] Disabling bettercap's BLE module")
            agent.run("ble.recon off", verbose_errors=False)
        except Exception as e:
            pass

    def on_ui_setup(self, ui):
        """
        Add the BT element
        """
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
        """
        Stop  BTManager and remove UI elements.
        """
        with ui._lock:
            try:
                ui.remove_element("bluetooth")
            except KeyError:
                pass
        try:
            self.btmanager.join()
        except AttributeError:
            pass
        logging.info("[BT-Tether] plugin unloaded")

    # ---------- UI ----------
    def on_ui_update(self, ui):
        """
        Retreive BTManager state and display
        """
        if not (self.btmanager and self.btmanager.ready):
            return
        state, status = "", ""
        # Checking connection
        match self.btmanager.connection_state:
            case ConnectionState.UP:
                with ui._lock:
                    ui.set("bluetooth", "U")
                return
            case ConnectionState.ACTIVATING:
                state, status = "A", "Connection activating"
            case ConnectionState.DOWN:
                state, status = "-", "Connection down"
            case ConnectionState.ERROR:
                state, status = "E", "Connection error"

        # Checking drivers
        if self.btmanager.driver_state == DriverState.ERROR:
            state, status = "K", "Driver error"

        with ui._lock:
            ui.set("bluetooth", state)
            if status:
                ui.set("status", status)

    # ---------- WEB ----------
    def on_webhook(self, path, request):
        """
        Handle web requests to show actual configuration
        """
        if not (self.btmanager and self.btmanager.ready):
            return """<html>
                        <head><title>BT-tether: Error</title></head>
                        <body><code>Plugin not ready</code></body>
                    </html>"""

        if not self.template:
            return """<html>
                        <head><title>BT-tether: Error</title></head>
                        <body><code>Template not loaded</code></body>
                    </html>"""
        if path == "/" or not path:
            try:
                bluetooth = bluetoothctl(["info", self.mac])
                bluetooth_config = [
                    tuple(i.split(": ")) for i in bluetooth.replace("\t", "").split("\n")[1:]
                ]
                bluetooth_header = bluetooth.replace("\t", "").split("\n")[0]
            except Exception as e:
                bluetooth_header = "Error while checking bluetoothctl"
                bluetooth_config = []

            try:
                device = nmcli(["-w", "0", "device", "show", self.mac])
                device_config = [
                    tuple(i.split(": ")) for i in device.replace("\t", "").split("\n")[1:]
                ]
                device_header = device.replace("\t", "").split("\n")[0]
            except Exception as e:
                logging.error(e)
                device_header = "Error while checking nmcli device"
                device_config = []

            try:
                connection = nmcli(["-w", "0", "connection", "show", self.phone_name])
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
