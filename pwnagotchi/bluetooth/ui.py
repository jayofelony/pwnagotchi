import re
import threading
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
        "?": "Error",
    }

    @staticmethod
    def strip_ansi(text):
        """Remove ANSI escape codes from text."""
        if not text:
            return text
        ansi_escape = re.compile(r"\x1b\[[0-9;]*m|\x08")
        return ansi_escape.sub("", text)

    @staticmethod
    def format_status(status_dict, state_str=""):
        """Format status dict into a detailed display string."""
        connected = status_dict.get("connected", False)
        paired = status_dict.get("paired", False)
        trusted = status_dict.get("trusted", False)
        pan_active = status_dict.get("pan_active", False)
        ip_address = status_dict.get("ip_address", None)

        if pan_active:
            if ip_address:
                return f"BT:{ip_address}"
            else:
                return "BT:Connected"
        elif connected and trusted:
            return "BT:Trusted"
        elif connected:
            return "BT:Connected"
        elif paired:
            return "BT:Paired"
        else:
            return "BT:Disconnected"

    @staticmethod
    def get_status_icon(status_dict, state_str=""):
        """Get single-character status icon."""
        pan_active = status_dict.get("pan_active", False)
        connected = status_dict.get("connected", False)
        paired = status_dict.get("paired", False)
        trusted = status_dict.get("trusted", False)

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


class UICache:
    """Thread-safe cache for UI status to avoid blocking render calls."""

    def __init__(self):
        self._cache = {
            "paired": False,
            "trusted": False,
            "connected": False,
            "pan_active": False,
            "interface": None,
            "ip_address": None,
        }
        self._lock = threading.Lock()

    def update(self, status=None, **kwargs):
        """Update cache with new status."""
        with self._lock:
            if status is not None:
                self._cache.update(status)
            self._cache.update(kwargs)

    def get(self):
        """Get current cached status."""
        with self._lock:
            return self._cache.copy()

    def get_field(self, field, default=None):
        """Get single field from cache."""
        with self._lock:
            return self._cache.get(field, default)
