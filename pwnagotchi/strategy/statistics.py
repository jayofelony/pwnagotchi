"""Channel and interaction statistics tracking."""

import time
import logging


class ChannelStatistics:
    """Tracks AP counts, interactions, and handshakes per channel."""

    def __init__(self):
        self.histogram = {"loops": 0}  # AP count per channel per epoch
        self.chistos = {"_all_actions": {-1: 0}}  # Interaction stats per channel
        self.known_aps = {}  # All APs seen (key: normalized_name-mac)
        self.active_channels = []  # Channels with APs in current scan
        self.unscanned_channels = []  # Channels to explore next

    def mark_ap_seen(self, access_point, context=None):
        """Track an AP sighting and update stats."""
        try:
            apname = self._normalize(access_point.get("hostname", ""))
            apmac = self._normalize(access_point.get("mac", ""))
            apid = f"{apname}-{apmac}"
            channel = access_point.get("channel", -1)

            tag = f"AT_{context}" if context else "AT_seen"

            if apid not in self.known_aps:
                # First time seeing this AP
                self.known_aps[apid] = access_point.copy()
                self.known_aps[apid]["AT_seen"] = 1
                self.known_aps[apid][tag] = 1
                self.known_aps[apid]["AT_visible"] = True

                self.increment_chisto("Unique APs", channel)
                self.increment_chisto("Current APs", channel)
                logging.info(f"New AP: {apid} on channel {channel}")
            else:
                # Update existing AP
                for key in access_point:
                    self.known_aps[apid][key] = access_point[key]

                if not self.known_aps[apid]["AT_visible"]:
                    self.known_aps[apid]["AT_visible"] = True
                    self.known_aps[apid]["AT_seen"] += 1
                    self.increment_chisto("Current APs", channel)

                tag_count = self.known_aps[apid].get(tag, 0)
                self.known_aps[apid][tag] = tag_count + 1

            self.known_aps[apid]["AT_lastseen"] = time.time()
            return True

        except Exception as e:
            logging.debug(f"Error marking AP seen: {e}")
            return False

    def increment_chisto(self, stat_name, channel, count=1):
        """Increment a statistic for a channel."""
        if stat_name not in self.chistos:
            self.chistos[stat_name] = {}
        if channel not in self.chistos[stat_name]:
            self.chistos[stat_name][channel] = 0
        self.chistos[stat_name][channel] += count

    def update_active_channels(self, access_points):
        """Update list of channels with active APs."""
        active_channels = []
        self.histogram["loops"] = self.histogram.get("loops", 0) + 1

        for ap in access_points:
            self.mark_ap_seen(ap, "wifi_update")
            channel = ap.get("channel")
            if channel and channel not in active_channels:
                active_channels.append(channel)
                if channel in self.unscanned_channels:
                    self.unscanned_channels.remove(channel)

            self.histogram[channel] = self.histogram.get(channel, 0) + 1

        self.active_channels = active_channels
        logging.debug(f"Active channels: {active_channels}, Histogram: {self.histogram}")

    def record_interaction(self, interaction_type, channel):
        """Record an interaction (association, deauth, handshake) on a channel."""
        self.increment_chisto(interaction_type, channel)

    def record_ap_lost(self, access_point):
        """Record an AP going offline."""
        try:
            apname = self._normalize(access_point.get("hostname", ""))
            apmac = self._normalize(access_point.get("mac", ""))
            apid = f"{apname}-{apmac}"
            channel = access_point.get("channel", -1)

            if apid in self.known_aps:
                if self.known_aps[apid]["AT_visible"]:
                    self.known_aps[apid]["AT_visible"] = False
                    self.increment_chisto("Current APs", channel, -1)
            else:
                self.increment_chisto("Missed joins", channel)

        except Exception as e:
            logging.debug(f"Error recording AP lost: {e}")

    @staticmethod
    def _normalize(text):
        """Normalize text for comparison."""
        if not text:
            return ""
        return text.lower().replace(" ", "_")

    def get_stats(self):
        """Get current statistics snapshot."""
        return {
            "active_channels": self.active_channels.copy(),
            "unscanned_count": len(self.unscanned_channels),
            "known_aps": len(self.known_aps),
            "histogram": self.histogram.copy(),
            "chistos": self.chistos.copy(),
        }
