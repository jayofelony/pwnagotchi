import json
import logging
import requests
import websockets

from requests.auth import HTTPBasicAuth
from time import sleep

requests.adapters.DEFAULT_RETRIES = 5 # increase retries number


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
        async with websockets.connect(s, ping_interval=60, ping_timeout=90) as ws:
            while True:
                try:
                    async for msg in ws:
                        try:
                            await consumer(msg)
                        except Exception as ex:
                                logging.debug("Error while parsing event (%s)", ex)
                except websockets.ConnectionClosedError:
                    logging.error("Lost websocket connection. Reconnecting...")
                    continue
                except websockets.WebSocketException as wex:
                    logging.error("Websocket exception (%s)", wex)
                    continue
                except OSError as e:
                    logging.error("Websocket OSError exception (%s) with parameter %s", e, s)
                    continue
                except Exception as e:
                    logging.error("Other exception (%s) with parameter %s", e, s)
                    continue

    def run(self, command, verbose_errors=True):
        for _ in range(0,2):
            try:
                r = requests.post("%s/session" % self.url, auth=self.auth, json={'cmd': command})
            except requests.exceptions.ConnectionError as e:
                logging.exception("Request connection error (%s) while running command (%s)", e, command)
                sleep(1) # Sleep for 1-s before trying a second time
            else:
                break

        return decode(r, verbose_errors=verbose_errors)
