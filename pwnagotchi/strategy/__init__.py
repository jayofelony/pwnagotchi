"""Pwnagotchi channel selection strategy - core to agent behavior.

This module replaces the removed RL-based AI with intelligent heuristics:
- Track active channels (have APs) and prioritize them
- Explore unscanned channels randomly
- Maintain statistics per channel
- Guide agent behavior through channel selection

Originally extracted from auto-tune plugin to make it core functionality.
"""

import logging
from .channels import ChannelStrategy
from .statistics import ChannelStatistics


class Strategy:
    """
    Main strategy facade.

    Integrates channel selection with agent lifecycle and event handling.
    """

    def __init__(self, config, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.channels = ChannelStrategy(config, logger=self.logger)
        self.config = config

    def start(self):
        """Initialize strategy when agent starts."""
        self.logger.info("Channel selection strategy initialized")

    def select_next_channels(self, agent, access_points):
        """
        Select channels for next epoch.

        Called after WiFi scan completes. Returns list of channels to scan.
        """
        return self.channels.select_channels(agent, access_points)

    # Event handlers - connect to agent event system
    def on_wifi_update(self, agent, access_points):
        """WiFi list updated."""
        self.channels.on_wifi_update(agent, access_points)

    def on_association(self, agent, access_point):
        """Association sent."""
        self.channels.on_association(agent, access_point)

    def on_deauthentication(self, agent, access_point, client_station):
        """Deauthentication sent."""
        self.channels.on_deauthentication(agent, access_point, client_station)

    def on_handshake(self, agent, filename, access_point, client_station):
        """Handshake captured."""
        self.channels.on_handshake(agent, filename, access_point, client_station)

    def on_bcap_wifi_ap_new(self, agent, event):
        """Bettercap: new AP detected."""
        self.channels.on_bcap_wifi_ap_new(agent, event)

    def on_bcap_wifi_ap_lost(self, agent, event):
        """Bettercap: AP lost."""
        self.channels.on_bcap_wifi_ap_lost(agent, event)

    def get_stats(self):
        """Get current strategy statistics."""
        return self.channels.get_stats()


__all__ = ["Strategy", "ChannelStrategy", "ChannelStatistics"]
