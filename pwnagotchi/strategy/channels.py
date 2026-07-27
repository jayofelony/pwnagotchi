"""Channel selection strategy - core to agent behavior."""

import random
import logging
import pwnagotchi.utils
from .statistics import ChannelStatistics


class ChannelStrategy:
    """
    Intelligent channel selection strategy.

    Strategy:
    - Always scan channels with active APs (high probability of captures)
    - Add random unscanned channels each epoch (explore new areas)
    - Track statistics per channel to guide future decisions
    """

    def __init__(self, config, logger=None):
        """
        Initialize channel strategy.

        Args:
            config: pwnagotchi configuration dict
            logger: optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = config
        self.stats = ChannelStatistics()

        # Configuration options
        self.extra_channels = config.get("main", {}).get("extra_channels", 15)
        self.restrict_channels = config.get("main", {}).get("restrict_channels", None)
        self.reset_history = config.get("main", {}).get("reset_history", True)

    def select_channels(self, agent, access_points):
        """
        Select next set of channels to scan based on current APs and unscanned channels.

        Returns list of channels to scan in next epoch.
        """
        try:
            # Update active channels from current scan
            self.stats.update_active_channels(access_points)

            # Build next channel list: active + extra unscanned
            next_channels = self.stats.active_channels.copy()

            # Add random unscanned channels for exploration
            n_extra = self.extra_channels
            if len(self.stats.unscanned_channels) == 0:
                self._repopulate_unscanned_channels(agent)

            for _ in range(n_extra):
                if len(self.stats.unscanned_channels):
                    ch = random.choice(list(self.stats.unscanned_channels))
                    self.stats.unscanned_channels.remove(ch)
                    next_channels.append(ch)

            # Update agent config
            if hasattr(agent, "_config"):
                agent._config["personality"]["channels"] = next_channels

            self.logger.info(
                f"Active: {self.stats.active_channels}, "
                f"Next: {next_channels}, "
                f"Unscanned: {len(self.stats.unscanned_channels)}"
            )

            return next_channels

        except Exception as e:
            self.logger.error(f"Error selecting channels: {e}")
            return self.stats.active_channels

    def _repopulate_unscanned_channels(self, agent):
        """Repopulate unscanned channel list from config or agent."""
        try:
            # Try restrict_channels first
            if self.restrict_channels:
                self.logger.info("Repopulating from restrict_channels")
                self.stats.unscanned_channels = self.restrict_channels.copy()
            # Try agent's allowed channels
            elif hasattr(agent, "_allowed_channels"):
                self.logger.info(f"Repopulating from allowed: {agent._allowed_channels}")
                self.stats.unscanned_channels = agent._allowed_channels.copy()
            # Try agent's supported channels
            elif hasattr(agent, "_supported_channels"):
                self.logger.info("Repopulating from supported")
                self.stats.unscanned_channels = agent._supported_channels.copy()
            # Fall back to all channels for interface
            else:
                self.logger.info("Repopulating from interface channels")
                iface = self.config.get("main", {}).get("iface", "wlan0")
                self.stats.unscanned_channels = pwnagotchi.utils.iface_channels(iface)

        except Exception as e:
            self.logger.warning(f"Error repopulating unscanned channels: {e}")

    def on_wifi_update(self, agent, access_points):
        """Called when agent updates its AP list."""
        self.stats.update_active_channels(access_points)

    def on_association(self, agent, access_point):
        """Called when sending association frame."""
        self.stats.record_interaction("Associations", access_point.get("channel", -1))
        self.stats.mark_ap_seen(access_point, "assoc")

    def on_deauthentication(self, agent, access_point, client_station):
        """Called when sending deauth."""
        self.stats.record_interaction("Deauths", access_point.get("channel", -1))
        self.stats.mark_ap_seen(access_point, "deauth")

    def on_handshake(self, agent, filename, access_point, client_station):
        """Called when handshake is captured."""
        self.stats.record_interaction("Handshakes", access_point.get("channel", -1))
        self.stats.mark_ap_seen(access_point, "handshake")

    def on_bcap_wifi_ap_new(self, agent, event):
        """Called when bettercap detects new AP."""
        try:
            ap = event.get("data", {})
            self.stats.mark_ap_seen(ap)
        except Exception as e:
            self.logger.debug(f"Error on_bcap_wifi_ap_new: {e}")

    def on_bcap_wifi_ap_lost(self, agent, event):
        """Called when bettercap loses AP."""
        try:
            ap = event.get("data", {})
            self.stats.record_ap_lost(ap)
        except Exception as e:
            self.logger.debug(f"Error on_bcap_wifi_ap_lost: {e}")

    def get_stats(self):
        """Get current strategy statistics."""
        return self.stats.get_stats()
