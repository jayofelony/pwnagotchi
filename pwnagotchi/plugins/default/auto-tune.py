import logging
import random
import time
import html

import pwnagotchi.plugins as plugins
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.utils
from pwnagotchi.utils import save_config, merge_config

from flask import abort
from flask import render_template_string


class auto_tune(plugins.Plugin):
    __author__ = 'Sniffleupagus'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'A plugin that adjust AUTO mode parameters'

    # Chistos - should really be an object, but I'm being lazy
    #
    # Channel histograms maintained per session
    # - stat = string : name of the statistic. It is the chart label for this stat
    # - channel = the channel where the stat happened
    # - count (default +1) - how much to add to the count for this chisto[stat][channel]
    #           for example, on_bcap_wifi_ap_new, use the default value, but on_bcap_wifi_ap_lost use -1
    #           to count current APs per channel
    def __init__(self):
        self._histogram = {'loops': 0}  # count APs per epoch

        self._chistos = {'_all_actions': {-1: 0}}  # arbitrary session stats per channel

        # plugin data
        self._unscanned_channels = []  # temporary set of channels to pull "extra_channels" from
        self._active_channels = []  # list of channels with APs found in last scan
        self._known_aps = {}  # dict of all APs by normalized name+mac
        self._known_clients = {}  # dict of all clients by normalized APmac+STAmac (many clients to not have names)
        self._agent = None

        self.descriptions = {  # descriptions of personality variables displayed in webui
            "advertise": "enable/disable advertising to mesh peers",
            "deauth": "enable/disable deauthentication attacks",
            "associate": "enable/disable association attacks",
            "throttle_a": "delay after an associate. Some delay seems to reduce nexmon crashes",
            "throttle_d": "delay after a deauthenticate. Delay helps reduce nexmon crashes",
            "assoc_prob": "probability of trying an associate attack. Set lower to spread out interaction instead of hitting all APs every time until max_interactions",
            "deauth_prob": "probability of trying a deauth. will spread the 'max_interactions' over a longer time",
            "min_rssi": "ignore APs with signal weaker than this value. lower values will attack more distant APs",
            "recon_time": "duration of the bettercap channel hopping scan phase, to discover APs before sending attacks",
            "min_recon_time": "time spent on each occupied channel per epoch, sending attacks and waiting for handshakes. and epoch is recon_time + #channels * min_recon_time seconds long",
            "ap_ttl": "APs that have not been seen since this many seconds are ignored. Shorten this if you are moving, to not try to scan APs that are no longer in range.",
            "sta_ttl": "Clients older than this will ignored",
        }
        self.options = dict()

    def incrementChisto(self, stat, channel, count=1):
        if stat not in self._chistos:
            self._chistos[stat] = {-1: 0}

        if channel not in self._chistos[stat]:
            self._chistos[stat][channel] = count
        else:
            self._chistos[stat][channel] += count

        # count all actions per channel, to get a full channel list
        if channel not in self._chistos['_all_actions']:
            self._chistos['_all_actions'][channel] = 1
        else:
            self._chistos['_all_actions'][channel] += 1

        # track total on channel -1
        self._chistos[stat][-1] += count
        self._chistos['_all_actions'][-1] += 1

    def showChistos(self, stats=None, sort_key='_all_actions'):  # stats is list of specific to show, else all
        ret = ""
        if not stats:
            stats = self._chistos.keys()
            logging.debug("Using keys: %s" % repr(stats))
        try:
            if sort_key in self._chistos:
                channel_order = sorted(self._chistos[sort_key].items(), key=lambda x: x[1], reverse=True)
            else:
                channel_order = self._agent._supported_channels
            logging.debug("Channel Order: %s" % repr(channel_order))

            ret += "<h2>Channel Statistics</h2>\n"
            ret += "<table border=1 cellspacing=4 cellpadding=4>\n"
            ret += "<tr><th>Channel</th>"
            for (ch, count) in channel_order:
                if ch == -1:
                    ret += "<th>All</th>"
                else:
                    ret += "<th>%d</th>" % ch
            ret += "</tr>\n"

            if not stats:
                ret += "</table>\n"
                return ret

            for s in stats:
                if s == sort_key:
                    ret += "<tr><th>%s</th>" % s
                else:
                    ret += "<tr><td>%s</td>" % s

                if s not in self._chistos:
                    ret += "<td colspan=%s>No data</td>" % len(channel_order)
                else:
                    chisto = self._chistos[s]
                    for (ch, dummy) in channel_order:
                        if ch in chisto:
                            ret += "<td align=right>%s</td>" % chisto[ch]
                        else:
                            ret += "<td align=center>-</td>"
                ret += "</tr>\n"
            ret += "</table>\n"

            return ret
        except Exception as e:
            eret = "<h2>Channel Statistics Error</h2>\n"
            eret += "<h3>Progress:</h3>\n<pre>%s</pre>\n<h3>Exception dump:</h3>\n<pre>%s</pre>\n" % (
            html.escape(ret), html.escape(repr(e)))
            logging.exception(e)

    def normalize(self, name):
        """
        Only allow alpha/nums
        """
        if not name or name == '':
            return 'EMPTY'
        if name == '<hidden>':
            return 'HIDDEN'
        return str.lower(''.join(c for c in name if c.isalnum()))


    def showEditForm(self, request):
        path = request.path if request.path.endswith("/update") else "%s/update" % request.path

        ret = '<form method=post action="%s">' % path
        ret += '<input id="csrf_token" name="csrf_token" type="hidden" value="{{ csrf_token() }}">'

        form_data = request.values.items()

        for secname, sec in [["Personality", self._agent._config['personality']],
                             ["AUTO Tune", self._agent._config['main']['plugins']['auto-tune']]]:
            ret += '<h2>%s Variables</h2>' % secname
            ret += '<table>\n'
            ret += '<tr align=left><th>Parameter</th><th>Value</th><th>Description</th></tr>\n'

            for p in sorted(sec):
                if type(sec[p]) in [int, str, float, bool]:
                    cls = type(sec[p]).__name__
                    iname = "newval,%s,%s,%s" % (sec[p], p, cls)
                    ret += "<tr align=left>"
                    if cls == "bool":
                        ret += '<th>%s</th><td style="white-space:nowrap; vertical-align:top;">' % (p)
                        checked = " checked" if sec[p] else ""
                        ret += '<input type=radio id="%s" name="%s" value="%s" %s>&nbsp;True<br>' % (
                        iname, iname, "True", checked)
                        checked = " checked" if not sec[p] else ""
                        ret += '<input type=radio id="%s" name="%s" value="%s" %s>&nbsp;False' % (
                        iname, iname, "False", checked)
                        ret += "</td>"
                    else:
                        ret += '<th>%s</th>' % p
                        ret += '<td><input type=text id="%s" name="%s" size="5" value="%s"></td>' % (
                        iname, iname, sec[p])
                        # ret += '<tr><th>%s</th>' % ("" if p not in self.descriptions else self.descriptions[p])
                    if p in self.descriptions:
                        ret += "<td>%s</td>" % self.descriptions[p]
                    ret += '</tr>\n'
                else:
                    ret += '<tr align=left><th>%s</th><td>%s</td><td><i>uneditable</i></tr>' % (p, repr(sec[p]))
            ret += "</table>"
        ret += '<input type=submit name=submit value="update"></form><p>'
        return ret

    def showHistogram(self):
        ret = ""
        histo = self._histogram
        nloops = int(histo["loops"])
        if nloops > 0:
            ret += "<h2>APs per Channel over %s epochs</h2>" % nloops
            ret += "<table border=1 spacing=4 cellspacing=1>"
            chans = "<tr><th>Channel</th>"
            totals = "<tr><th>APs seen</th>"
            vals = "<tr><th>Avg APs/epoch</th>"

            for (ch, count) in sorted(histo.items(), key=lambda x: x[1], reverse=True):
                if ch == "loops":
                    pass
                else:
                    weight = float(count) / nloops
                    # ret +="<tr><th>%d</th><td>%0.2f</td>" % (ch, count)
                    chans += "<th>%s</th>" % ch
                    totals += "<td align=right>%d</td>" % count
                    vals += "<td align=right>%0.1f</td>" % weight
            chans += "</tr>"
            totals += "</tr>"
            vals += "</tr>"
            ret += chans + totals + vals
            ret += "</table>"
        else:
            ret += "<h2>No channel data collected yet</h2>"

        return ret

    def showInteractions(self):
        ret = ""
        numHidden = 0
        numVisible = 0
        if self._agent:
            now = time.time()
            ret += "<h2>Interactions per endpoint</h2>"
            ret += "<p><b>Encounters</b> is how many different times this AP has been seen, then not seen, then seen again. Interactions should be the sum of assoc and deauth attacks. All are per session stats. <b>Age</b> is seconds since AP was last seen by the plugin.</p>"
            ret += "<table border=1 spacing=4 cellspacing=4 cellpadding=4>"
            ret += "<tr><th>Hostname</th><th>MAC</th><th>Channel</th><th>Age</th><th>RSSI</th><th>Encounters</th><th>Associates</th><th>Deauths</th><th>Handshakes</th><th>Interactions</th></tr>"
            for (id, ap) in sorted(self._known_aps.items(), key=lambda x: x[1]['AT_lastseen'], reverse=True):
                lmac = ap['mac'].lower()
                if ap['hostname'] == "<hidden>" and not self.options['show_hidden']:
                    logging.debug("Skipping %s '%s'" % (ap['hostname'], lmac))
                    numHidden += 1
                    continue  # skip hidden APs
                elif ap['hostname'] == '' and not self.options['show_hidden']:
                    logging.debug("Skipping no-name %s '%s'" % (ap['hostname'], lmac))
                    numHidden += 1
                    continue  # skip hidden APs
                elif ap['hostname'] is None and not self.options['show_hidden']:
                    logging.debug("Skipping None %s '%s'" % (ap['hostname'], lmac))
                    numHidden += 1
                    continue  # skip hidden APs
                else:
                    numVisible += 1
                    logging.debug("Not skipping '%s'" % ap['hostname'])
                if ap['AT_visible']:
                    ret += "<tr><td>%s</td>" % html.escape(ap['hostname'])
                else:
                    ret += "<tr><td><i>%s</i></td>" % html.escape(
                        ap['hostname'])  # italicise hosts not currently visible
                ret += "<td>%s</td><td>%s</td>" % (ap['mac'], ap['channel'])
                ret += "<td>%d</td>" % int(now - ap['AT_lastseen'])  # time since last interaction
                ret += "<td>%s</td>" % ap['rssi']
                for t in ['seen', 'assoc', 'deauth', 'handshake']:
                    tag = 'AT_' + t
                    if tag in ap:
                        ret += "<td>%s</td>" % ap[tag]
                    else:
                        ret += "<td></td>"
                if lmac in self._agent._history:
                    ret += "<td>%s</td>" % self._agent._history[lmac]
                else:
                    ret += "<td>no attacks yet</td>"
                ret += "</tr>\n"
            #            for (mac, count) in sorted(self._agent._history.items(), key=lambda x:x[1], reverse = True):
            #                ret += "<tr><td>%s</td><td>%s</td><td></td><td>%s</td></tr>" % (mac, mac, count)
            ret += "</table>\n"
            if numHidden:
                ret += "%s visible, %s hidden networks<p>" % (numVisible, numHidden)

        return ret

    def update_parameter(self, cfg, parameter, vtype, val, ret):
        changed = False
        if parameter in cfg:
            old_val = cfg[parameter]

            if val == old_val:
                pass
            elif vtype == "int":
                cfg[parameter] = int(val)
                changed = True
            elif vtype == "float":
                cfg[parameter] = float(val)
                ret += "Updated float %s: %s -> %s<br>\n" % (parameter, old_val, val)
                changed = True
            elif vtype == "bool":
                cfg[parameter] = bool(val == "True")
                ret += "Updated boolean %s: %s -> %s<br>\n" % (parameter, old_val, val)
                changed = True
            elif vtype == "str":
                cfg[parameter] = val
                ret += "Updated string %s: %s -> %s<br>\n" % (parameter, old_val, val)
                changed = True
            else:
                ret += "No update %s (%s): %s -> %s<br>\n" % (parameter, type, old_val, val)

        return changed

    # called when http://<host>:<port>/plugins/<plugin>/ is called
    # must return a html page
    # IMPORTANT: If you use "POST"s, add a csrf-token (via csrf_token() and render_template_string)
    def on_webhook(self, path, request):
        # display personality parameters for editing
        # show statistic per channel, etc
        if not self._agent:
            ret = "<html><head><title>AUTO Tune not ready</title></head><body><h1>AUTO Tune not ready</h1></body></html>"
            return render_template_string(ret)

        try:
            if request.method == "GET":
                if path == "/" or not path:
                    logging.debug("webhook called")
                    ret = '<html><head><title>AUTO Tune</title><meta name="csrf_token" content="{{ csrf_token() }}"></head>'
                    ret += "<body><h1>AUTO Tune</h1><p>"
                    ret += self.showEditForm(request)

                    ret += self.showHistogram()
                    ret += self.showChistos()
                    if 'show_interactions' in self.options and self.options['show_interactions']:
                        ret += self.showInteractions()
                    ret += "</body></html>"
                    return render_template_string(ret)
                # other paths here
            elif request.method == "POST":
                ret = '<html><head><title>AUTO Tune</title><meta name="csrf_token" content="{{ csrf_token() }}"></head>'
                if path == "update":  # update settings that changed, save to json file
                    ret = '<html><head><title>AUTO Tune Update!</title><meta name="csrf_token" content="{{ csrf_token() }}"></head>'
                    ret += "<body><h1>AUTO Tune Update</h1>"
                    ret += "<h2>Processing changes</h2><ul>"
                    changed = False
                    for (key, val) in request.values.items():
                        if key != "":
                            # ret += "%s -> %s<br>\n" % (key,val)
                            try:
                                if key.startswith('newval,'):
                                    (tag, value, parameter, vtype) = key.split(",", 4)
                                    if value == val:
                                        logging.debug("Skip unchanged value")
                                        continue

                                    if parameter in self._agent._config['personality']:
                                        logging.debug("Personality update")
                                        chg = self.update_parameter(self._agent._config['personality'], parameter,
                                                                    vtype, val, ret)
                                    elif parameter in self.options:
                                        logging.debug("plugin settings update")
                                        chg = self.update_parameter(self.options, parameter, vtype, val, ret)
                                    else:
                                        ret += "<li><b>Skipping unknown %s</b> -> %s\n" % (key, val)
                                    if chg:
                                        ret += "<li>%s: %s -> %s\n" % (parameter, value, val)
                                    changed = changed or chg
                                else:
                                    pass  # ret += "No update %s -> %s<br>\n" % (key, val)
                            except Exception as e:
                                ret += "</code><h2>Error</h2><pre>%s</pre><p><code>" % repr(e)
                                logging.exception(e)
                    ret += "</ul>"
                    if changed:
                        save_config(self._agent._config, "/etc/pwnagotchi/config.toml")
                    ret += self.showEditForm(request)
                    ret += self.showHistogram()
                    ret += self.showChistos()
                    ret += "</body></html>"
                else:
                    ret += "<body><h1>Unknown request</h1>"
                    ret += '<img src="/ui?%s">' % int(time.time())
                    ret += "<h2>Path</h2><code>%s</code><p>" % repr(path)
                    ret += "<h2>Request</h2><code>%s</code><p>" % repr(request.values)
                    ret += "</body></html>"
                return render_template_string(ret)
        except Exception as e:
            ret = "<html><head><title>AUTO Tune error</title></head>"
            ret += "<body><h1>%s</h1></body></html>" % repr(e)
            logging.exception("AUTO Tune error: %s" % repr(e))
            return render_template_string(ret)

    # called when the plugin is loaded
    def on_loaded(self):
        try:
            defaults = {'show_hidden': False,
                        'reset_history': True,
                        'extra_channels': 15,
                        }

            for d in defaults:
                if d not in self.options:
                    self.options[d] = defaults[d]
        except Exception as e:
            logging.exception(e)

    def on_ready(self, agent):
        self._agent = agent
        if self.options['reset_history']:
            self._agent._history = {}  # clear "max_interactions" data
            self._agent.run("wifi.recon clear")
            self._agent.run("wifi.clear")

    # called when the agent refreshed its access points list
    def on_wifi_update(self, agent, access_points):
        # check aps and update active channels
        try:
            active_channels = []
            self._histogram["loops"] = self._histogram["loops"] + 1
            for ap in access_points:
                self.markAPSeen(ap, 'wifi_update')
                ch = ap['channel']
                logging.debug("%s %d" % (ap['hostname'], ch))
                if ch not in active_channels:
                    active_channels.append(ch)
                    if ch in self._unscanned_channels:
                        self._unscanned_channels.remove(ch)
                self._histogram[ch] = 1 if ch not in self._histogram else self._histogram[ch] + 1

            self._active_channels = active_channels
            logging.info("Histo: %s" % repr(self._histogram))
        except Exception as e:
            logging.exception(e)

    # called when the agent refreshed an unfiltered access point list
    # this list contains all access points that were detected BEFORE filtering
    # def on_unfiltered_ap_list(self, agent, access_points):
    #    pass

    # called when an epoch is over (where an epoch is a single loop of the main algorithm)
    def on_epoch(self, agent, epoch, epoch_data):
        # pick set of channels for next time
        try:
            next_channels = self._active_channels.copy()
            n = 3 if "extra_channels" not in self.options else self.options["extra_channels"]
            if len(self._unscanned_channels) == 0:
                if "restrict_channels" in self.options:
                    logging.info("Repopulating from restricted list")
                    self._unscanned_channels = self.options["restrict_channels"].copy()
                elif hasattr(agent, "_allowed_channels"):
                    logging.info("Repopulating from allowed list: %s" % agent._allowed_channels)
                    self._unscanned_channels = agent._allowed_channels.copy()
                elif hasattr(agent, "_supported_channels"):
                    logging.info("Repopulating from supported list")
                    self._unscanned_channels = agent._supported_channels.copy()
                else:
                    logging.info("Repopulating unscanned list")
                    self._unscanned_channels = pwnagotchi.utils.iface_channels(agent._config['main']['iface'])

            for i in range(n):
                if len(self._unscanned_channels):
                    ch = random.choice(list(self._unscanned_channels))
                    self._unscanned_channels.remove(ch)
                    next_channels.append(ch)
            # update live config
            agent._config['personality']['channels'] = next_channels
            logging.info("Active: %s, Next scan: %s, yet unscanned: %d %s" % (
            self._active_channels, next_channels, len(self._unscanned_channels), self._unscanned_channels))
        except Exception as e:
            logging.exception(e)

    def markAPSeen(self, access_point, context=None):
        try:
            apname = self.normalize(access_point['hostname'])
            apmac = self.normalize(access_point['mac'])
            apID = apname + '-' + apmac
            channel = access_point['channel']

            contextlabel = " on " + context if context else ""
            tag = 'AT_' + context if context else 'AT_seen'

            if apID not in self._known_aps:
                # first time seen this AP
                self._known_aps[apID] = access_point.copy()
                self._known_aps[apID]['AT_seen'] = 1
                self._known_aps[apID][tag] = 1
                self._known_aps[apID]['AT_visible'] = True

                self.incrementChisto('Unique APs', channel)
                self.incrementChisto('Current APs', channel)

                logging.info("New AP%s: %s" % (contextlabel, apID))
            else:
                # seen before, merge info
                for p in access_point:
                    self._known_aps[apID][p] = access_point[p]

                # if wasn't visible, increment current count
                if not self._known_aps[apID]['AT_visible']:
                    self._known_aps[apID]['AT_visible'] = True
                    self._known_aps[apID]['AT_seen'] += 1
                    self.incrementChisto('Current APs', channel)

                # increment context count in the AP data
                self._known_aps[apID][tag] = 1 if tag not in self._known_aps[apID] else self._known_aps[apID][tag] + 1
                if not context:
                    logging.info("Returning AP: %s" % apID)

            self._known_aps[apID]['AT_lastseen'] = time.time()
            return True
        except Exception as e:
            logging.exception(e)
            return False

    # called when the agent is sending an association frame
    def on_association(self, agent, access_point):
        try:
            self.incrementChisto('Associations', access_point['channel'])
            self.markAPSeen(access_point, "assoc")

        except Exception as e:
            logging.exception(e)

    # called when the agent is deauthenticating a client station from an AP
    def on_deauthentication(self, agent, access_point, client_station):
        try:
            self.incrementChisto('Deauths', access_point['channel'])
            self.markAPSeen(access_point, "deauth")

        except Exception as e:
            logging.exception(e)

    # callend when the agent is tuning on a specific channel
    def on_channel_hop(self, agent, channel):
        pass

    # called when a new handshake is captured, access_point and client_station are json objects
    # if the agent could match the BSSIDs to the current list, otherwise they are just the strings of the BSSIDs
    def on_handshake(self, agent, filename, access_point, client_station):
        try:
            self.incrementChisto('Handshakes', access_point['channel'])
            self.markAPSeen(access_point, "handshake")
        except Exception as e:
            logging.exception(e)

    def on_bcap_wifi_ap_new(self, agent, event):
        try:
            ap = event['data']
            apname = self.normalize(ap['hostname'])
            apmac = self.normalize(ap['mac'])
            apID = apname + '-' + apmac
            channel = ap['channel']

            self.markAPSeen(ap)

        except Exception as e:
            logging.exception(repr(e))

    def on_bcap_wifi_ap_lost(self, agent, event):
        try:
            ap = event['data']
            apname = self.normalize(ap['hostname'])
            apmac = self.normalize(ap['mac'])
            apID = apname + '-' + apmac
            channel = ap['channel']

            if apID not in self._known_aps:
                self.incrementChisto('Missed joins', channel)
                logging.warn("Unknown AP '%s' seen leaving" % apID)
            else:
                if not self._known_aps[apID]['AT_visible']:
                    self.incrementChisto('Missed rejoins', channel)
                    logging.warn("AP '%s' already gone", apID)
                else:
                    self._known_aps[apID]['AT_visible'] = False
                    self.incrementChisto('Current APs', channel, -1)

        except Exception as e:
            logging.exception(repr(e))

    def on_bcap_wifi_client_new(self, agent, event):
        try:
            ap = event['data']['AP']
            cl = event['data']['Client']
            apmac = self.normalize(ap['mac'])
            clmac = self.normalize(cl['mac'])
            clID = clmac + '-' + apmac
            channel = ap['channel']
        except Exception as e:
            logging.exception(repr(e))

    def on_bcap_wifi_client_lost(self, agent, event):
        try:
            ap = event['data']['AP']
            cl = event['data']['Client']
        except Exception as e:
            logging.exception(repr(e))