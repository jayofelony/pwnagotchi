import logging
import re
import subprocess
import time
import random
from io import TextIOWrapper

import pwnagotchi
from pwnagotchi import plugins

import pwnagotchi.ui.faces as faces
from pwnagotchi.bettercap import Client

from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts


class FixServices(plugins.Plugin):
    __author__ = 'jayofelony'
    __version__ = '1.0'
    __license__ = 'GPL3'
    __description__ = 'Fix blindness, firmware crashes and brain not being loaded'
    __name__ = 'Fix_Services'
    __help__ = """
    Reload brcmfmac module when blindbug is detected, instead of rebooting. Adapted from WATCHDOG.
    """

    def __init__(self):
        self.options = dict()
        self.pattern = re.compile(r'brcmf_cfg80211_nexmon_set_channel.*?Set Channel failed')
        self.pattern2 = re.compile(r'wifi error while hopping to channel')
        self.pattern3 = re.compile(r'Firmware has halted or crashed')
        self.pattern4 = re.compile(r'error 400: could not find interface wlan0mon')
        self.isReloadingMon = False
        self.connection = None
        self.LASTTRY = 0
        self._status = "--"
        self._count = 0

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        self._status = "ld"
        logging.info("[Fix_Services] plugin loaded.")

    def on_ready(self, agent):
        last_lines = ''.join(list(TextIOWrapper(subprocess.Popen(['journalctl', '-n10', '-k'],
                                                                 stdout=subprocess.PIPE).stdout))[-10:])
        try:
            cmd_output = subprocess.check_output("ip link show wlan0mon", shell=True)
            logging.info("[Fix_Services ip link show wlan0mon]: %s" % repr(cmd_output))
            if ",UP," in str(cmd_output):
                logging.info("wlan0mon is up.")
                self._status = "up"

            if len(self.pattern.findall(last_lines)) >= 3:
                self._status = "XX"
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Blind-Bug detected. Restarting.')
                    display.update(force=True)
                logging.info('[Fix_Services] Blind-Bug detected. Restarting.')
                try:
                    self._tryTurningItOffAndOnAgain(agent)
                except Exception as err:
                    logging.warning("[Fix_Services turnOffAndOn] %s" % repr(err))

            else:
                logging.info("[Fix_Services] Logs look good!")
                self._status = ""

        except Exception as err:
            logging.error("[Fix_Services ip link show wlan0mon]: %s" % repr(err))
            try:
                self._status = "xx"
                self._tryTurningItOffAndOnAgain(agent)
            except Exception as err:
                logging.error("[Fix_Services OffNOn]: %s" % repr(err))

    # bettercap sys_log event
    # search syslog events for the brcmf channel fail, and reset when it shows up
    # apparently this only gets messages from bettercap going to syslog, not from syslog
    def on_bcap_sys_log(self, agent, event):
        if re.search('wifi error while hopping to channel', event['data']['Message']):
            logging.info("[Fix_Services]SYSLOG MATCH: %s" % event['data']['Message'])
            logging.info("[Fix_Services]**** restarting wifi.recon")
            try:
                result = agent.run("wifi.recon off; wifi.recon on")
                if result["success"]:
                    logging.info("[Fix_Services] wifi.recon flip: success!")
                    if hasattr(agent, 'view'):
                        display = agent.view()
                        if display:
                            display.update(force=True, new_data={"status": "Wifi recon flipped!", "face": faces.COOL})
                    else:
                        print("Wifi recon flipped")
                else:
                    logging.warning("[Fix_Services] wifi.recon flip: FAILED: %s" % repr(result))
                    self._tryTurningItOffAndOnAgain(agent)
            except Exception as err:
                logging.error("[Fix_Services]SYSLOG wifi.recon flip fail: %s" % err)
                self._tryTurningItOffAndOnAgain(agent)

    def on_epoch(self, agent, epoch, epoch_data):
        last_lines = ''.join(list(TextIOWrapper(subprocess.Popen(['journalctl', '-n10', '-k'],
                                                                 stdout=subprocess.PIPE).stdout))[-10:])
        other_last_lines = ''.join(list(TextIOWrapper(subprocess.Popen(['journalctl', '-n10'],
                                                                       stdout=subprocess.PIPE).stdout))[-10:])
        other_other_last_lines = ''.join(
            list(TextIOWrapper(subprocess.Popen(['tail', '-n10', '/var/log/pwnagotchi.log'],
                                                stdout=subprocess.PIPE).stdout))[-10:])
        # don't check if we ran a reset recently
        logging.debug("[Fix_Services]**** epoch")
        if time.time() - self.LASTTRY > 180:
            # get last 10 lines
            display = None

            logging.debug("[Fix_Services]**** checking")

            # Look for pattern 1
            if len(self.pattern.findall(last_lines)) >= 3:
                logging.info("[Fix_Services]**** Should trigger a reload of the wlan0mon device:\n%s" % last_lines)
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Blind-Bug detected. Restarting.')
                    display.update(force=True)
                logging.info('[Fix_Services] Blind-Bug detected. Restarting.')
                try:
                    self._tryTurningItOffAndOnAgain(agent)
                except Exception as err:
                    logging.warning("[Fix_Services] TTOAOA: %s" % repr(err))

            # Look for pattern 2
            elif len(self.pattern2.findall(other_last_lines)) >= 5:
                logging.info("[Fix_Services]**** Should trigger a reload of the wlan0mon device:\n%s" % last_lines)
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Wifi channel stuck. Restarting recon.')
                    display.update(force=True)
                logging.info('[Fix_Services] Wifi channel stuck. Restarting recon.')

                try:
                    result = agent.run("wifi.recon off; wifi.recon on")
                    if result["success"]:
                        logging.info("[Fix_Services] wifi.recon flip: success!")
                        if display:
                            display.update(force=True, new_data={"status": "Wifi recon flipped!",
                                                                 "brcmfmac_status": self._status,
                                                                 "face": faces.COOL})
                        else:
                            print("Wifi recon flipped\nthat was easy!")
                    else:
                        logging.warning("[Fix_Services] wifi.recon flip: FAILED: %s" % repr(result))

                except Exception as err:
                    logging.error("[Fix_Services wifi.recon flip] %s" % repr(err))

            # Look for pattern 3
            elif len(self.pattern3.findall(other_last_lines)) >= 1:
                logging.info("[Fix_Services] Firmware has halted or crashed. Restarting wlan0mon.")
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Firmware has halted or crashed. Restarting wlan0mon.')
                    display.update(force=True)
                try:
                    # Run the monstart command to restart wlan0mon
                    cmd_output = subprocess.check_output("monstart", shell=True)
                    logging.info("[Fix_Services monstart]: %s" % repr(cmd_output))
                except Exception as err:
                    logging.error("[Fix_Services monstart]: %s" % repr(err))

            # Look for pattern 4
            elif len(self.pattern4.findall(other_other_last_lines)) >= 3:
                logging.info("[Fix_Services] wlan0 is down!")
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Restarting wlan0 now!')
                    display.update(force=True)
                try:
                    # Run the monstart command to restart wlan0mon
                    cmd_output = subprocess.check_output("monstart", shell=True)
                    logging.info("[Fix_Services monstart]: %s" % repr(cmd_output))
                except Exception as err:
                    logging.error("[Fix_Services monstart]: %s" % repr(err))

            else:
                print("logs look good")

    def logPrintView(self, level, message, ui=None, displayData=None, force=True):
        try:
            if level == "error":
                logging.error(message)
            elif level == "warning":
                logging.warning(message)
            elif level == "debug":
                logging.debug(message)
            else:
                logging.info(message)

            if ui:
                ui.update(force=force, new_data=displayData)
            elif displayData and "status" in displayData:
                print(displayData["status"])
            else:
                print("[%s] %s" % (level, message))
        except Exception as err:
            logging.error("[logPrintView] ERROR %s" % repr(err))

    def _tryTurningItOffAndOnAgain(self, connection):
        # avoid overlapping restarts, but allow it if it's been a while
        # (in case the last attempt failed before resetting "isReloadingMon")
        if self.isReloadingMon and (time.time() - self.LASTTRY) < 180:
            logging.info("[Fix_Services] Duplicate attempt ignored")
        else:
            self.isReloadingMon = True
            self.LASTTRY = time.time()

            self._status = "BL"
            if hasattr(connection, 'view'):
                display = connection.view()
                if display:
                    display.update(force=True, new_data={"status": "I'm blind! Try turning it off and on again",
                                                         "brcmfmac_status": self._status, "face": faces.BORED})
            else:
                display = None

            # main divergence from WATCHDOG starts here
            #
            # instead of rebooting, and losing all that energy loading up the AI
            #    pause wifi.recon, close wlan0mon, reload the brcmfmac kernel module
            #    then recreate wlan0mon, ..., and restart wifi.recon

            # Turn it off

            # attempt a sanity check. does wlan0mon exist?
            # is it up?
            try:
                cmd_output = subprocess.check_output("ip link show wlan0mon", shell=True)
                logging.info("[Fix_Services ip link show wlan0mon]: %s" % repr(cmd_output))
                if ",UP," in str(cmd_output):
                    logging.info("wlan0mon is up. Skip reset?")
                    # not reliable, so don't skip just yet
                    # print("wlan0mon is up. Skipping reset.")
                    # self.isReloadingMon = False
                    # return
            except Exception as err:
                logging.error("[Fix_Services ip link show wlan0mon]: %s" % repr(err))

            try:
                result = connection.run("wifi.recon off")
                if "success" in result:
                    self.logPrintView("info", "[Fix_Services] wifi.recon off: %s!" % repr(result),
                                      display, {"status": "Wifi recon paused!", "face": faces.COOL})
                    time.sleep(2)
                else:
                    self.logPrintView("warning", "[Fix_Services] wifi.recon off: FAILED: %s" % repr(result),
                                      display, {"status": "Recon was busted (probably)",
                                                "face": random.choice((faces.BROKEN, faces.DEBUG))})
            except Exception as err:
                logging.error("[Fix_Services wifi.recon off] error  %s" % (repr(err)))

            logging.info("[Fix_Services] recon paused. Now trying wlan0mon reload")

            try:
                cmd_output = subprocess.check_output("monstop", shell=True)
                self._status = "dn"
                self.logPrintView("info", "[Fix_Services] wlan0mon down and deleted: %s" % cmd_output,
                                  display, {"status": "wlan0mon d-d-d-down!", "face": faces.BORED})
            except Exception as nope:
                logging.error("[Fix_Services delete wlan0mon] %s" % nope)
                pass

            logging.debug("[Fix_Services] Now trying modprobe -r")

            # Try this sequence 3 times until it is reloaded
            #
            # Future: while "not fixed yet": blah blah blah. if "max_attemts", then reboot like the old days
            #
            tries = 1
            while tries < 3:
                try:
                    # unload the module
                    cmd_output = subprocess.check_output("sudo modprobe -r brcmfmac", shell=True)
                    self.logPrintView("info", "[Fix_Services] unloaded brcmfmac", display,
                                      {"status": "Turning it off #%s" % tries, "face": faces.SMART})
                    self._status = "ul"

                    # reload the module
                    try:
                        # reload the brcmfmac kernel module
                        cmd_output = subprocess.check_output("sudo modprobe brcmfmac", shell=True)

                        self.logPrintView("info", "[Fix_Services] reloaded brcmfmac")
                        self._status = "rl"

                        # success! now make the mon0
                        try:
                            cmd_output = subprocess.check_output("monstart", shell=True)
                            self.logPrintView("info", "[Fix_Services interface add wlan0mon worked #%s: %s"
                                              % (tries, cmd_output))
                            self._status = "up"
                            try:
                                # try accessing mon0 in bettercap
                                result = connection.run("set wifi.interface wlan0mon")
                                if "success" in result:
                                    logging.info("[Fix_Services set wifi.interface wlan0mon worked!")
                                    self._status = ""
                                    self._count = self._count + 1
                                    # stop looping and get back to recon
                                    break
                                else:
                                    logging.info(
                                        "[Fix_Services set wifi.interfaceface wlan0mon] failed? %s" % repr(result))
                            except Exception as err:
                                logging.info(
                                    "[Fix_Services set wifi.interface wlan0mon] except: %s" % repr(err))
                        except Exception as cerr:  #
                            if not display:
                                print("failed loading wlan0mon attempt #%s: %s" % (tries, repr(cerr)))
                    except Exception as err:  # from modprobe
                        if not display:
                            print("Failed reloading brcmfmac")
                        logging.error("[Fix_Services] Failed reloading brcmfmac %s" % repr(err))

                except Exception as nope:  # from modprobe -r
                    # fails if already unloaded, so probably fine
                    logging.error("[Fix_Services #%s modprobe -r] %s" % (tries, repr(nope)))
                    if not display:
                        print("[Fix_Services #%s modprobe -r] %s" % (tries, repr(nope)))
                    pass

                tries = tries + 1
                if tries < 3:
                    logging.info("[Fix_Services] wlan0mon didn't make it. trying again")
                    if not display:
                        print(" wlan0mon didn't make it. trying again")
                else:
                    logging.info("[Fix_Services] wlan0mon loading failed, no choice but to reboot ..")
                    pwnagotchi.reboot()

            # exited the loop, so hopefully it loaded
            if tries < 3:
                if display:
                    display.update(force=True, new_data={"status": "And back on again...",
                                                         "brcmfmac_status": self._status,
                                                         "face": faces.INTENSE})
                else:
                    print("And back on again...")
                logging.info("[Fix_Services] wlan0mon back up")
            else:
                self.LASTTRY = time.time()

            time.sleep(8 + tries * 2)  # give it a bit before restarting recon in bettercap
            self.isReloadingMon = False

            logging.info("[Fix_Services] re-enable recon")
            try:
                result = connection.run("wifi.clear; wifi.recon on")

                if "success" in result:  # and result["success"] is True:
                    self._status = ""
                    if display:
                        display.update(force=True, new_data={"status": "I can see again! (probably)",
                                                             "brcmfmac_status": self._status,
                                                             "face": faces.HAPPY})
                    else:
                        print("I can see again")
                    logging.info("[Fix_Services] wifi.recon on")
                    self.LASTTRY = time.time() + 120  # 2-minute pause until next time.
                else:
                    logging.error("[Fix_Services] wifi.recon did not start up")
                    self.LASTTRY = time.time() - 300  # failed, so try again ASAP
                    self.isReloadingMon = False

            except Exception as err:
                logging.error("[Fix_Services wifi.recon on] %s" % repr(err))
                pwnagotchi.reboot()

    # called to setup the ui elements
    def on_ui_setup(self, ui):
        with ui._lock:
            # add custom UI elements
            if "position" in self.options:
                pos = self.options['position'].split(',')
                pos = [int(x.strip()) for x in pos]
            else:
                pos = (ui.width() / 2 + 35, ui.height() - 11)

            logging.info("Got here")
            ui.add_element('brcmfmac_status', Text(color=BLACK, value='--', position=pos, font=fonts.Small))

    # called when the ui is updated
    def on_ui_update(self, ui):
        # update those elements
        if self._status:
            ui.set('brcmfmac_status', "wlan0mon %s" % self._status)
        else:
            ui.set('brcmfmac_status', "rst#%s" % self._count)

    def on_unload(self, ui):
        with ui._lock:
            try:
                ui.remove_element('brcmfmac_status')
                logging.info("[Fix_Services] unloaded")
            except Exception as err:
                logging.info("[Fix_Services] unload err %s " % repr(err))
            pass


# run from command line to brute force a reload
if __name__ == "__main__":
    print("Performing brcmfmac reload and restart wlan0mon in 5 seconds...")
    fb = FixServices()

    data = {'Message': "kernel: brcmfmac: brcmf_cfg80211_nexmon_set_channel: Set Channel failed: chspec=1234"}
    event = {'data': data}

    agent = Client('localhost', port=8081, username="pwnagotchi", password="pwnagotchi")

    time.sleep(2)
    print("3 seconds")
    time.sleep(3)
    fb.on_epoch(agent, event, None)
    # fb._tryTurningItOffAndOnAgain(agent)
