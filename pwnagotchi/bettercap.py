import json
import logging
import requests
import websockets
import asyncio
import random

from requests.auth import HTTPBasicAuth
from time import sleep

requests.adapters.DEFAULT_RETRIES = 5  # increase retries number

ping_timeout = 90
ping_interval = 60

max_sleep = 2.0


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

    def session(self):
        r = requests.get("%s/session" % self.url, auth=self.auth)
        return decode(r)

    async def start_websocket(self, consumer):
        s = "%s/events" % self.websocket

        # More modern version of the approach below
        # logging.info("Creating new websocket...")
        # async for ws in websockets.connect(s):
        #     try:
        #         async for msg in ws:
        #             try:
        #                 await consumer(msg)
        #             except Exception as ex:
        #                     logging.debug("Error while parsing event (%s)", ex)
        #     except websockets.exceptions.ConnectionClosedError:
        #         sleep_time = max_sleep*random.random()
        #         logger.warning('Retrying websocket connection in {} sec'.format(sleep_time))
        #         await asyncio.sleep(sleep_time)
        #         continue

        # restarted every time the connection fails
        while True:
            logging.info("creating new websocket...")
            try:
                async with websockets.connect(s, ping_interval=ping_interval, ping_timeout=ping_timeout) as ws:
                    # listener loop
                    while True:
                        try:
                            async for msg in ws:
                                try:
                                    await consumer(msg)
                                except Exception as ex:
                                    logging.debug("error while parsing event (%s)", ex)
                        except websockets.exceptions.ConnectionClosedError:
                            try:
                                pong = await ws.ping()
                                await asyncio.wait_for(pong, timeout=ping_timeout)
                                logging.warning('ping OK, keeping connection alive...')
                                continue
                            except:
                                sleep_time = max_sleep*random.random()
                                logging.warning('ping error - retrying connection in {} sec'.format(sleep_time))
                                await asyncio.sleep(sleep_time)
                                break
            except ConnectionRefusedError:
                sleep_time = max_sleep*random.random()
                logging.warning('nobody seems to listen to the bettercap endpoint...')
                logging.warning('retrying connection in {} sec'.format(sleep_time))
                await asyncio.sleep(sleep_time)
                continue

    def run(self, command, verbose_errors=True):
        for _ in range(0, 2):
            try:
                r = requests.post("%s/session" % self.url, auth=self.auth, json={'cmd': command})
            except requests.exceptions.ConnectionError as e:
                sleep_time = max_sleep*random.random()
                logging.exception("Request connection error (%s) while running command (%s)", e, command)
                logging.warning('Retrying run in {} sec'.format(sleep_time))
                sleep(sleep_time)
            else:
                break

        return decode(r, verbose_errors=verbose_errors)
