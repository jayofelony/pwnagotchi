import re
import logging


class BluetoothDevice:
    """Represents a Bluetooth device with connection state."""

    def __init__(self, mac, name, paired=False, trusted=False, connected=False, has_nap=False):
        self.mac = mac
        self.name = name
        self.paired = paired
        self.trusted = trusted
        self.connected = connected
        self.has_nap = has_nap

    def __eq__(self, other):
        if isinstance(other, BluetoothDevice):
            return self.mac == other.mac
        return False

    def __hash__(self):
        return hash(self.mac)

    def __repr__(self):
        return f"BluetoothDevice(mac={self.mac}, name={self.name}, paired={self.paired}, trusted={self.trusted}, connected={self.connected}, has_nap={self.has_nap})"

    @staticmethod
    def validate_mac(mac):
        """Validate MAC address format."""
        if not mac:
            return False
        pattern = r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"
        return bool(re.match(pattern, mac))

    @staticmethod
    def from_info_output(mac, name, info_dict):
        """Create device from bluetoothctl info output."""
        paired = info_dict.get("Paired", "no").lower() == "yes"
        trusted = info_dict.get("Trusted", "no").lower() == "yes"
        connected = info_dict.get("Connected", "no").lower() == "yes"
        has_nap = "PNP" in info_dict.get("UUID", "") or info_dict.get("Has_NAP", False)
        return BluetoothDevice(mac, name, paired, trusted, connected, has_nap)
