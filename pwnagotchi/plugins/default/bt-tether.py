import logging
import subprocess
import re
import time
import os
from dataclasses import dataclass, field, asdict
from threading import Thread, Event
from datetime import datetime, UTC
from enum import Enum, auto
from copy import deepcopy
from flask import render_template_string, render_template, abort
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

# We all love crazy regex patterns
MAC_PTTRN = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
IP_PTTRN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
DNS_PTTRN = r"^\s*((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]\s*)+((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[ ,;]?\s*)$"

KERN_ERROR_PTTRN = r"^\[\s*(\d+\.\d+)\]\s+Bluetooth:\s(hci0:\s.+.*)"


class ConfigError(Exception):
    pass


# ---------- PHONE STATES ----------
class BTState(Enum):
    """Bluetooth device states"""

    ERROR = auto()
    NOTCONFIGURED = auto()
    PAIRED = auto()
    TRUSTED = auto()
    CONFIGURED = auto()
    DISCONNECTED = auto()
    CONNECTED = auto()


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


# ---------- WATCHDOG STATES ----------
class DriverState(Enum):
    """Kernel Module states"""

    ERROR = auto()
    OK = auto()


class BluetoothdState(Enum):
    """Bluetooth server states"""

    ERROR = auto()
    OK = auto()


class WatchdogState(Enum):
    """Watchdog states"""

    ERROR = auto()
    OK = auto()


# ---------- COMMAND HELPERS ----------
def exec_cmd(cmd: str, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [cmd] + args, check=True, capture_output=True, text=True, timeout=timeout
        )
    except Exception as exp:
        logging.debug(f"[BT-Tether] Error with {cmd}: {exp}")
        raise exp


def bluetoothctl(args: list[str], pattern: str | None = None) -> int | str | None:
    result = exec_cmd("bluetoothctl", args)
    if not result:
        return None
    if not pattern:
        return result.stdout
    return result.stdout.find(pattern)


def nmcli(args: list[str], pattern: str | None = None) -> int | str | None:
    result = exec_cmd("nmcli", args)
    if not result:
        return None
    if not pattern:
        return result.stdout
    return result.stdout.find(pattern)


def ping(interface: str, target: str) -> bool:
    result = exec_cmd("ping", ["-c", "1", "-I", interface, target])
    if result:
        return result.returncode == 0
    return False


def rmmod(module: str) -> None:
    exec_cmd("rmmod", ["-f", module])


def modprobe(module: str) -> None:
    exec_cmd("modprobe", [module])


def hciconfig(command: str) -> None:
    exec_cmd("hciconfig", ["hci0", command])


def systemctl(command: str, service: str) -> None:
    exec_cmd("systemctl", [command, service], timeout=30)


def dmesg() -> str | None:
    if result := exec_cmd("dmesg", ["-l", "err", "-k"]):
        return result.stdout
    return None


