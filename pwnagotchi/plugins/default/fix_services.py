import logging
import os
import re
import subprocess
import time
import random

import pwnagotchi
from pwnagotchi import plugins

import pwnagotchi.ui.faces as faces
from pwnagotchi.bettercap import Client


class FixServices(plugins.Plugin):
    __author__ = 'jayofelony'
    __version__ = '1.1.0'
    __license__ = 'GPL3'
    __description__ = 'Fix blindness, firmware crashes and brain not being loaded. Auto-disables for external WiFi adapters.'
    __name__ = 'Fix_Services'
    __help__ = """
    Reload brcmfmac module when blindbug is detected, instead of rebooting. Adapted from WATCHDOG.
    Automatically disables itself when an external WiFi adapter is detected instead of the onboard brcmfmac chip.
    """

    SUBPROCESS_TIMEOUT = 30  # seconds

    def __init__(self):
        self.options = dict()
        self.pattern = re.compile(r'ieee80211 phy0: brcmf_cfg80211_add_iface: iface validation failed: err=-95')
        self.pattern2 = re.compile(r'wifi error while hopping to channel')
        self.pattern3 = re.compile(r'Firmware has halted or crashed')
        self.pattern4 = re.compile(r'error 400: could not find interface wlan0mon')
        self.pattern5 = re.compile(r'fatal error: concurrent map iteration and map write')
        self.pattern6 = re.compile(r'panic: runtime error')
        self.pattern7 = re.compile(r'ieee80211 phy0: _brcmf_set_multicast_list: Setting allmulti failed, -110')
        self.isReloadingMon = False
        self.connection = None
        self.LASTTRY = 0
        self.is_disabled = self._check_external_adapter()

    def _run_cmd(self, cmd, timeout=None):
        """Run a subprocess command safely with timeout and return stdout.

        Args:
            cmd: List of command arguments (no shell=True).
            timeout: Timeout in seconds (default: SUBPROCESS_TIMEOUT).

        Returns:
            stdout as string, or empty string on failure.
        """
        if timeout is None:
            timeout = self.SUBPROCESS_TIMEOUT
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            logging.error("[Fix_Services] Command timed out after %ds: %s" % (timeout, cmd))
            return ""
        except Exception as e:
            logging.error("[Fix_Services] Command failed: %s: %s" % (cmd, e))
            return ""

    def _get_journal_lines(self, extra_args=None, n=10):
        """Get last N lines from journalctl safely."""
        cmd = ['journalctl', '-n%d' % n]
        if extra_args:
            cmd.extend(extra_args)
        return self._run_cmd(cmd)

    def _get_display(self, agent):
        """Safely get the display from agent, returns None if unavailable."""
        if hasattr(agent, 'view'):
            try:
                return agent.view()
            except Exception:
                pass
        return None

    def _wifi_recon_flip(self, agent, display=None):
        """Attempt wifi.recon off then on. Returns True on success."""
        try:
            result = agent.run("wifi.recon off; wifi.recon on")
            if result.get("success"):
                logging.debug("[Fix_Services] wifi.recon flip: success!")
                if display:
                    display.update(force=True, new_data={"status": "Wifi recon flipped!",
                                                         "face": faces.COOL})
                return True
            else:
                logging.warning("[Fix_Services] wifi.recon flip: FAILED: %s" % repr(result))
                return False
        except Exception as err:
            logging.error("[Fix_Services] wifi.recon flip error: %s" % repr(err))
            return False

    def _check_external_adapter(self):
        """
        Check if an external WiFi adapter is being used instead of the onboard brcmfmac chip.
        Returns True if external adapter detected (plugin should be disabled), False otherwise.
        """
        try:
            interfaces = os.listdir('/sys/class/net/')

            if 'wlan0' not in interfaces:
                logging.warning("[Fix_Services] wlan0 interface not found. Plugin will be disabled.")
                return True

            driver_path = "/sys/class/net/wlan0/device/driver"
            if os.path.exists(driver_path):
                driver_link = os.readlink(driver_path)
                driver_name = os.path.basename(driver_link)

                logging.info("[Fix_Services] Detected WiFi driver: %s" % driver_name)

                if driver_name != "brcmfmac":
                    logging.info("[Fix_Services] External WiFi adapter detected (%s). "
                                 "Plugin will be disabled." % driver_name)
                    return True
                else:
                    logging.info("[Fix_Services] Onboard brcmfmac detected. Plugin will remain active.")
                    return False

            # Fallback: check lsmod directly (no shell pipe needed)
            try:
                result = subprocess.run(
                    ['lsmod'], capture_output=True, text=True, timeout=10
                )
                if 'brcmfmac' in result.stdout:
                    logging.info("[Fix_Services] brcmfmac module detected via lsmod. "
                                 "Plugin will remain active.")
                    return False
            except (subprocess.TimeoutExpired, Exception):
                pass

            logging.info("[Fix_Services] brcmfmac module not found. External adapter likely in use. "
                         "Plugin will be disabled.")
            return True

        except Exception as e:
            logging.error("[Fix_Services] Error detecting WiFi adapter: %s. Plugin will be disabled." % e)
            return True

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        if self.is_disabled:
            logging.info("[Fix_Services] plugin loaded but disabled due to external WiFi adapter.")
            return
        logging.info("[Fix_Services] plugin loaded.")

    def on_ready(self, agent):
        if self.is_disabled:
            return
        try:
            cmd_output = self._run_cmd(['ip', 'link', 'show', 'wlan0mon'])
            logging.debug("[Fix_Services ip link show wlan0mon]: %s" % repr(cmd_output))
            if ",UP," in cmd_output:
                logging.debug("[Fix_Services] wlan0mon is up.")
            else:
                logging.warning("[Fix_Services] wlan0mon not UP, attempting recovery.")
                self._tryTurningItOffAndOnAgain(agent)
        except Exception as err:
            logging.error("[Fix_Services] on_ready error: %s" % repr(err))
            try:
                self._tryTurningItOffAndOnAgain(agent)
            except Exception as err2:
                logging.error("[Fix_Services] recovery also failed: %s" % repr(err2))

    # bettercap sys_log event
    # search syslog events for the brcmf channel fail, and reset when it shows up
    # apparently this only gets messages from bettercap going to syslog, not from syslog
    def on_bcap_sys_log(self, agent, event):
        if self.is_disabled:
            return
        message = event.get('data', {}).get('Message', '')
        if not isinstance(message, str):
            return
        if 'wifi error while hopping to channel' not in message:
            return
        # Cooldown: don't spam recon flips when bettercap is unstable
        if time.time() - self.LASTTRY < 30:
            return
        logging.debug("[Fix_Services] SYSLOG MATCH: %s" % message)
        logging.debug("[Fix_Services] Restarting wifi.recon")
        self.LASTTRY = time.time()
        display = self._get_display(agent)
        if not self._wifi_recon_flip(agent, display):
            self._tryTurningItOffAndOnAgain(agent)

    def on_epoch(self, agent, epoch, epoch_data):
        if self.is_disabled:
            return

        # Cooldown: don't check if we ran a reset recently
        if time.time() - self.LASTTRY <= 180:
            return

        # Read log sources once using safe subprocess calls
        kernel_lines = self._get_journal_lines(['-k'])
        syslog_lines = self._get_journal_lines()
        pwnlog_lines = self._run_cmd(
            ['tail', '-n10', '/etc/pwnagotchi/log/pwnagotchi.log']
        )

        display = self._get_display(agent)

        logging.debug("[Fix_Services] epoch check")

        # Pattern 1: iface validation failed → monstop/monstart + restart
        if self.pattern.findall(kernel_lines):
            logging.debug("[Fix_Services] iface validation failed, restarting")
            self.LASTTRY = time.time()
            self._run_cmd(['monstop'])
            self._run_cmd(['monstart'])
            if display:
                display.set('status', 'Wifi channel stuck. Restarting recon.')
                display.update(force=True)
            pwnagotchi.restart("AUTO")

        # Pattern 2: wifi channel hopping errors (need 5+ occurrences)
        elif len(self.pattern2.findall(syslog_lines)) >= 5:
            logging.debug("[Fix_Services] Wifi channel stuck, flipping recon")
            self.LASTTRY = time.time()
            if display:
                display.set('status', 'Wifi channel stuck. Restarting recon.')
                display.update(force=True)
            if not self._wifi_recon_flip(agent, display):
                logging.warning("[Fix_Services] Recon flip failed after channel errors")

        # Pattern 3: firmware halted/crashed → monstart
        elif self.pattern3.findall(syslog_lines):
            logging.debug("[Fix_Services] Firmware has halted or crashed. Restarting wlan0mon.")
            self.LASTTRY = time.time()
            if display:
                display.set('status', 'Firmware has halted or crashed. Restarting wlan0mon.')
                display.update(force=True)
            self._run_cmd(['monstart'])

        # Pattern 4: wlan0mon missing (need 3+ occurrences) → monstart
        elif len(self.pattern4.findall(pwnlog_lines)) >= 3:
            logging.debug("[Fix_Services] wlan0mon missing, running monstart")
            self.LASTTRY = time.time()
            if display:
                display.set('status', 'Restarting wlan0mon now!')
                display.update(force=True)
            self._run_cmd(['monstart'])

        # Patterns 5+6: bettercap crash (concurrent map write or runtime panic)
        elif self.pattern5.findall(pwnlog_lines) or self.pattern6.findall(pwnlog_lines):
            logging.debug("[Fix_Services] Bettercap has crashed! Restarting.")
            self.LASTTRY = time.time()
            if display:
                display.set('status', 'Restarting pwnagotchi!')
                display.update(force=True)
            self._run_cmd(['sudo', 'systemctl', 'restart', 'bettercap'])
            pwnagotchi.restart("AUTO")

        # Pattern 7: multicast list failed → recon flip
        elif self.pattern7.findall(pwnlog_lines):
            logging.debug("[Fix_Services] Monitor mode multicast failed, flipping recon")
            self.LASTTRY = time.time()
            if not self._wifi_recon_flip(agent, display):
                logging.warning("[Fix_Services] Recon flip failed after multicast error")

        else:
            logging.debug("[Fix_Services] logs look good")

    def logPrintView(self, level, message, ui=None, displayData=None, force=True):
        try:
            if level == "error":
                logging.error(message)
            elif level == "warning":
                logging.warning(message)
            else:
                logging.debug(message)

            if ui:
                ui.update(force=force, new_data=displayData)
            elif displayData and "status" in displayData:
                logging.debug(displayData["status"])
        except Exception as err:
            logging.error("[Fix_Services logPrintView] %s" % repr(err))

    def _tryTurningItOffAndOnAgain(self, connection):
        if self.is_disabled:
            return
        # avoid overlapping restarts, but allow it if it's been a while
        # (in case the last attempt failed before resetting "isReloadingMon")
        if self.isReloadingMon and (time.time() - self.LASTTRY) < 180:
            logging.debug("[Fix_Services] Duplicate attempt ignored")
            return

        self.isReloadingMon = True
        self.LASTTRY = time.time()

        display = self._get_display(connection)
        if display:
            display.update(force=True, new_data={"status": "I'm blind! Try turning it off and on again",
                                                 "face": faces.BORED})

        # main divergence from WATCHDOG starts here
        #
        # instead of rebooting, and losing all that energy loading up the AI
        #    pause wifi.recon, close wlan0mon, reload the brcmfmac kernel module
        #    then recreate wlan0mon, ..., and restart wifi.recon

        # attempt a sanity check. does wlan0mon exist? is it up?
        try:
            cmd_output = self._run_cmd(['ip', 'link', 'show', 'wlan0mon'])
            logging.debug("[Fix_Services ip link show wlan0mon]: %s" % repr(cmd_output))
            if ",UP," in cmd_output:
                logging.debug("[Fix_Services] wlan0mon is up. Skip reset?")
                # not reliable, so don't skip just yet
        except Exception as err:
            logging.error("[Fix_Services ip link show wlan0mon]: %s" % repr(err))

        # Turn off wifi.recon
        try:
            result = connection.run("wifi.recon off")
            if result.get("success"):
                self.logPrintView("info", "[Fix_Services] wifi.recon off: success",
                                  display, {"status": "Wifi recon paused!", "face": faces.COOL})
                time.sleep(2)
            else:
                self.logPrintView("warning", "[Fix_Services] wifi.recon off: FAILED: %s" % repr(result),
                                  display, {"status": "Recon was busted (probably)",
                                            "face": random.choice((faces.BROKEN, faces.DEBUG))})
        except Exception as err:
            logging.error("[Fix_Services] wifi.recon off error: %s" % repr(err))

        logging.debug("[Fix_Services] recon paused. Now trying wlan0mon reload")

        # Stop monitor mode
        try:
            cmd_output = self._run_cmd(['monstop'])
            self.logPrintView("info", "[Fix_Services] wlan0mon down and deleted: %s" % cmd_output,
                              display, {"status": "wlan0mon d-d-d-down!", "face": faces.BORED})
        except Exception as nope:
            logging.error("[Fix_Services] monstop failed: %s" % nope)

        logging.debug("[Fix_Services] Now trying modprobe -r")

        # Try this sequence up to 3 times until it is reloaded
        tries = 0
        success = False
        while tries < 3:
            tries += 1
            try:
                # unload the module
                self._run_cmd(['sudo', 'modprobe', '-r', 'brcmfmac'])
                self.logPrintView("info", "[Fix_Services] unloaded brcmfmac", display,
                                  {"status": "Turning it off #%s" % tries, "face": faces.SMART})

                # reload the module
                try:
                    self._run_cmd(['sudo', 'modprobe', 'brcmfmac'])
                    self.logPrintView("info", "[Fix_Services] reloaded brcmfmac")

                    # success! now make the mon0
                    try:
                        cmd_output = self._run_cmd(['monstart'])
                        self.logPrintView("info", "[Fix_Services] interface add wlan0mon worked #%s: %s"
                                          % (tries, cmd_output))
                        try:
                            # try accessing mon0 in bettercap
                            result = connection.run("set wifi.interface wlan0mon")
                            if result.get("success"):
                                logging.debug("[Fix_Services] set wifi.interface wlan0mon worked!")
                                success = True
                                # stop looping and get back to recon
                                break
                            else:
                                logging.debug(
                                    "[Fix_Services] set wifi.interface wlan0mon failed: %s" % repr(result))
                        except Exception as err:
                            logging.debug(
                                "[Fix_Services] set wifi.interface wlan0mon except: %s" % repr(err))
                    except Exception as cerr:
                        logging.error("[Fix_Services] failed loading wlan0mon attempt #%s: %s"
                                      % (tries, repr(cerr)))
                except Exception as err:  # from modprobe
                    logging.error("[Fix_Services] Failed reloading brcmfmac: %s" % repr(err))

            except Exception as nope:  # from modprobe -r
                # fails if already unloaded, so probably fine
                logging.error("[Fix_Services #%s modprobe -r] %s" % (tries, repr(nope)))

            if tries < 3:
                logging.debug("[Fix_Services] wlan0mon didn't make it. trying again")
            else:
                logging.error("[Fix_Services] wlan0mon loading failed after %d attempts, rebooting" % tries)
                self.isReloadingMon = False
                pwnagotchi.reboot()
                return

        # exited the loop, so hopefully it loaded
        if success:
            if display:
                display.update(force=True, new_data={"status": "And back on again...",
                                                     "face": faces.INTENSE})
            logging.debug("[Fix_Services] wlan0mon back up")

        time.sleep(8 + tries * 2)  # give it a bit before restarting recon in bettercap
        self.isReloadingMon = False

        logging.debug("[Fix_Services] re-enable recon")
        try:
            result = connection.run("wifi.clear; wifi.recon on")

            if result.get("success"):
                if display:
                    display.update(force=True, new_data={"status": "I can see again! (probably)",
                                                         "face": faces.HAPPY})
                logging.debug("[Fix_Services] wifi.recon on")
                self.LASTTRY = time.time() + 120  # 2-minute pause until next time.
            else:
                logging.error("[Fix_Services] wifi.recon did not start up")
                self.LASTTRY = time.time() - 300  # failed, so try again ASAP

        except Exception as err:
            logging.error("[Fix_Services] wifi.recon on failed: %s" % repr(err))
            pwnagotchi.reboot()

    # called to setup the ui elements
    def on_ui_setup(self, ui):
        if self.is_disabled:
            return

    # called when the ui is updated
    def on_ui_update(self, ui):
        if self.is_disabled:
            return

    def on_unload(self, ui):
        self.isReloadingMon = False
        logging.info("[Fix_Services] plugin unloaded.")


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
