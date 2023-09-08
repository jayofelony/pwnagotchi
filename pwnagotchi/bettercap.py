import logging
import requests
import websockets
import backoff

from requests.auth import HTTPBasicAuth
import asyncio  # Add asyncio for async functionality
from time import sleep  # Add sleep function


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

    @backoff.on_exception(backoff.expo, requests.exceptions.ConnectionError, max_tries=10)
    async def start_websocket(self, consumer):
        s = "%s/events" % self.websocket
        while True:
            try:
                async with websockets.connect(s, ping_interval=60, ping_timeout=90) as ws:
                    async for msg in ws:
                        try:
                            await consumer(msg)
                        except Exception as ex:
                            logging.debug("Error while parsing event (%s)", ex)
            except websockets.exceptions.ConnectionClosedError:
                logging.debug("Lost websocket connection. Reconnecting...")
                await asyncio.sleep(1)  # Sleep for x seconds before reconnecting
            except websockets.exceptions.WebSocketException as wex:
                logging.debug("Websocket exception (%s)", wex)
                await asyncio.sleep(1)  # Sleep for x seconds before reconnecting
            except Exception as e:
                logging.exception("Other error while opening websocket (%s) with parameter %s", e, s)
                await asyncio.sleep(1)  # Sleep for x seconds before reconnecting

    @backoff.on_exception(backoff.expo, requests.exceptions.ConnectionError, max_tries=10)
    def run(self, command, verbose_errors=True):
        for _ in range(0, 2):
            try:
                r = requests.post("%s/session" % self.url, auth=self.auth, json={'cmd': command})
            except requests.exceptions.ConnectionError as e:
                logging.exception("Request connection error (%s) while running command (%s)", e, command)
                sleep(1)  # Sleep for 1-s before trying a second time
            else:
                break

        return decode(r, verbose_errors=verbose_errors)
