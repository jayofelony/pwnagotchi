import re
import logging


class UIRenderer:
    """Renders Bluetooth status for display."""

    DISPLAY_CODES = {
        "C": "Connected with PAN",
        "T": "Trusted",
        "N": "Connected (no tether)",
        "P": "Paired",
        "X": "No device",
        "I": "Initializing",
        "S": "Scanning",
        ">": "Connecting",
        "R": "Reconnecting",
        "D": "Disconnecting",
        "!": "Controller stuck - power-cycle",
        "?": "Error",
    }

    # Shown when a bluetooth restart could not clear a wedged controller
    STUCK_ICON = "!"
    STUCK_TEXT = "BT:Stuck-reboot"

    @staticmethod
    def strip_ansi(text):
        """Remove ANSI escape codes from text."""
        if not text:
            return text
        ansi_escape = re.compile(r"\x1b\[[0-9;]*m|\x08")
        return ansi_escape.sub("", text)

    @classmethod
    def format_status(cls, status_dict, bt_stuck=False):
        """Format status dict into the detailed display line.

        Shows the tether address once PAN is up (IPv4, falling back to IPv6 for
        v6-only tethering). bt_stuck takes precedence while not connected: a
        bluetooth restart could not clear the controller, so a power-cycle is
        needed and the user should see that rather than a plain "Paired".
        """
        connected = status_dict.get("connected", False)
        paired = status_dict.get("paired", False)
        trusted = status_dict.get("trusted", False)
        pan_active = status_dict.get("pan_active", False)
        ip_address = status_dict.get("ip_address") or status_dict.get("ipv6")

        if bt_stuck and not connected:
            return cls.STUCK_TEXT

        if pan_active:
            return f"BT:{ip_address}" if ip_address else "BT:Connected"
        elif connected and trusted:
            return "BT:Trusted"
        elif connected:
            return "BT:Connected"
        elif paired:
            return "BT:Paired"
        else:
            return "BT:- -"

    @classmethod
    def get_status_icon(cls, status_dict, bt_stuck=False):
        """Get the single-character status icon.

        Settled states are uppercase (C/T/N/P/X); "!" flags a wedged controller.
        """
        pan_active = status_dict.get("pan_active", False)
        connected = status_dict.get("connected", False)
        paired = status_dict.get("paired", False)
        trusted = status_dict.get("trusted", False)

        if bt_stuck and not connected:
            return cls.STUCK_ICON

        if pan_active:
            return "C"
        elif connected and trusted:
            return "T"
        elif connected:
            return "N"
        elif paired:
            return "P"
        else:
            return "X"
