import time
import threading
import logging

import pwnagotchi
import pwnagotchi.utils as utils

# REMOVED: from pwnagotchi.ai.reward import RewardFunction
# The RewardFunction computed a reward score that was logged but never consumed
# by any decision-making logic after AI removal. Removed to eliminate dead CPU work.


class Epoch(object):
    def __init__(self, config):
        self.epoch = 0
        self.config = config
        # how many consecutive epochs with no activity
        self.inactive_for = 0
        # how many consecutive epochs with activity
        self.active_for = 0
        # number of epochs with no visible access points
        self.blind_for = 0
        # number of epochs in sad state
        self.sad_for = 0
        # number of epochs in bored state
        self.bored_for = 0
        # did deauth in this epoch in the current channel?
        self.did_deauth = False
        # number of deauths in this epoch
        self.num_deauths = 0
        # did associate in this epoch in the current channel?
        self.did_associate = False
        # number of associations in this epoch
        self.num_assocs = 0
        # number of assocs or deauths missed
        self.num_missed = 0
        # did get any handshake in this epoch?
        self.did_handshakes = False
        # number of handshakes captured in this epoch
        self.num_shakes = 0
        # number of channels hops
        self.num_hops = 0
        # number of seconds sleeping
        self.num_slept = 0
        # number of peers seen during this epoch
        self.num_peers = 0
        # cumulative bond factor
        self.tot_bond_factor = 0.0
        # average bond factor
        self.avg_bond_factor = 0.0
        # any activity at all during this epoch?
        self.any_activity = False
        # when the current epoch started
        self.epoch_started = time.time()
        # last epoch duration
        self.epoch_duration = 0
        # https://www.metageek.com/training/resources/why-channels-1-6-11.html
        self.non_overlapping_channels = {1: 0, 6: 0, 11: 0}
        # REMOVED: observation histogram vectors (_observation, _observation_ready)
        # These were 14-element float arrays per channel computed every observe() call,
        # feeding a neural network that no longer exists.
        self._epoch_data = {}
        self._epoch_data_ready = threading.Event()
        # REMOVED: self._reward = RewardFunction()

    def wait_for_epoch_data(self, with_observation=True, timeout=None):
        # REMOVED: observation wait (was already commented out in original)
        self._epoch_data_ready.wait(timeout)
        self._epoch_data_ready.clear()
        # REMOVED: merging histogram observation vectors - just return epoch data
        return self._epoch_data

    def data(self):
        return self._epoch_data

    def observe(self, aps, peers):
        # REMOVED: histogram computation (aps_histogram, sta_histogram, peers_histogram)
        # These were normalised channel observation vectors for the neural network.
        # Kept: the non-histogram peer/AP accounting the mood system depends on.
        num_aps = len(aps)
        if num_aps == 0:
            self.blind_for += 1
        else:
            self.blind_for = 0

        bond_unit_scale = self.config['personality']['bond_encounters_factor']

        self.num_peers = len(peers)
        num_peers = self.num_peers + 1e-10  # avoid division by 0

        self.tot_bond_factor = sum((peer.encounters for peer in peers)) / bond_unit_scale
        self.avg_bond_factor = self.tot_bond_factor / num_peers

        # REMOVED: per-channel histogram normalisation loops
        # REMOVED: self._observation update and self._observation_ready.set()

    def track(self, deauth=False, assoc=False, handshake=False, hop=False, sleep=False, miss=False, inc=1):
        if deauth:
            self.num_deauths += inc
            self.did_deauth = True
            self.any_activity = True

        if assoc:
            self.num_assocs += inc
            self.did_associate = True
            self.any_activity = True

        if miss:
            self.num_missed += inc

        if hop:
            self.num_hops += inc
            # these two are used in order to determine the sleep time in seconds
            # before switching to a new channel ... if nothing happened so far
            # during this epoch on the current channel, we will sleep less
            self.did_deauth = False
            self.did_associate = False

        if handshake:
            self.num_shakes += inc
            self.did_handshakes = True

        if sleep:
            self.num_slept += inc

    def next(self):
        if self.any_activity is False and self.did_handshakes is False:
            self.inactive_for += 1
            self.active_for = 0
        else:
            self.active_for += 1
            self.inactive_for = 0
            self.sad_for = 0
            self.bored_for = 0

        if self.inactive_for >= self.config['personality']['sad_num_epochs']:
            # sad > bored; cant be sad and bored
            self.bored_for = 0
            self.sad_for += 1
        elif self.inactive_for >= self.config['personality']['bored_num_epochs']:
            # sad_treshhold > inactive > bored_treshhold; cant be sad and bored
            self.sad_for = 0
            self.bored_for += 1
        else:
            self.sad_for = 0
            self.bored_for = 0

        now = time.time()
        cpu = pwnagotchi.cpu_load("epoch")
        mem = pwnagotchi.mem_usage()
        temp = pwnagotchi.temperature()

        self.epoch_duration = now - self.epoch_started

        # cache the state of this epoch for other threads to read
        self._epoch_data = {
            'duration_secs': self.epoch_duration,
            'slept_for_secs': self.num_slept,
            'blind_for_epochs': self.blind_for,
            'inactive_for_epochs': self.inactive_for,
            'active_for_epochs': self.active_for,
            'sad_for_epochs': self.sad_for,
            'bored_for_epochs': self.bored_for,
            'missed_interactions': self.num_missed,
            'num_hops': self.num_hops,
            'num_peers': self.num_peers,
            'tot_bond': self.tot_bond_factor,
            'avg_bond': self.avg_bond_factor,
            'num_deauths': self.num_deauths,
            'num_associations': self.num_assocs,
            'num_handshakes': self.num_shakes,
            'cpu_load': cpu,
            'mem_usage': mem,
            'temperature': temp
        }

        # REMOVED: self._epoch_data['reward'] = self._reward(self.epoch + 1, self._epoch_data)

        self._epoch_data_ready.set()

        logging.info("[epoch %d] duration=%s slept_for=%s blind=%d sad=%d bored=%d inactive=%d active=%d peers=%d tot_bond=%.2f "
                     "avg_bond=%.2f hops=%d missed=%d deauths=%d assocs=%d handshakes=%d cpu=%d%% mem=%d%% "
                     "temperature=%dC" % (
                         self.epoch,
                         utils.secs_to_hhmmss(self.epoch_duration),
                         utils.secs_to_hhmmss(self.num_slept),
                         self.blind_for,
                         self.sad_for,
                         self.bored_for,
                         self.inactive_for,
                         self.active_for,
                         self.num_peers,
                         self.tot_bond_factor,
                         self.avg_bond_factor,
                         self.num_hops,
                         self.num_missed,
                         self.num_deauths,
                         self.num_assocs,
                         self.num_shakes,
                         cpu * 100,
                         mem * 100,
                         temp))

        self.epoch += 1
        self.epoch_started = now
        self.did_deauth = False
        self.num_deauths = 0
        self.num_peers = 0
        self.tot_bond_factor = 0.0
        self.avg_bond_factor = 0.0
        self.did_associate = False
        self.num_assocs = 0
        self.num_missed = 0
        self.did_handshakes = False
        self.num_shakes = 0
        self.num_hops = 0
        self.num_slept = 0
        self.any_activity = False