@dataclass(slots=True)
class BTPhone:
    """
    Class for checking bluetooth, NetworkMananger device and NetworkMananger connection.
    This class tries to keep the connection up.
    """

    phone_name: str = field(compare=True)
    mac: str = field(compare=True)
    phone: str = field(compare=True)
    ip: str = field(compare=False)
    gateway: str = field(compare=False)
    dns: str = field(compare=False)
    metric: str = field(compare=False)
    internet: str = field(compare=False)
    autoconnect: str = field(compare=False)
    last_reconnect: datetime = field(
        default_factory=lambda: datetime(2025, 1, 1, 0, 0, tzinfo=UTC), compare=False
    )
    bluetooth_state: BTState = field(default=BTState.NOTCONFIGURED, compare=False)
    device_state: DeviceState = field(default=DeviceState.DOWN, compare=False)
    connection_state: ConnectionState = field(default=ConnectionState.DOWN, compare=False)
    up_date: datetime | None = None
    header: str = field(default="", compare=False)

    def __post_init__(self):
        self.header = f"[BT-Tether][{self.phone_name}]"
        logging.info(f"{self.header} IP: {self.ip}, Gateway: {self.gateway}, MAC: {self.mac}")

    @property
    def up_date_ago(self) -> tuple[int, int] | None:
        if self.up_date:
            seconds = round((datetime.now(tz=UTC) - self.up_date).total_seconds())
            return (seconds // 60, seconds % 60)
        return None

    @property
    def phone_network(self):
        return f"{self.phone_name} Network"

    def is_up(self):
        return self.connection_state == ConnectionState.UP

    def is_up_or_activating(self):
        return self.connection_state in [ConnectionState.UP, ConnectionState.ACTIVATING]

    def configure(self):
        """
        Check bluetooth pairing, configure NetworkMananger then tries to up all.
        """
        if not self.check_bluetooth_ready():
            logging.error(f"{self.header} Bluetooth pairing error")
            raise ConfigError()
        try:
            self.configure_connection()
            self.configure_device()
            self.reload_connection()
            logging.info(f"{self.header} Phone configured")
        except ConfigError:
            logging.error(f"{self.header} Error while configuring")
            raise ConfigError

    # ---------- BLUETOOTH ----------
    def check_bluetooth(self):
        """
        Check bluetooth config and status with bluetoothctl
        """
        try:
            result = bluetoothctl(["--timeout", "1", "info", self.mac])
        except Exception as e:
            logging.error(f"{self.header}[Bluetooth] Error on check: {e}")
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
                logging.error(
                    f"{self.header}[Bluetooth] BT device trusted but not paired: {self.mac}"
                )
            case BTState.PAIRED:
                logging.error(
                    f"{self.header}[Bluetooth] BT device paired but not trusted: {self.mac}"
                )
            case BTState.NOTCONFIGURED:
                logging.error(f"{self.header}[Bluetooth] BT device not configured: {self.mac}")
            case BTState.ERROR:
                logging.error(f"{self.header}[Bluetooth] Error with BT device: {self.mac}")
        return False

    def connect_bluetooth(self):
        """
        Check bluetooth status and tries to connect if necessary.
        """
        match self.check_bluetooth():
            case BTState.CONNECTED:
                logging.info(f"{self.header} Bluetooth already up")
            case BTState.DISCONNECTED | BTState.CONFIGURED:
                try:
                    if bluetoothctl(["connect", self.mac], "Connection successful") != -1:
                        logging.info(f"{self.header}[Bluetooth] BT device connected")
                    else:
                        logging.info(
                            f"{self.header}[Bluetooth] Failed to connect to BT device ({self.mac})"
                        )
                        logging.info(f"{self.header}[Bluetooth] Let's try later")
                except Exception as e:
                    logging.error(
                        f"{self.header}[Bluetooth] Bluetooth up failed ({self.mac}). Is tethering enabled on your phone?"
                    )
            case BTState.ERROR | BTState.TRUSTED | BTState.PAIRED | BTState.NOTCONFIGURED:
                logging.error(f"{self.header} Error with BT device ({self.mac})")

    def disconnect_bluetooth(self):
        """
        Bluetooth disconnection
        """
        if self.check_bluetooth() == BTState.DISCONNECTED:
            return
        try:
            bluetoothctl(["disconnect", f"{self.mac}"])
        except Exception as e:
            logging.error(
                f"{self.header}[Bluetooth] Failed to disconnect BT device ({self.mac}): {e}"
            )

    def get_bluetooth_config(self):
        try:
            return bluetoothctl(["info", self.mac])
        except Exception:
            logging.error(f"{self.header}[Bluetooth] Error while getting BT config ({self.mac})")
            return None

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
                logging.error(f"{self.header}[Device] Error on check: {result}")
        except Exception as e:
            self.device_state = DeviceState.ERROR
            logging.error(f"{self.header}[Device] Error on check: {e}")
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
            logging.info(f"{self.header}[Device] Device ({self.mac}) configured")
        except Exception as e:
            logging.error(f"{self.header}[Device] Error while configuring device ({self.mac}): {e}")
            raise ConfigError()

    def up_device(self):
        """
        Check NetworkManager device status and tries to up if necesary.
        """
        match self.check_device():
            case DeviceState.UP:
                logging.info(f"{self.header}[Device] Device already up")
            case DeviceState.CONNECTING:
                logging.info(f"{self.header}[Device] Device already trying to up")
            case DeviceState.DOWN:
                try:
                    nmcli(["device", "up", f"{self.mac}"])
                    logging.info(f"{self.header}[Device] Device {self.mac} up")
                except Exception as e:
                    logging.error(f"{self.header}[Device] Failed to up device.")
                self.check_device()
            case DeviceState.ERROR:
                logging.error(f"{self.header}[Device] Error with device ({self.mac})")

    def down_device(self):
        """
        NetworkManager device down
        """
        if self.check_device() == DeviceState.DOWN:
            return
        try:
            nmcli(["device", "down", f"{self.mac}"])
        except Exception as e:
            logging.error(f"{self.header}[Device] Failed to down device ({self.mac}): {e}")

    def get_device_config(self):
        try:
            return nmcli(["-w", "0", "device", "show", f"{self.mac}"])
        except Exception:
            logging.error(f"{self.header}[Device] Error on getting device config ({self.mac})")
            return None

    # ---------- CONNECTION ----------
    def check_connection(self):
        """
        Check NetworkManager connection state
        """
        try:
            args = ["-w", "0", "-g", "GENERAL.STATE", "connection", "show", self.phone_network]
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
                logging.error(f"{self.header}[Connection] Error on check: {result}")
        except Exception as e:
            self.connection_state = ConnectionState.ERROR
            logging.error(f"{self.header}[Connection] Error on check: {e}")
        return self.connection_state

    def configure_connection(self):
        """
        Configure NetworkManager connection options.
        Used by configure
        """
        try:
            args = ["connection", "modify", f"{self.phone_network}"]
            args += ["connection.type", "bluetooth"]
            args += ["bluetooth.type", "panu"]
            args += ["bluetooth.bdaddr", f"{self.mac}"]

            args += ["ipv4.method", "manual"]
            args += ["ipv4.dns", f"{self.dns}"]
            args += ["ipv4.addresses", f"{self.ip}/24"]
            args += ["ipv4.route-metric", f"{self.metric}"]
            if self.internet:
                args += ["ipv4.gateway", f"{self.gateway}"]
            else:
                args += ["ipv4.gateway", ""]

            if self.autoconnect:
                args += ["connection.autoconnect", "yes"]
                args += ["connection.autoconnect-retries", "5"]
            else:
                args += ["connection.autoconnect", "no"]
            nmcli(args)
            logging.info(f"{self.header}[Connection] Connection configured")
        except Exception as e:
            logging.error(f"{self.header}[Connection] Error while configuring : {e}")
            raise ConfigError()

    def reload_connection(self):
        """
        Reload NetworkManager connection avec configuration
        Used by configure.
        """
        try:
            nmcli(["connection", "reload"])
            logging.info(f"{self.header}[Connection] Connection reloaded")
        except Exception as e:
            logging.error(f"{self.header}[Connection] Error with connection reload: {e}")

    def up_connection(self):
        """
        Check NetworkManager connection status and tries to up if necesary.
        """
        match self.check_connection():
            case ConnectionState.UP:
                logging.info(f"{self.header}[Connection] Connection already up")
                return
            case ConnectionState.ACTIVATING:
                logging.info(f"{self.header}[Connection] Connection already trying to up")
                return
            case ConnectionState.DOWN:
                try:
                    nmcli(["connection", "up", f"{self.phone_network}"])
                    logging.info(f"{self.header}[Connection] Connection up")
                except Exception as e:
                    logging.error(f"{self.header}[Connection] Failed to up: {e}")
            case ConnectionState.ERROR:
                logging.error(f"{self.header}[Connection] Error with connection")

    def down_connection(self):
        """
        NetworkManager connection down
        """
        if self.check_connection() == ConnectionState.DOWN:
            return
        try:
            nmcli(["connection", "down", f"{self.phone_network}"])
        except Exception as e:
            logging.error(f"{self.header}[Connection] Failed to down connection: {e}")

    def get_connection_config(self):
        try:
            return nmcli(["-w", "0", "connection", "show", self.phone_network])
        except Exception:
            logging.error(f"{self.header}[Connection] Error on getting connection config")
            return None

    # ---------- Ping ----------
    def ping(self) -> bool:
        """
        Ping the gateway
        """
        try:
            return ping(self.ip, self.gateway)
        except Exception as e:
            pass
        return False

    # ---------- ALL UP and DOWN ----------
    def up(self):
        """
        Up all elements
        """
        logging.info(f"{self.header} Trying to up the connection")
        self.connect_bluetooth()
        time.sleep(2)
        if self.check_bluetooth() != BTState.CONNECTED:
            return
        self.up_device()
        if self.check_device() != DeviceState.UP:
            return
        time.sleep(2)
        self.up_connection()
        time.sleep(2)
        if self.check_connection() == ConnectionState.UP:
            self.up_date = datetime.now(tz=UTC)
            plugins.on("bluetooth_up", asdict(self))

    def down(self):
        """
        Down all elements
        """
        logging.info(f"{self.header} Downing the connection")
        self.down_connection()
        time.sleep(2)
        self.down_device()
        time.sleep(2)
        self.disconnect_bluetooth()
        time.sleep(2)
        if self.check_connection() == ConnectionState.DOWN:
            self.up_date = None
            plugins.on("bluetooth_down", asdict(self))

    def reconnect(self):
        """
        Tries to reconnect if not using autoconnect
        """
        if (datetime.now(tz=UTC) - self.last_reconnect).total_seconds() < 30:
            return
        self.last_reconnect = datetime.now(tz=UTC)
        self.up()

    # ---------- MAIN LOOP ----------
    def run(self, active: bool) -> ConnectionState:
        """
        Check NetworkManager connection state.
        """
        self.check_bluetooth()
        self.check_device()
        last_connection_state = self.connection_state
        connection_state = self.check_connection()
        if not active:
            return self.connection_state

        if last_connection_state != connection_state:
            match last_connection_state, connection_state:
                case ConnectionState.UP, _:
                    plugins.on("bluetooth_down", asdict(self))
                case _, ConnectionState.UP:
                    plugins.on("bluetooth_up", asdict(self))
                case _, _:
                    pass
        match connection_state:
            case ConnectionState.UP:
                if not self.ping():
                    logging.error(f"{self.header}[Ping] No ping anwser. Going down")
                    self.down()
                return self.connection_state
            case ConnectionState.ACTIVATING:
                return self.connection_state
            case ConnectionState.DOWN:
                pass
            case ConnectionState.ERROR:
                logging.error(
                    f"{self.header} Error with connection ({self.phone_network}). Reloading"
                )
                self.down()
                return self.connection_state

        if not self.autoconnect:  # if autoconnect=false, need to up the connection on loss
            self.reconnect()
        return self.connection_state


@dataclass(slots=True)
class BTManager(Thread):
    """
    Thread for checking kernel and call phone.run().
    If a kernel issue is detected, modules are reloaded properly.
    """

    phones: dict[str, BTPhone] = field(default_factory=dict)
    active_phone: str | None = None
    # Kernel modules variables
    # Assume the drivers won't mess during loading
    last_timestamp: str | None = None
    drivers_error: bool = False
    drivers_state: DriverState = DriverState.OK

    bluetoothd_state: BluetoothdState = BluetoothdState.OK
    bluetoothd_restart_retries: int = 0
    # Thread variables
    ready: bool = False
    exit: Event = field(default_factory=lambda: Event())
    header: str = "[BT-Tether][Manager]"

    def __post_init__(self):
        super(BTManager, self).__init__()
        self.last_timestamp, _ = self.get_last_timestamp()

    def __hash__(self):
        return super(BTManager, self).__hash__()

    def append_phone(self, phone: BTPhone) -> None:
        for key in self.phones:
            if self.phones[key] == phone:
                logging.error(f"{self.header} {phone.phone_name} Allready exists")
                return
        self.phones[phone.phone_name] = phone

    def configure(self):
        """
        Check bluetooth pairing, configure NetworkMananger then tries to up all.
        """
        try:
            self.restart_bluetoothd()
            for key in self.phones:
                self.phones[key].configure()
            self.ready = True
        except ConfigError:
            logging.error(f"{self.header} Error while configuring")

    # ---------- KERNEL DRIVERS ----------
    def get_last_timestamp(self) -> tuple[str | None, str | None]:
        """
        Retreive last timestamp of a kernel error. Ex:
        Bluetooth: hci0: command 0xXXXX tx timeout
        Bluetooth: hci0: link tx timeout
        Bluetooth: hci0: killing stalled connection XX:XX:XX:XX:XX:XX
        """
        try:
            if not (result := dmesg()):
                return (None, None)
            timestamp, message = re.findall(KERN_ERROR_PTTRN, result, re.MULTILINE)[-1]
            return (timestamp, message)
        except IndexError:
            return (None, None)

    def check_drivers(self):
        """
        Checks if there is a new kernel issue.
        """
        if self.drivers_error:
            self.drivers_state = DriverState.ERROR
        else:
            last_timestamp, message = self.get_last_timestamp()
            if last_timestamp != self.last_timestamp:
                self.last_timestamp = last_timestamp
                self.drivers_error = True
                self.drivers_state = DriverState.ERROR
                logging.error(f"{self.header}[Drivers] Kernel Drivers error(dmesg): {message}")
            else:
                self.drivers_state = DriverState.OK
        return self.drivers_state

    def reload_drivers(self):
        """
        Reload kernel drivers by downing all, stoping daemon, removing modules,
        then it reloads everything.
        Can be removed in future version is the bug doesn't happen anymore
        """
        logging.info(f"{self.header}[Drivers] Reloading kernel modules")
        self.stop_bluetoothd()
        hciconfig("down")
        for module in ["hci_uart", "btbcm", "bnep", "bluetooth"]:
            rmmod(module)
        for module in ["btbcm", "hci_uart", "bnep", "bluetooth"]:
            modprobe(module)
        hciconfig("up")
        hciconfig("reset")
        self.start_bluetoothd()
        systemctl("restart", "NetworkManager")
        logging.info(f"{self.header}[Drivers] Kernel modules reloaded")
        self.drivers_error = False

    # ---------- BLUETOOTH ----------
    def check_bluetoothd(self):
        """
        Check bluetoothd
        """
        try:
            bluetoothctl(["list"])
            self.bluetoothd_state = BluetoothdState.OK
        except Exception as e:
            self.bluetoothd_state = BluetoothdState.ERROR
            logging.error(f"{self.header}[Bluetoothd] Error on check: {e}")
        return self.bluetoothd_state

    def start_bluetoothd(self):
        try:
            logging.info(f"{self.header}[Bluetoothd] Start bluetooth service")
            systemctl("start", "bluetooth")
            time.sleep(2)
            bluetoothctl(["power", "on"])
            bluetoothctl(["agent", "on"])
        except Exception as e:
            logging.error(f"{self.header}[Bluetoothd] Error while starting bluetooth: {e}")

    def stop_bluetoothd(self):
        try:
            logging.info(f"{self.header}[Bluetoothd] Stoping bluetooth service")
            systemctl("stop", "bluetooth")
        except Exception as e:
            logging.error(f"{self.header}[Bluetoothd] Error while stoping bluetooth: {e}")

    def restart_bluetoothd(self):
        try:
            logging.info(f"{self.header}[Bluetoothd] Restarting bluetooth service")
            systemctl("restart", "bluetooth")
            time.sleep(2)
            bluetoothctl(["power", "on"])
            bluetoothctl(["agent", "on"])
        except Exception as e:
            logging.error(f"{self.header}[Bluetoothd] Error while restarting bluetooth: {e}")

    # ---------- ALL UP and DOWN ----------
    def up_one_phone(self) -> str | None:
        """
        Up one phones
        """
        for key in self.phones:
            if not self.active_phone:
                logging.info(f"{self.header} Trying to activate phone: {key}")
                self.phones[key].up()
                if self.phones[key].is_up():
                    self.active_phone = key
                    continue
            self.phones[key].down()
        if self.active_phone:
            logging.info(f"{self.header} Current active connection: {self.active_phone}")
        else:
            logging.info(f"{self.header} No active connection")
        return self.active_phone

    def down(self):
        """
        Down all phones
        """
        for key in self.phones:
            self.phones[key].down()
        self.active_phone = None

    def full_reload_drivers(self):
        """
        Reload all phones
        """
        logging.info(f"{self.header} Reloading kernel modules and connections")
        self.down()
        self.reload_drivers()

    # ---------- MAIN LOOP ----------
    def drivers_watchdog(self) -> WatchdogState:
        match self.check_drivers():
            case DriverState.OK:
                return WatchdogState.OK
            case DriverState.ERROR:
                self.full_reload_drivers()
                return WatchdogState.ERROR
        return WatchdogState.OK

    def bluetoothd_watchdog(self) -> WatchdogState:
        match self.check_bluetoothd():
            case BluetoothdState.OK:
                self.bluetoothd_restart_retries = 0
                return WatchdogState.OK
            case BluetoothdState.ERROR:
                if self.bluetoothd_restart_retries < 3:  # try to restart bluetooth service first
                    self.bluetoothd_restart_retries += 1
                    logging.info(
                        f"{self.header}[Bluetoothd] Trying to restart bluetooth service: {self.bluetoothd_restart_retries} tries"
                    )
                    self.restart_bluetoothd()
                else:  # reload drivers
                    logging.info(
                        f"{self.header}[Bluetoothd] Number of retries exceeded ({self.bluetoothd_restart_retries} tries): Reloading all"
                    )
                    self.full_reload_drivers()
                    self.bluetoothd_restart_retries = 0
                    return WatchdogState.ERROR
        return WatchdogState.OK

    def phone_watchdog(self) -> WatchdogState:
        # Check for multiple connections
        nb = 0
        for key in self.phones:
            self.phones[key].check_connection()
            if self.phones[key].is_up_or_activating():
                nb += 1
        if nb > 1:
            logging.error(f"{self.header}[Phones] Multiple connections at the same time: {nb}")
            self.active_phone = None

        # RUN
        if self.active_phone:
            for key in self.phones:
                self.phones[key].run(self.active_phone == key)
            if self.phones[self.active_phone].is_up_or_activating():
                return WatchdogState.OK
        uptime_str = ""
        if self.active_phone and (uptime_ago := self.phones[self.active_phone].up_date_ago):
            uptime_str = f" (uptime:{uptime_ago[0]}min {uptime_ago[1]}s)"
            logging.error(
                f"{self.header}[Phones] Connection lost with {self.active_phone}{uptime_str}"
            )

        # No active connection, try to up one
        self.active_phone = None
        if self.up_one_phone():
            return WatchdogState.OK
        return WatchdogState.ERROR

    def watchdog(self):
        """
        Check kernel and NetworkManager connection state.
        """
        nb_tries = 0
        time_sleep = 10
        while not self.exit.is_set():
            for func in [self.drivers_watchdog, self.bluetoothd_watchdog, self.phone_watchdog]:
                if self.exit.wait(10):
                    return
                if func() == WatchdogState.ERROR:
                    nb_tries += 1
                    break
            else:
                nb_tries = 0
                time_sleep = 10
            if nb_tries == 3:
                logging.error(f"{self.header}[Watchdog] Multiple errors. Let's wait {time_sleep}s")
                self.down()
                nb_tries = 0
                time_sleep = min(time_sleep * 2, 60)
                self.exit.wait(time_sleep)

    def run(self):
        logging.info(f"{self.header} Starting watchdog")
        if not self.ready:
            logging.critical(f"{self.header} Thread not ready. Cancelling")
            return
        try:
            self.up_one_phone()
            self.watchdog()
        except Exception as e:
            logging.error(f"{self.header} Error on watchdog: {e}")

    def join(self, timeout=None):
        """
        End main loop and down all
        """
        self.exit.set()
        try:
            super(BTManager, self).join(timeout)
        except RuntimeError:  # Handle coding bugs and ensure the thread exit
            pass
        self.down()

    # ---------- CONNECTION STATE ----------
    def get_connection_state(self) -> ConnectionState:
        state = max([phone.connection_state.value for phone in self.phones.values()])
        return ConnectionState(state)


class BTTether(plugins.Plugin):
    """
    Pwnagotchi BT plugin. Configure and starts BTManager and handle Display (UI/Web)
    """

    __author__ = "Jayofelony, modified my fmatray"
    __version__ = "1.7.0"
    __license__ = "GPL3"
    __description__ = "A new BT-Tether plugin"

    def __init__(self):
        self.options = dict()
        self.ip_end = 2
        self.btmanager = None
        self.header = "[BT-Tether][Plugin]"
        try:
            template_file = os.path.dirname(os.path.realpath(__file__)) + "/" + "bt-tether.html"
            with open(template_file, "r") as fb:
                self.template = fb.read()
        except Exception as e:
            logging.error(f"{self.header} Error loading template file {template_file}: {e}")
            self.template = None

    def on_loaded(self):
        logging.info(f"{self.header} Plugin loaded. Version {self.__version__}")

    # ---------- CONFIGURATION ----------
    def on_config_changed(self, config):
        """
        Read config and starts BTManager
        """
        self.btmanager = BTManager()
        default_options = self.read_options(self.options)
        if "phone-name" in self.options and (
            phone := self.create_btdevice(self.options, default_options)
        ):
            self.btmanager.append_phone(phone)

        if phones := self.options.get("phones", None):
            if not isinstance(phones, list):
                logging.error(f"{self.header} Phones options error, must be a list of dict")
            for phone_options in phones:
                if not isinstance(phone_options, dict):
                    logging.error(f"{self.header} Phones options error, must be a list of dict")
                if phone := self.create_btdevice(phone_options, default_options):
                    self.btmanager.append_phone(phone)
        self.btmanager.configure()
        self.btmanager.start()
        logging.info(f"{self.header} Plugin configured")

    def read_mandatory_options(self, options: dict) -> dict | None:
        # Phone Name
        if not (phone_name := options.get("phone-name", None)):
            return None

        # MAC
        mac = options.get("mac", None)
        if not (mac and re.match(MAC_PTTRN, mac)):
            logging.error(f"{self.header}[{phone_name}] Error with mac address: {mac}")
            return None

        # PHONE + IP + GATEWAY
        phone = options.get("phone", "").lower()
        match phone:
            case "android":
                default_ip = f"192.168.44.{self.ip_end}"
                default_gateway = "192.168.44.1"
            case "ios":
                default_ip = f"172.20.10.{self.ip_end}"
                default_gateway = "172.20.10.1"
            case _:
                logging.error(f"{self.header}[{phone_name}] Phone type {phone} not supported")
                return None
        ip = options.get("ip", None)
        if not ip:
            ip = default_ip
            self.ip_end += 1
        elif not re.match(IP_PTTRN, ip):
            logging.error(f"{self.header}[{phone_name}] Error with IP: '{ip}'. Using default")
            ip = default_ip
            self.ip_end += 1

        gateway = options.get("gateway", None)
        if not gateway:
            gateway = default_gateway
        elif not re.match(IP_PTTRN, gateway):
            logging.error(
                f"{self.header}[{phone_name}] Error with gateway: '{gateway}'. Using default"
            )
            gateway = default_gateway
        return dict(phone_name=phone_name, mac=mac, phone=phone, ip=ip, gateway=gateway)

    def read_options(
        self, options: dict, defaults: dict[str, str | int | bool] | None = None
    ) -> dict[str, str | int | bool]:
        DEFAULT_DNS = "8.8.8.8 1.1.1.1"
        if not defaults:
            defaults = dict(dns=DEFAULT_DNS, metric=200, internet=True, autoconnect=False)

        dns = options.get("dns", defaults["dns"])
        if not re.match(DNS_PTTRN, dns):
            logging.error(f"{self.header} Wrong DNS setting: '{dns}'. Using default")
            dns = DEFAULT_DNS
        dns = re.sub("[\s,;]+", " ", dns).strip()  # DNS cleaning
        metric = self.options.get("metric", defaults["metric"])
        internet = self.options.get("internet", defaults["internet"])
        autoconnect = self.options.get("autoconnect", defaults["autoconnect"])
        return dict(dns=dns, metric=metric, internet=internet, autoconnect=autoconnect)

    def create_btdevice(
        self, options: dict[str, str | int | bool], default_options: dict[str, str | int | bool]
    ) -> BTPhone | None:
        if not (phone_options := self.read_mandatory_options(options)):
            return None
        phone_options.update(self.read_options(options, default_options))
        return BTPhone(**phone_options)

    def on_ready(self, agent):
        """
        Turns bettercap ble.recon off.
        """
        try:
            logging.info(f"{self.header} Disabling bettercap's BLE module")
            agent.run("ble.recon off", verbose_errors=False)
        except Exception as e:
            pass

    def on_unload(self, ui):
        """
        Stop  BTManager and remove UI elements.
        """
        with ui._lock:
            try:
                ui.remove_element("bluetooth")
            except KeyError:
                pass
        if self.btmanager:
            self.btmanager.join()
        logging.info(f"{self.header} Plugin unloaded")

    # ---------- UI ----------
    def on_ui_setup(self, ui):
        """
        Add the BT element to the UI
        """
        with ui._lock:
            ui.add_element(
                "bluetooth",
                LabeledValue(
                    color=BLACK,
                    label="BT",
                    value="#",
                    position=(ui.width() / 2 - 10, 0),
                    label_font=fonts.Bold,
                    text_font=fonts.Medium,
                ),
            )

    def on_ui_update(self, ui):
        """
        Retreive BTManager state and display
        """
        if not (self.btmanager and self.btmanager.ready):
            return
        state, status = "", None
        # Checking connection
        match self.btmanager.get_connection_state():
            case ConnectionState.UP:
                state = "U"
                status = f"Active conn.:\n{self.btmanager.active_phone}"
            case ConnectionState.ACTIVATING:
                state, status = "A", "Connection activating"
            case ConnectionState.DOWN:
                state, status = "-", "Connection down"
            case ConnectionState.ERROR:
                state, status = "E", "Connection error"

        # Checking drivers
        if self.btmanager.drivers_state == DriverState.ERROR:
            state, status = "K", "Drivers error"

        with ui._lock:
            ui.set("bluetooth", state)
            if status:
                ui.set("status", status)

    # ---------- WEB UI----------
    def on_webhook(self, path, request):
        """
        Handle web requests to show actual configuration
        """
        if not (self.btmanager and self.btmanager.ready):
            return render_template(
                "status.html", title="Error", go_back_after=10, message="Plugin not ready"
            )
        if not self.template:
            return render_template(
                "status.html", title="Error", go_back_after=10, message="Template not loaded"
            )
        if path == "/" or not path:
            try:
                return render_template_string(
                    self.template,
                    title="BT-Tether",
                    phones=deepcopy(self.btmanager.phones),
                    active_phone=self.btmanager.active_phone,
                )
            except Exception as e:
                logging.error(f"{self.header}[WEB] Error while rendering template: {e}")
                return render_template(
                    "status.html", title="Error", go_back_after=10, message=f"Rendering error: {e}"
                )
        abort(404)
