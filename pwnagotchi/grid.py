import subprocess
import requests
import logging

import pwnagotchi

# pwngrid-peer is running on port 8666
API_ADDRESS = "http://127.0.0.1:8666/api/v1"


def is_connected():
    try:
        # check DNS
        host = 'https://api.opwngrid.xyz/api/v1/uptime'
        headers = {'user-agent': f'pwnagotchi/{pwnagotchi.__version__}'}
        r = requests.get(host, headers=headers, timeout=(30.0, 60.0))
        if r.json().get('isUp'):
            return True
    except Exception:
        pass
    return False


def call(path, obj=None):
    url = '%s%s' % (API_ADDRESS, path)
    if obj is None:
        r = requests.get(url, headers=None, timeout=(30.0, 60.0))
    elif isinstance(obj, dict):
        r = requests.post(url, headers=None, json=obj, timeout=(30.0, 60.0))
    else:
        r = requests.post(url, headers=None, data=obj, timeout=(30.0, 60.0))

    if r.status_code != 200:
        raise Exception("(status %d) %s" % (r.status_code, r.text))
    return r.json()


def advertise(enabled=True):
    # FIX B1: parentheses around ternary ensure correct string interpolation
    return call("/mesh/%s" % ('true' if enabled else 'false'))


def set_advertisement_data(data):
    return call("/mesh/data", obj=data)


def get_advertisement_data():
    return call("/mesh/data")


def memory():
    return call("/mesh/memory")


def peers():
    return call("/mesh/peers")


def closest_peer():
    all = peers()
    return all[0] if len(all) else None


def update_data(last_session):
    # REMOVED: brain.json loading - file is never created by the noai fork
    # REMOVED: AI session fields (train_epochs, avg_reward, min_reward, max_reward) - always zero without AI
    enabled = [name for name, options in pwnagotchi.config['main']['plugins'].items() if
               'enabled' in options and options['enabled']]
    language = pwnagotchi.config['main']['lang']

    data = {
        'ai': "No AI!",
        'session': {
            'duration': last_session.duration,
            'epochs': last_session.epochs,
            'deauthed': last_session.deauthed,
            'associated': last_session.associated,
            'handshakes': last_session.handshakes,
            'peers': last_session.peers,
        },
        'uname': subprocess.getoutput("uname -a"),
        'version': pwnagotchi.__version__,
        'build': "Pwnagotchi by Jayofelony",
        'plugins': enabled,
        'language': language,
        'bettercap': subprocess.getoutput("bettercap -version"),
        'opwngrid': subprocess.getoutput("pwngrid -version")
    }

    logging.debug("updating grid data: %s" % data)

    call("/data", data)


def report_ap(essid, bssid):
    try:
        call("/report/ap", {
            'essid': essid,
            'bssid': bssid,
        })
        return True
    except Exception as e:
        logging.exception("error while reporting ap %s(%s)" % (essid, bssid))

    return False


def inbox(page=1, with_pager=False):
    obj = call("/inbox?p=%d" % page)
    return obj["messages"] if not with_pager else obj


def inbox_message(id):
    return call("/inbox/%d" % int(id))


def mark_message(id, mark):
    return call("/inbox/%d/%s" % (int(id), str(mark)))


def send_message(to, message):
    return call("/unit/%s/inbox" % to, message.encode('utf-8'))
