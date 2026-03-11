import logging
import os
import re
import subprocess
import threading
import time
import random

import pwnagotchi
from pwnagotchi import plugins

import pwnagotchi.ui.faces as faces
from pwnagotchi.bettercap import Client


class FixServices(plugins.Plugin):
    __author__ = 'jayofelony'
    __version__ = '1.2.0'
    __license__ = 'GPL3'
    __description__ = 'Fix blindness, firmware crashes and brain not being loaded. Auto-disables for external WiFi adapters.'
    __name__ = 'Fix_Services'
    __help__ = """
    Reload brcmfmac module when blindbug is detected, instead of rebooting. Adapted from WATCHDOG.
    Automatically disables itself when an external WiFi adapter is detected instead of the onboard brcmfmac chip.
    """

    # Configuration constants — extracted from previously hardcoded magic numbers
    SUBPROCESS_TIMEOUT = 30       # Max seconds for any subprocess call
    EPOCH_COOLDOWN = 180          # Base seconds between epoch recovery attempts
    SYSLOG_COOLDOWN = 30          # Seconds between syslog-triggered recon flips
    MAX_RELOAD_ATTEMPTS = 3       # Max brcmfmac reload retries before reboot
    JOURNAL_LINES = 20            # Lines to read from journalctl per check
    PWNLOG_LINES = 10             # Lines to read from pwnagotchi.log per check
    RECON_RESTART_DELAY = 8       # Base seconds to wait before restarting recon
    POST_SUCCESS_COOLDOWN = 120   # Extra cooldown seconds after successful recovery
    MAX_BACKOFF_COOLDOWN = 3600   # Maximum backoff cooldown (1 hour)

    # Valid interface name pattern — alphanumeric, underscore, hyphen only.
    # Prevents command injection if interface names ever come from config.
    _IFACE_RE = re.compile(r'^[a-zA-Z0-9_-]+$')

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
        self._lock = threading.Lock()  # Guards LASTTRY and isReloadingMon across threads
        self._fail_count = 0           # Consecutive recovery failures for backoff
        self._is_root = getattr(os, 'getuid', lambda: -1)() == 0
        self.is_disabled = self._check_external_adapter()

    # ── Helpers ──────────────────────────────────────────────────────────

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

    def _sudo_cmd(self, cmd, timeout=None):
        """Run a command, prepending sudo only if not already root.

        Pwnagotchi typically runs as root, so sudo is redundant in that case.
        This avoids relying on passwordless sudo configuration.
        """
        if self._is_root:
            return self._run_cmd(cmd, timeout)
        return self._run_cmd(['sudo'] + cmd, timeout)

    def _read_last_lines(self, filepath, n=10):
        """Read last N lines from a file using Python I/O (no subprocess needed).

        Replaces the previous approach of shelling out to 'tail' — saves one
        subprocess call per epoch on resource-constrained Pi Zero hardware.
        """
        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
                return ''.join(lines[-n:])
        except Exception as e:
            logging.debug("[Fix_Services] Could not read %s: %s" % (filepath, e))
            return ""

    def _get_journal_lines(self, extra_args=None, n=None):
        """Get last N lines from journalctl safely."""
        if n is None:
            n = self.JOURNAL_LINES
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

    def _get_cooldown(self):
        """Get current epoch cooldown with exponential backoff on repeated failures.

        First failure: 180s, second: 360s, third: 720s, ... up to 3600s (1 hour).
        Prevents recovery storms when the underlying hardware issue persists.
        """
        if self._fail_count <= 0:
            return self.EPOCH_COOLDOWN
        backoff = self.EPOCH_COOLDOWN * (2 ** min(self._fail_count, 5))
        return min(backoff, self.MAX_BACKOFF_COOLDOWN)

    def _record_success(self):
        """Reset failure count after successful recovery."""
        self._fail_count = 0

    def _record_failure(self):
        """Increment failure count for exponential backoff."""
        self._fail_count += 1
        logging.debug("[Fix_Services] Consecutive failures: %d, next cooldown: %ds"
                      % (self._fail_count, self._get_cooldown()))

    @staticmethod
    def _validate_iface(name):
        """Validate interface name to prevent command injection.

        All interface names are currently hardcoded (wlan0, wlan0mon), but this
        guard protects against future changes that might source names from config.
        """
        if not name or not FixServices._IFACE_RE.match(name):
            raise ValueError("Invalid interface name: %s" % repr(name))
        return name

    # ── Adapter detection ────────────────────────────────────────────────

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

    # ── Plugin hooks ─────────────────────────────────────────────────────

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
            iface = self._validate_iface('wlan0mon')
            cmd_output = self._run_cmd(['ip', 'link', 'show', iface])
            logging.debug("[Fix_Services] ip link show %s: %s" % (iface, repr(cmd_output)))
            if ",UP," in cmd_output:
                logging.debug("[Fix_Services] %s is up." % iface)
            else:
                logging.warning("[Fix_Services] %s not UP, attempting recovery." % iface)
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
        with self._lock:
            if time.time() - self.LASTTRY < self.SYSLOG_COOLDOWN:
                return
            self.LASTTRY = time.time()
        logging.debug("[Fix_Services] SYSLOG MATCH: %s" % message)
        display = self._get_display(agent)
        if not self._wifi_recon_flip(agent, display):
            self._tryTurningItOffAndOnAgain(agent)

    def on_epoch(self, agent, epoch, epoch_data):
        if self.is_disabled:
            return

        # Cooldown with exponential backoff on repeated failures
        with self._lock:
            cooldown = self._get_cooldown()
            if time.time() - self.LASTTRY <= cooldown:
                return

        # Read log sources: 1 subprocess call + 1 Python file read
        # (down from 3 subprocess calls — saves 2 Popen per epoch on Pi Zero)
        journal_lines = self._get_journal_lines()
        pwnlog_lines = self._read_last_lines(
            '/etc/pwnagotchi/log/pwnagotchi.log', self.PWNLOG_LINES
        )

        display = self._get_display(agent)

        logging.debug("[Fix_Services] epoch check (cooldown=%ds, failures=%d)"
                      % (cooldown, self._fail_count))

        handled = False

        # Pattern 1: iface validation failed → monstop/monstart + restart
        if self.pattern.findall(journal_lines):
            logging.debug("[Fix_Services] iface validation failed, restarting")
            with self._lock:
                self.LASTTRY = time.time()
            self._run_cmd(['monstop'])
            self._run_cmd(['monstart'])
            if display:
                display.set('status', 'Wifi channel stuck. Restarting recon.')
                display.update(force=True)
            pwnagotchi.restart("AUTO")
            handled = True

        # Pattern 2: wifi channel hopping errors (need 5+ occurrences)
        elif len(self.pattern2.findall(journal_lines)) >= 5:
            logging.debug("[Fix_Services] Wifi channel stuck, flipping recon")
            with self._lock:
                self.LASTTRY = time.time()
            if display:
                display.set('status', 'Wifi channel stuck. Restarting recon.')
                display.update(force=True)
            if self._wifi_recon_flip(agent, display):
                self._record_success()
            else:
                self._record_failure()
                logging.warning("[Fix_Services] Recon flip failed after channel errors")
            handled = True

        # Pattern 3: firmware halted/crashed → monstart
        elif self.pattern3.findall(journal_lines):
            logging.debug("[Fix_Services] Firmware has halted or crashed. Restarting wlan0mon.")
            with self._lock:
                self.LASTTRY = time.time()
            if display:
                display.set('status', 'Firmware has halted or crashed. Restarting wlan0mon.')
                display.update(force=True)
            self._run_cmd(['monstart'])
            handled = True

        # Pattern 4: wlan0mon missing (need 3+ occurrences) → monstart
        elif len(self.pattern4.findall(pwnlog_lines)) >= 3:
            logging.debug("[Fix_Services] wlan0mon missing, running monstart")
            with self._lock:
                self.LASTTRY = time.time()
            if display:
                display.set('status', 'Restarting wlan0mon now!')
                display.update(force=True)
            self._run_cmd(['monstart'])
            handled = True

        # Patterns 5+6: bettercap crash (concurrent map write or runtime panic)
        elif self.pattern5.findall(pwnlog_lines) or self.pattern6.findall(pwnlog_lines):
            logging.debug("[Fix_Services] Bettercap has crashed! Restarting.")
            with self._lock:
                self.LASTTRY = time.time()
            if display:
                display.set('status', 'Restarting pwnagotchi!')
                display.update(force=True)
            self._sudo_cmd(['systemctl', 'restart', 'bettercap'])
            pwnagotchi.restart("AUTO")
            handled = True

        # Pattern 7: multicast list failed → recon flip
        elif self.pattern7.findall(pwnlog_lines):
            logging.debug("[Fix_Services] Monitor mode multicast failed, flipping recon")
            with self._lock:
                self.LASTTRY = time.time()
            if self._wifi_recon_flip(agent, display):
                self._record_success()
            else:
                self._record_failure()
                logging.warning("[Fix_Services] Recon flip failed after multicast error")
            handled = True

        if not handled:
            logging.debug("[Fix_Services] logs look good")
            # Logs are clean — reset failure count since things are stable
            if self._fail_count > 0:
                self._record_success()

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
        with self._lock:
            if self.isReloadingMon and (time.time() - self.LASTTRY) < self.EPOCH_COOLDOWN:
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
            iface = self._validate_iface('wlan0mon')
            cmd_output = self._run_cmd(['ip', 'link', 'show', iface])
            logging.debug("[Fix_Services] ip link show %s: %s" % (iface, repr(cmd_output)))
            if ",UP," in cmd_output:
                logging.debug("[Fix_Services] %s is up. Skip reset?" % iface)
                # not reliable, so don't skip just yet
        except Exception as err:
            logging.error("[Fix_Services] ip link show error: %s" % repr(err))

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
            self.logPrintView("info", "[Fix_Services] wlan0mon stopped: %s" % cmd_output,
                              display, {"status": "wlan0mon d-d-d-down!", "face": faces.BORED})
        except Exception as nope:
            logging.error("[Fix_Services] monstop failed: %s" % nope)

        logging.debug("[Fix_Services] Now trying modprobe -r")

        # Try reload sequence up to MAX_RELOAD_ATTEMPTS times
        tries = 0
        success = False
        while tries < self.MAX_RELOAD_ATTEMPTS:
            tries += 1
            try:
                # unload the module
                self._sudo_cmd(['modprobe', '-r', 'brcmfmac'])
                self.logPrintView("info", "[Fix_Services] unloaded brcmfmac", display,
                                  {"status": "Turning it off #%s" % tries, "face": faces.SMART})

                # reload the module
                try:
                    self._sudo_cmd(['modprobe', 'brcmfmac'])
                    self.logPrintView("info", "[Fix_Services] reloaded brcmfmac")

                    # success! now make the mon0
                    try:
                        cmd_output = self._run_cmd(['monstart'])
                        self.logPrintView("info", "[Fix_Services] interface add wlan0mon worked #%s: %s"
                                          % (tries, cmd_output))
                        try:
                            # try accessing mon0 in bettercap
                            iface = self._validate_iface('wlan0mon')
                            result = connection.run("set wifi.interface %s" % iface)
                            if result.get("success"):
                                logging.debug("[Fix_Services] set wifi.interface %s worked!" % iface)
                                success = True
                                # stop looping and get back to recon
                                break
                            else:
                                logging.debug(
                                    "[Fix_Services] set wifi.interface %s failed: %s"
                                    % (iface, repr(result)))
                        except Exception as err:
                            logging.debug(
                                "[Fix_Services] set wifi.interface except: %s" % repr(err))
                    except Exception as cerr:
                        logging.error("[Fix_Services] failed loading wlan0mon attempt #%s: %s"
                                      % (tries, repr(cerr)))
                except Exception as err:  # from modprobe
                    logging.error("[Fix_Services] Failed reloading brcmfmac: %s" % repr(err))

            except Exception as nope:  # from modprobe -r
                # fails if already unloaded, so probably fine
                logging.error("[Fix_Services #%s modprobe -r] %s" % (tries, repr(nope)))

            if tries < self.MAX_RELOAD_ATTEMPTS:
                logging.debug("[Fix_Services] wlan0mon didn't make it. trying again")
            else:
                logging.error("[Fix_Services] wlan0mon loading failed after %d attempts, rebooting"
                              % tries)
                with self._lock:
                    self.isReloadingMon = False
                self._record_failure()
                pwnagotchi.reboot()
                return

        # exited the loop, so hopefully it loaded
        if success:
            if display:
                display.update(force=True, new_data={"status": "And back on again...",
                                                     "face": faces.INTENSE})
            logging.debug("[Fix_Services] wlan0mon back up")
            self._record_success()
        else:
            self._record_failure()

        time.sleep(self.RECON_RESTART_DELAY + tries * 2)
        with self._lock:
            self.isReloadingMon = False

        logging.debug("[Fix_Services] re-enable recon")
        try:
            result = connection.run("wifi.clear; wifi.recon on")

            if result.get("success"):
                if display:
                    display.update(force=True, new_data={"status": "I can see again! (probably)",
                                                         "face": faces.HAPPY})
                logging.debug("[Fix_Services] wifi.recon on")
                with self._lock:
                    self.LASTTRY = time.time() + self.POST_SUCCESS_COOLDOWN
            else:
                logging.error("[Fix_Services] wifi.recon did not start up")
                self._record_failure()
                with self._lock:
                    self.LASTTRY = time.time()

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
        with self._lock:
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
