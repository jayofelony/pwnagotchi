import argparse
import ipaddress
import json
import logging
import os
import shutil
import subprocess
import sys

import tomlkit


CLIENT_PROFILE = "USB Gadget (client)"
SHARED_PROFILE = "USB Gadget (shared)"
WATCHER_SERVICE = "rpi-usb-gadget-ics.service"

DEFAULT_OPTIONS = {
    "manage": False,
    "mode": "auto",
    "interface": "usb0",
    "shared_address": "10.12.194.1/28",
    "check_conflicts": True,
}


class UsbGadgetConfigError(ValueError):
    pass


def load_options(config_path):
    options = dict(DEFAULT_OPTIONS)
    if not os.path.exists(config_path):
        return options

    with open(config_path, encoding="utf-8") as config_file:
        config = tomlkit.load(config_file)

    configured = config.get("usb_gadget", {})
    if not isinstance(configured, dict):
        raise UsbGadgetConfigError("[usb_gadget] must be a TOML table")

    for key in DEFAULT_OPTIONS:
        if key in configured:
            options[key] = configured[key]
    return options


def validate_options(options):
    mode = str(options["mode"]).lower()
    if mode not in ("auto", "client", "shared"):
        raise UsbGadgetConfigError(
            "usb_gadget.mode must be one of: auto, client, shared"
        )

    interface = str(options["interface"]).strip()
    if not interface:
        raise UsbGadgetConfigError("usb_gadget.interface cannot be empty")

    try:
        shared_address = ipaddress.ip_interface(str(options["shared_address"]))
    except ValueError as error:
        raise UsbGadgetConfigError(
            "usb_gadget.shared_address must be a valid IPv4 CIDR"
        ) from error

    if shared_address.version != 4:
        raise UsbGadgetConfigError(
            "usb_gadget.shared_address must be an IPv4 CIDR"
        )
    if shared_address.network.prefixlen > 30:
        raise UsbGadgetConfigError(
            "usb_gadget.shared_address must leave room for a DHCP client"
        )
    if shared_address.ip in (
        shared_address.network.network_address,
        shared_address.network.broadcast_address,
    ):
        raise UsbGadgetConfigError(
            "usb_gadget.shared_address must be a usable host address"
        )

    validated = dict(options)
    validated["mode"] = mode
    validated["interface"] = interface
    validated["shared_address"] = str(shared_address)
    validated["manage"] = bool(options["manage"])
    validated["check_conflicts"] = bool(options["check_conflicts"])
    return validated


def run_command(command):
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        message = "%s failed" % command[0]
        if detail:
            message += ": %s" % detail
        raise UsbGadgetConfigError(message) from error
    return result.stdout.strip()


def find_local_conflicts(network, interface, run=run_command):
    conflicts = set()

    addresses = json.loads(run(["ip", "-j", "-4", "address", "show"]))
    for device in addresses:
        if device.get("ifname") == interface:
            continue
        for address in device.get("addr_info", []):
            if address.get("family") != "inet" or "local" not in address:
                continue
            local_network = ipaddress.ip_network(
                "%s/%s" % (address["local"], address["prefixlen"]),
                strict=False,
            )
            if network.overlaps(local_network):
                conflicts.add(
                    "%s on %s" % (local_network, device.get("ifname", "?"))
                )

    routes = json.loads(run(["ip", "-j", "-4", "route", "show"]))
    for route in routes:
        destination = route.get("dst")
        if route.get("dev") == interface or destination in (None, "default"):
            continue
        try:
            route_network = ipaddress.ip_network(destination, strict=False)
        except ValueError:
            continue
        if network.overlaps(route_network):
            conflicts.add(
                "route %s via %s" % (route_network, route.get("dev", "?"))
            )

    return sorted(conflicts)


def apply_options(options, run=run_command):
    options = validate_options(options)
    if not options["manage"]:
        logging.info("USB gadget configuration management is disabled")
        return False

    shared_address = ipaddress.ip_interface(options["shared_address"])
    if options["check_conflicts"] and options["mode"] != "client":
        conflicts = find_local_conflicts(
            shared_address.network,
            options["interface"],
            run=run,
        )
        if conflicts:
            raise UsbGadgetConfigError(
                "USB gadget shared network %s overlaps with %s"
                % (shared_address.network, ", ".join(conflicts))
            )

    if options["mode"] == "auto":
        run(["systemctl", "enable", "--now", WATCHER_SERVICE])
    else:
        # Stop the watcher for this boot without disabling it persistently. If
        # management is later turned off, auto mode returns on the next boot.
        run(["systemctl", "stop", WATCHER_SERVICE])

    current_address = run(
        [
            "nmcli",
            "-g",
            "ipv4.addresses",
            "connection",
            "show",
            SHARED_PROFILE,
        ]
    )
    address_changed = current_address != options["shared_address"]
    if address_changed:
        run(
            [
                "nmcli",
                "connection",
                "modify",
                SHARED_PROFILE,
                "ipv4.method",
                "shared",
                "ipv4.addresses",
                options["shared_address"],
            ]
        )

    active_profile = run(
        [
            "nmcli",
            "-g",
            "GENERAL.CONNECTION",
            "device",
            "show",
            options["interface"],
        ]
    )
    if options["mode"] == "auto":
        desired_profile = active_profile
        must_activate = address_changed and active_profile == SHARED_PROFILE
    else:
        desired_profile = (
            CLIENT_PROFILE if options["mode"] == "client" else SHARED_PROFILE
        )
        must_activate = active_profile != desired_profile or (
            address_changed and desired_profile == SHARED_PROFILE
        )

    if must_activate:
        logging.warning(
            "Switching %s to %s; the current USB connection may disconnect",
            options["interface"],
            desired_profile,
        )
        run(
            [
                "nmcli",
                "connection",
                "up",
                desired_profile,
                "ifname",
                options["interface"],
            ]
        )
        return True

    return address_changed


def check_commands():
    missing = [
        name for name in ("ip", "nmcli", "systemctl") if not shutil.which(name)
    ]
    if missing:
        raise UsbGadgetConfigError(
            "required command(s) not found: %s" % ", ".join(missing)
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Apply Pwnagotchi USB gadget settings to NetworkManager"
    )
    parser.add_argument(
        "--config",
        default="/etc/pwnagotchi/config.toml",
        help="Pwnagotchi user configuration file",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        options = load_options(args.config)
        if not options["manage"]:
            logging.info("USB gadget configuration management is disabled")
            return 0
        check_commands()
        changed = apply_options(options)
        if changed:
            logging.info("USB gadget configuration applied")
        else:
            logging.info("USB gadget configuration is already current")
        return 0
    except (
        OSError,
        subprocess.CalledProcessError,
        tomlkit.exceptions.ParseError,
        UsbGadgetConfigError,
    ) as error:
        logging.error("could not configure USB gadget: %s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
