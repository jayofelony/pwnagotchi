import logging
import requests
import websockets
import asyncio
import random

from requests.auth import HTTPBasicAuth
from time import sleep

import pwnagotchi

requests.adapters.DEFAULT_RETRIES = 5  # increase retries number

ping_timeout = 180
ping_interval = 15
max_queue = 10000

min_sleep = 0.5
max_sleep = 5.0

# FIX B2: constants for run() retry logic
MAX_RETRIES = 10
BACKOFF_BASE = 2.0

# FIX B3: consecutive websocket OSError failures before triggering restart
MAX_WS_ERRORS = 5


def decode(r, verbose_errors=True):
    try:
        return r.json()
    except Exception as e:
        if r.status_code == 200:
            logging.error("error while decoding json: error='%s' resp='%s'" % (e, r.text))
        else:
            err = "error %d: %s" % (r.status_code, r.text.strip())
            if verbose_errors:
                logging.info(err)
            raise Exception(err)
        return r.text


class Client(object):
    def __init__(self, hostname='localhost', scheme='http', port=8081, username='user', password='pass'):
        self.hostname = hostname
        self.scheme = scheme
        self.port = port
        self.username = username
        self.password = password
        self.url = "%s://%s:%d/api" % (scheme, hostname, port)
        self.websocket = "ws://%s:%s@%s:%d/api" % (username, password, hostname, port)
        self.auth = HTTPBasicAuth(username, password)

    # session takes optional argument to pull a sub-dictionary
    #  ex.: "session/wifi", "session/ble"
    def session(self, sess="session"):
        r = requests.get("%s/%s" % (self.url, sess), auth=self.auth)
        return decode(r)

    async def start_websocket(self, consumer):
        s = "%s/events" % self.websocket

        # FIX B3: track consecutive OSError failures before escalating to restart
        oserror_count = 0

        # restarted every time the connection fails
        while True:
            logging.info("[bettercap] creating new websocket...")
            try:
                async with websockets.connect(s, ping_interval=ping_interval, ping_timeout=ping_timeout,
                                              max_queue=max_queue) as ws:
                    # reset error counter on successful connect
                    oserror_count = 0
                    # listener loop
                    while True:
                        try:
                            async for msg in ws:
                                try:
                                    await consumer(msg)
                                except Exception as ex:
                                    logging.debug("[bettercap] error while parsing event (%s)", ex)
                        except websockets.ConnectionClosedError:
                            try:
                                pong = await ws.ping()
                                await asyncio.wait_for(pong, timeout=ping_timeout)
                                logging.warning('[bettercap] ping OK, keeping connection alive...')
                                continue
                            except Exception:
                                # FIX B4: replaced bare except with except Exception
                                sleep_time = min_sleep + max_sleep * random.random()
                                logging.warning('[bettercap] ping error - retrying connection in {} sec'.format(sleep_time))
                                await asyncio.sleep(sleep_time)
                                break
            except ConnectionRefusedError:
                sleep_time = min_sleep + max_sleep * random.random()
                logging.warning('[bettercap] nobody seems to be listening at the bettercap endpoint...')
                logging.warning('[bettercap] retrying connection in {} sec'.format(sleep_time))
                await asyncio.sleep(sleep_time)
                continue
            except OSError:
                # FIX B3: count consecutive failures, only restart after MAX_WS_ERRORS
                oserror_count += 1
                logging.warning('[bettercap] connection to the bettercap endpoint failed (failure %d/%d)...',
                                oserror_count, MAX_WS_ERRORS)
                if oserror_count >= MAX_WS_ERRORS:
                    logging.error('[bettercap] too many consecutive websocket failures, restarting...')
                    pwnagotchi.restart("AUTO")
                else:
                    sleep_time = min_sleep + max_sleep * random.random()
                    logging.warning('[bettercap] retrying websocket in %.1fs', sleep_time)
                    await asyncio.sleep(sleep_time)
                    continue

    def run(self, command, verbose_errors=True):
        # FIX B2: replace infinite while True loop with bounded retry + exponential backoff
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.post("%s/session" % self.url, auth=self.auth, json={'cmd': command})
                return decode(r, verbose_errors=verbose_errors)
            except requests.exceptions.ConnectionError:
                sleep_time = min(BACKOFF_BASE ** attempt, 30)
                logging.warning(
                    "[bettercap] can't run my request... connection failed (attempt %d/%d), retrying in %.1fs",
                    attempt + 1, MAX_RETRIES, sleep_time)
                sleep(sleep_time)

        logging.critical('[bettercap] unreachable after %d attempts, restarting...', MAX_RETRIES)
        pwnagotchi.restart('AUTO')
