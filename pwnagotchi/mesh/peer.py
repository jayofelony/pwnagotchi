import time
import logging
import datetime

import pwnagotchi.ui.faces as faces


def parse_rfc3339(dt):
    if not isinstance(dt, str) or dt == "0001-01-01T00:00:00Z":
        return datetime.datetime.now()
    return datetime.datetime.strptime(dt.split('.')[0], "%Y-%m-%dT%H:%M:%S")


class Peer(object):
    def __init__(self, obj):
        now = time.time()
        just_met = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        try:
            self.first_met = parse_rfc3339(obj.get('met_at', just_met))
            self.first_seen = parse_rfc3339(obj.get('detected_at', just_met))
            self.prev_seen = parse_rfc3339(obj.get('prev_seen_at', just_met))
        except Exception as e:
            logging.warning("error while parsing peer timestamps: %s" % e)
            logging.debug(e, exc_info=True)
            self.first_met = just_met
            self.first_seen = just_met
            self.prev_seen = just_met

        self.last_seen = now  # should be seen_at
        self.encounters = obj.get('encounters', 0)
        self.session_id = obj.get('session_id', '')
        self.last_channel = obj.get('channel', 1)
        try:
            self.rssi = int(obj.get('rssi', 0))
        except (TypeError, ValueError):
            self.rssi = 0
        # the advertisement comes straight off the mesh as untrusted JSON: a
        # peer running buggy/old firmware can send a null advertisement, or
        # null/wrong-typed fields inside it. Everything downstream (the UI
        # friend face/name, pwnd counters) assumed well-formed values, so a
        # single malformed advert used to crash _update_peers on every
        # _fetch_stats pass with "expected string or bytes".
        adv = obj.get('advertisement')
        self.adv = adv if isinstance(adv, dict) else {}

    def _adv_str(self, key, default):
        val = self.adv.get(key, default)
        return val if isinstance(val, str) else default

    def _adv_int(self, key, default=0):
        try:
            return int(self.adv.get(key, default))
        except (TypeError, ValueError):
            return default

    def update(self, new):
        if self.name() != new.name():
            logging.info("peer %s changed name: %s -> %s" % (self.full_name(), self.name(), new.name()))

        if self.session_id != new.session_id:
            logging.info("peer %s changed session id: %s -> %s" % (self.full_name(), self.session_id, new.session_id))

        self.adv = new.adv
        self.rssi = new.rssi
        self.session_id = new.session_id
        self.last_seen = time.time()
        self.prev_seen = new.prev_seen
        self.first_met = new.first_met
        self.encounters = new.encounters

    def inactive_for(self):
        return time.time() - self.last_seen

    def first_encounter(self):
        return self.encounters == 1

    def is_good_friend(self, config):
        return self.encounters >= config['personality']['bond_encounters_factor']

    def face(self):
        return self._adv_str('face', faces.FRIEND)

    def name(self):
        return self._adv_str('name', '???')

    def identity(self):
        return self._adv_str('identity', '???')

    def full_name(self):
        return "%s@%s" % (self.name(), self.identity())

    def version(self):
        return self._adv_str('version', '1.0.0a')

    def pwnd_run(self):
        return self._adv_int('pwnd_run', 0)

    def pwnd_total(self):
        return self._adv_int('pwnd_tot', 0)

    def uptime(self):
        return self.adv.get('uptime', 0)

    def epoch(self):
        return self.adv.get('epoch', 0)

    def is_closer(self, other):
        return self.rssi > other.rssi
