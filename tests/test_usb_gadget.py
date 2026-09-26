import ipaddress
import json
import tempfile
import unittest
from pathlib import Path

from pwnagotchi.usb_gadget import (
    CLIENT_PROFILE,
    SHARED_PROFILE,
    WATCHER_SERVICE,
    UsbGadgetConfigError,
    apply_options,
    find_local_conflicts,
    load_options,
    validate_options,
)


class FakeRunner:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.commands = []

    def __call__(self, command):
        command = tuple(command)
        self.commands.append(command)
        return self.responses.get(command, "")


class UsbGadgetTests(unittest.TestCase):
    def test_missing_config_keeps_management_disabled(self):
        options = load_options("/path/that/does/not/exist")
        self.assertFalse(options["manage"])
        self.assertEqual(options["mode"], "auto")

    def test_loads_usb_gadget_table(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                '[usb_gadget]\nmanage = true\nmode = "shared"\n'
                'shared_address = "10.12.195.1/28"\n',
                encoding="utf-8",
            )
            options = load_options(config)

        self.assertTrue(options["manage"])
        self.assertEqual(options["mode"], "shared")
        self.assertEqual(options["shared_address"], "10.12.195.1/28")

    def test_rejects_invalid_mode_and_address(self):
        with self.assertRaises(UsbGadgetConfigError):
            validate_options({
                "manage": True,
                "mode": "invalid",
                "interface": "usb0",
                "shared_address": "10.12.194.1/28",
                "check_conflicts": True,
            })
        with self.assertRaises(UsbGadgetConfigError):
            validate_options({
                "manage": True,
                "mode": "shared",
                "interface": "usb0",
                "shared_address": "not-an-address",
                "check_conflicts": True,
            })

    def test_detects_non_usb_address_and_route_conflicts(self):
        runner = FakeRunner({
            ("ip", "-j", "-4", "address", "show"): json.dumps([
                {
                    "ifname": "wlan0",
                    "addr_info": [{
                        "family": "inet",
                        "local": "10.12.195.20",
                        "prefixlen": 24,
                    }],
                },
                {
                    "ifname": "usb0",
                    "addr_info": [{
                        "family": "inet",
                        "local": "10.12.195.1",
                        "prefixlen": 28,
                    }],
                },
            ]),
            ("ip", "-j", "-4", "route", "show"): json.dumps([
                {"dst": "10.12.195.0/25", "dev": "eth0"},
                {"dst": "default", "dev": "wlan0"},
            ]),
        })

        conflicts = find_local_conflicts(
            ipaddress.ip_network("10.12.195.0/28"),
            "usb0",
            runner,
        )

        self.assertEqual(len(conflicts), 2)

    def test_auto_mode_updates_address_and_enables_watcher(self):
        runner = FakeRunner({
            ("ip", "-j", "-4", "address", "show"): "[]",
            ("ip", "-j", "-4", "route", "show"): "[]",
            (
                "nmcli", "-g", "ipv4.addresses", "connection", "show", SHARED_PROFILE
            ): "10.12.194.1/28",
            (
                "nmcli", "-g", "GENERAL.CONNECTION", "device", "show", "usb0"
            ): CLIENT_PROFILE,
        })
        changed = apply_options({
            "manage": True,
            "mode": "auto",
            "interface": "usb0",
            "shared_address": "10.12.195.1/28",
            "check_conflicts": True,
        }, runner)

        self.assertTrue(changed)
        self.assertIn(
            ("systemctl", "enable", "--now", WATCHER_SERVICE),
            runner.commands,
        )

    def test_active_shared_profile_is_reapplied_after_address_change(self):
        runner = FakeRunner({
            ("ip", "-j", "-4", "address", "show"): "[]",
            ("ip", "-j", "-4", "route", "show"): "[]",
            (
                "nmcli", "-g", "ipv4.addresses", "connection", "show", SHARED_PROFILE
            ): "10.12.194.1/28",
            (
                "nmcli", "-g", "GENERAL.CONNECTION", "device", "show", "usb0"
            ): SHARED_PROFILE,
        })
        changed = apply_options({
            "manage": True,
            "mode": "shared",
            "interface": "usb0",
            "shared_address": "10.12.195.1/28",
            "check_conflicts": True,
        }, runner)

        self.assertTrue(changed)
        self.assertIn(
            ("nmcli", "connection", "up", SHARED_PROFILE, "ifname", "usb0"),
            runner.commands,
        )
        self.assertIn(
            (
                "nmcli", "connection", "modify", SHARED_PROFILE,
                "ipv4.method", "shared", "ipv4.addresses", "10.12.195.1/28",
            ),
            runner.commands,
        )

    def test_forced_client_stops_watcher_and_switches_profile(self):
        runner = FakeRunner({
            ("ip", "-j", "-4", "address", "show"): "[]",
            ("ip", "-j", "-4", "route", "show"): "[]",
            (
                "nmcli", "-g", "ipv4.addresses", "connection", "show", SHARED_PROFILE
            ): "10.12.194.1/28",
            (
                "nmcli", "-g", "GENERAL.CONNECTION", "device", "show", "usb0"
            ): SHARED_PROFILE,
        })
        changed = apply_options({
            "manage": True,
            "mode": "client",
            "interface": "usb0",
            "shared_address": "10.12.194.1/28",
            "check_conflicts": True,
        }, runner)

        self.assertTrue(changed)
        self.assertIn(
            ("systemctl", "stop", WATCHER_SERVICE),
            runner.commands,
        )
        self.assertIn(
            ("nmcli", "connection", "up", CLIENT_PROFILE, "ifname", "usb0"),
            runner.commands,
        )


if __name__ == "__main__":
    unittest.main()
