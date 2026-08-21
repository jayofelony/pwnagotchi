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
        "R": "Recovering Bluetooth",
        "D": "Disconnecting",
        "~": "Link stalled (probing)",
        "!": "Controller stuck - power-cycle",
        "?": "Error",
    }

    # Shown when a bluetooth restart could not clear a wedged controller
    STUCK_ICON = "!"
    STUCK_TEXT = "BT:Stuck-reboot"
    # Shown while the recovery ladder is actively resetting Bluetooth
    RECOVERING_ICON = "R"
    RECOVERING_TEXT = "BT:Recovering..."
    # Shown while the watchdog is counting failed peer probes on a live link
    STALLED_ICON = "~"
    STALLED_TEXT = "BT:Stalled?"

    @staticmethod
    def strip_ansi(text):
        """Remove ANSI escape codes from text."""
        if not text:
            return text
        ansi_escape = re.compile(r"\x1b\[[0-9;]*m|\x08")
        return ansi_escape.sub("", text)

    @classmethod
    def format_status(cls, status_dict, bt_stuck=False, recovering=False, stalled=False):
        """Format status dict into the detailed display line.

        Shows the tether address once PAN is up (IPv4, falling back to IPv6 for
        v6-only tethering). Transient truths outrank the steady-state view:
        - bt_stuck (while not connected): a bluetooth restart could not clear the
          controller, so a power-cycle is needed - not a plain "Paired".
        - recovering: the recovery ladder is actively resetting Bluetooth - the link
          bouncing through Paired/Connected is expected, not a problem.
        - stalled: the watchdog is counting failed peer probes - the link LOOKS
          connected but may be half-open, so don't show a healthy IP.
        A PAN without an address is shown as "No IP" (DHCP starving), which is a
        different situation than a healthy connect.
        """
        connected = status_dict.get("connected", False)
        paired = status_dict.get("paired", False)
        trusted = status_dict.get("trusted", False)
        pan_active = status_dict.get("pan_active", False)
        ip_address = status_dict.get("ip_address") or status_dict.get("ipv6")

        if bt_stuck and not connected:
            return cls.STUCK_TEXT
        if recovering:
            return cls.RECOVERING_TEXT

        if pan_active:
            if stalled:
                return cls.STALLED_TEXT
            return f"BT:{ip_address}" if ip_address else "BT:No IP"
        elif connected and trusted:
            return "BT:Trusted"
        elif connected:
            return "BT:Connected"
        elif paired:
            return "BT:Paired"
        else:
            return "BT:- -"

    @classmethod
    def get_status_icon(cls, status_dict, bt_stuck=False, recovering=False, stalled=False):
        """Get the single-character status icon.

        Settled states are uppercase (C/T/N/P/X); "R" is a recovery in progress,
        "~" a suspect (possibly half-open) link, "!" a wedged controller.
        """
        pan_active = status_dict.get("pan_active", False)
        connected = status_dict.get("connected", False)
        paired = status_dict.get("paired", False)
        trusted = status_dict.get("trusted", False)

        if bt_stuck and not connected:
            return cls.STUCK_ICON
        if recovering:
            return cls.RECOVERING_ICON

        if pan_active:
            return cls.STALLED_ICON if stalled else "C"
        elif connected and trusted:
            return "T"
        elif connected:
            return "N"
        elif paired:
            return "P"
        else:
            return "X"
