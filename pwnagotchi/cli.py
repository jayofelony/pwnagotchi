import logging
import argparse
import time
import signal
import sys
import toml
import requests
import os
import re

import pwnagotchi
from pwnagotchi import utils
from pwnagotchi.google import cmd as google_cmd
from pwnagotchi.plugins import cmd as plugins_cmd
from pwnagotchi import log
from pwnagotchi import fs
from pwnagotchi.utils import DottedTomlEncoder, parse_version as version_to_tuple


def pwnagotchi_cli():
    def do_clear(display):
        logging.info("clearing the display ...")
        display.clear()
        sys.exit(0)

    def do_manual_mode(agent):
        logging.info("entering manual mode ...")

        agent.mode = 'manual'
        agent.last_session.parse(agent.view(), args.skip_session)
        if not args.skip_session:
            logging.info(
                "the last session lasted %s (%d completed epochs, trained for %d), average reward:%s (min:%s max:%s)" % (
                    agent.last_session.duration_human,
                    agent.last_session.epochs,
                    agent.last_session.train_epochs,
                    agent.last_session.avg_reward,
                    agent.last_session.min_reward,
                    agent.last_session.max_reward))

        while True:
            display.on_manual_mode(agent.last_session)
            time.sleep(5)
            if grid.is_connected():
                plugins.on('internet_available', agent)

    def do_auto_mode(agent):
        logging.info("entering auto mode ...")

        agent.mode = 'auto'
        agent.last_session.parse(agent.view(), args.skip_session)  # show stats in AUTO
        agent.start()

        while True:
            try:
                # recon on all channels
                agent.recon()
                # get nearby access points grouped by channel
                channels = agent.get_access_points_by_channel()
                # for each channel
                for ch, aps in channels:
                    time.sleep(1)
                    agent.set_channel(ch)

                    if not agent.is_stale() and agent.any_activity():
                        logging.info("%d access points on channel %d" % (len(aps), ch))

                    # for each ap on this channel
                    for ap in aps:
                        # send an association frame in order to get for a PMKID
                        agent.associate(ap)
                        # deauth all client stations in order to get a full handshake
                        for sta in ap['clients']:
                            agent.deauth(ap, sta)
                            time.sleep(1)  # delay to not trigger nexmon firmware bugs

                # An interesting effect of this:
                #
                # From Pwnagotchi's perspective, the more new access points
                # and / or client stations nearby, the longer one epoch of
                # its relative time will take ... basically, in Pwnagotchi's universe,
                # Wi-Fi electromagnetic fields affect time like gravitational fields
                # affect ours ... neat ^_^
                agent.next_epoch()

                if grid.is_connected():
                    plugins.on('internet_available', agent)

            except Exception as e:
                if str(e).find("wifi.interface not set") > 0:
                    logging.exception("main loop exception due to unavailable wifi device, likely programmatically disabled (%s)", e)
                    logging.info("sleeping 60 seconds then advancing to next epoch to allow for cleanup code to trigger")
                    time.sleep(60)
                    agent.next_epoch()
                else:
                    logging.exception("main loop exception (%s)", e)

    def add_parsers(parser):
        """
        Adds the plugins and google subcommands
        """
        subparsers = parser.add_subparsers()

        # Add parsers from plugins_cmd
        plugins_cmd.add_parsers(subparsers)

        # Add parsers from google_cmd
        google_cmd.add_parsers(subparsers)

    parser = argparse.ArgumentParser(prog="pwnagotchi")
    # pwnagotchi --help
    parser.add_argument('-C', '--config', action='store', dest='config', default='/etc/pwnagotchi/default.toml',
                        help='Main configuration file.')
    parser.add_argument('-U', '--user-config', action='store', dest='user_config', default='/etc/pwnagotchi/config.toml',
                        help='If this file exists, configuration will be merged and this will override default values.')

    parser.add_argument('--manual', dest="do_manual", action="store_true", default=False, help="Manual mode.")
    parser.add_argument('--skip-session', dest="skip_session", action="store_true", default=False,
                        help="Skip last session parsing in manual mode.")

    parser.add_argument('--clear', dest="do_clear", action="store_true", default=False,
                        help="Clear the ePaper display and exit.")

    parser.add_argument('--debug', dest="debug", action="store_true", default=False,
                        help="Enable debug logs.")

    parser.add_argument('--version', dest="version", action="store_true", default=False,
                        help="Print the version.")

    parser.add_argument('--print-config', dest="print_config", action="store_true", default=False,
                        help="Print the configuration.")

    # Jayofelony added these
    parser.add_argument('--wizard', dest="wizard", action="store_true", default=False,
                        help="Interactive installation of your personal configuration.")
    parser.add_argument('--check-update', dest="check_update", action="store_true", default=False,
                        help="Check for updates on Pwnagotchi. And tells current version.")
    parser.add_argument('--donate', dest="donate", action="store_true", default=False,
                        help="How to donate to this project.")

    # pwnagotchi plugins --help
    add_parsers(parser)
    args = parser.parse_args()

    if plugins_cmd.used_plugin_cmd(args):
        config = utils.load_config(args)
        log.setup_logging(args, config)
        rc = plugins_cmd.handle_cmd(args, config)
        sys.exit(rc)
    if google_cmd.used_google_cmd(args):
        config = utils.load_config(args)
        log.setup_logging(args, config)
        rc = google_cmd.handle_cmd(args)
        sys.exit(rc)

    if args.version:
        print(pwnagotchi.__version__)
        sys.exit(0)

    if args.wizard:
        def is_valid_hostname(hostname):
            if len(hostname) > 255:
                return False
            if hostname[-1] == ".":
                hostname = hostname[:-1]  # strip exactly one dot from the right, if present
            allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
            return all(allowed.match(x) for x in hostname.split("."))

        pwn_restore = input("Do you want to restore the previous configuration?\n\n"
                            "[Y/N]: ")
        if pwn_restore in ('y', 'yes'):
            os.system("cp -f /etc/pwnagotchi/config.toml.bak /etc/pwnagotchi/config.toml")
            print("Your previous configuration is restored, and I will restart in 5 seconds.")
            time.sleep(5)
            os.system("service pwnagotchi restart")
        else:
            pwn_check = input("This will create a new configuration file and overwrite your current backup, are you sure?\n\n"
                              "[Y/N]: ")
            if pwn_check.lower() in ('y', 'yes'):
                os.system("mv -f /etc/pwnagotchi/config.toml /etc/pwnagotchi/config.toml.bak")
                with open("/etc/pwnagotchi/config.toml", "a+") as f:
                    f.write("# Do not edit this file if you do not know what you are doing!!!\n\n")
                    # Set pwnagotchi name
                    print("Welcome to the interactive installation of your personal Pwnagotchi configuration!\n"
                          "My name is Jayofelony, how may I call you?\n\n")
                    pwn_name = input("Pwnagotchi name (no spaces): ")
                    if pwn_name == "":
                        pwn_name = "Pwnagotchi"
                        print("I shall go by Pwnagotchi from now on!")
                        pwn_name = f"main.name = \"{pwn_name}\"\n"
                        f.write(pwn_name)
                    else:
                        if is_valid_hostname(pwn_name):
                            print(f"I shall go by {pwn_name} from now on!")
                            pwn_name = f"main.name = \"{pwn_name}\"\n"
                            f.write(pwn_name)
                        else:
                            print("You have chosen an invalid name. Please start over.")
                            exit()
                    pwn_whitelist = input("How many networks do you want to whitelist? "
                                          "We will also ask a MAC for each network?\n"
                                          "Each SSID and BSSID count as 1 network. \n\n"
                                          "Be sure to use digits as your answer.\n\n"
                                          "Amount of networks: ")
                    if int(pwn_whitelist) > 0:
                        f.write("main.whitelist = [\n")
                        for x in range(int(pwn_whitelist)):
                            ssid = input("SSID (Name): ")
                            bssid = input("BSSID (MAC): ")
                            f.write(f"\t\"{ssid}\",\n")
                            if bssid != "":
                                f.write(f"\t\"{bssid}\",\n")
                        f.write("]\n")
                    # set bluetooth tether
                    pwn_bluetooth = input("Do you want to enable BT-Tether?\n\n"
                                          "[Y/N] ")
                    if pwn_bluetooth.lower() in ('y', 'yes'):
                        f.write("main.plugins.bt-tether.enabled = true\n\n")
                        pwn_bluetooth_phone_name = input("What name uses your phone, check settings?\n\n")
                        if pwn_bluetooth_phone_name != "":
                            f.write(f"main.plugins.bt-tether.phone-name = \"{pwn_bluetooth_phone_name}\"\n")
                        pwn_bluetooth_device = input("What device do you use? android or ios?\n\n"
                                                     "Device: ")
                        if pwn_bluetooth_device != "":
                            if pwn_bluetooth_device != "android" and pwn_bluetooth_device != "ios":
                                print("You have chosen an invalid device. Please start over.")
                                exit()
                            f.write(f"main.plugins.bt-tether.phone = \"{pwn_bluetooth_device.lower()}\"\n")
                            if pwn_bluetooth_device == "android":
                                f.write("main.plugins.bt-tether.ip = \"192.168.44.44\"\n")
                            elif pwn_bluetooth_device == "ios":
                                f.write("main.plugins.bt-tether.ip = \"172.20.10.6\"\n")
                        pwn_bluetooth_mac = input("What is the bluetooth MAC of your device?\n\n"
                                                  "MAC: ")
                        if pwn_bluetooth_mac != "":
                            f.write(f"main.plugins.bt-tether.mac = \"{pwn_bluetooth_mac}\"\n")
                    # set up display settings
                    pwn_display_enabled = input("Do you want to enable a display?\n\n"
                                                "[Y/N]: ")
                    if pwn_display_enabled.lower() in ('y', 'yes'):
                        f.write("ui.display.enabled = true\n")
                        pwn_display_type = input("What display do you use?\n\n"
                                                 "Be sure to check for the correct display type @ \n"
                                                 "https://github.com/jayofelony/pwnagotchi/blob/master/pwnagotchi/utils.py#L240-L501\n\n"
                                                 "Display type: ")
                        if pwn_display_type != "":
                            f.write(f"ui.display.type = \"{pwn_display_type}\"\n")
                        pwn_display_invert = input("Do you want to invert the display colors?\n"
                                                   "N = Black background\n"
                                                   "Y = White background\n\n"
                                                   "[Y/N]: ")
                        if pwn_display_invert.lower() in ('y', 'yes'):
                            f.write("ui.invert = true\n")
                    f.close()
                    if pwn_bluetooth.lower() in ('y', 'yes'):
                        if pwn_bluetooth_device.lower == "android":
                            print("To visit the webui when connected with your phone, visit: http://192.168.44.44:8080\n"
                                  "Be sure to run `sudo bluetoothctl` to set-up the bluetooth connection for the first time. And read the wiki step 4.\n"
                                  "Your configuration is done, and I will restart in 5 seconds.")

                        elif pwn_bluetooth_device.lower == "ios":
                            print("To visit the webui when connected with your phone, visit: http://172.20.10.6:8080\n"
                                  "Your configuration is done, and I will restart in 5 seconds.")
                    else:
                        print("Your configuration is done, and I will restart in 5 seconds.")
                    time.sleep(5)
                    os.system("service pwnagotchi restart")
            else:
                print("Ok, doing nothing.")
        sys.exit(0)

    if args.donate:
        print("Donations can be made @ \n "
              "https://github.com/sponsors/jayofelony \n\n"
              "But only if you really want to!")
        sys.exit(0)

    if args.check_update:
        resp = requests.get("https://api.github.com/repos/jayofelony/pwnagotchi/releases/latest")
        latest = resp.json()
        latest_ver = latest['tag_name'].replace('v', '')

        local = version_to_tuple(pwnagotchi.__version__)
        remote = version_to_tuple(latest_ver)
        if remote > local:
            user_input = input("There is a new version available! Update from v%s to v%s?\n[Y/N] " % (pwnagotchi.__version__, latest_ver))
            # input validation
            if user_input.lower() in ('y', 'yes'):
                if os.path.exists('/root/.auto-update'):
                    os.system("rm /root/.auto-update && systemctl restart pwnagotchi")
                else:
                    logging.error("You should make sure auto-update is enabled!")
                print("Okay, give me a couple minutes. Just watch pwnlog while you wait.")
            elif user_input.lower() in ('n', 'no'):  # using this elif for readability
                print("Okay, guess not!")
        else:
            print("You are currently on the latest release, v%s." % pwnagotchi.__version__)
        sys.exit(0)

    config = utils.load_config(args)

    if args.print_config:
        print(toml.dumps(config, encoder=DottedTomlEncoder()))
        sys.exit(0)

    from pwnagotchi.identity import KeyPair
    from pwnagotchi.agent import Agent
    from pwnagotchi.ui import fonts
    from pwnagotchi.ui.display import Display
    from pwnagotchi import grid
    from pwnagotchi import plugins

    pwnagotchi.config = config
    fs.setup_mounts(config)
    log.setup_logging(args, config)
    fonts.init(config)

    pwnagotchi.set_name(config['main']['name'])

    plugins.load(config)

    display = Display(config=config, state={'name': '%s>' % pwnagotchi.name()})

    if args.do_clear:
        do_clear(display)
        sys.exit(0)

    agent = Agent(view=display, config=config, keypair=KeyPair(view=display))

    def usr1_handler(*unused):
        logging.info('Received USR1 signal. Restart process ...')
        agent._restart("MANU" if args.do_manual else "AUTO")

    signal.signal(signal.SIGUSR1, usr1_handler)

    if args.do_manual:
        do_manual_mode(agent)
    else:
        do_auto_mode(agent)


if __name__ == '__main__':
    pwnagotchi_cli()
