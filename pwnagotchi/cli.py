import logging
import argparse
import time
import signal
import sys
import toml
import dbus
import dbus.mainloop.glib

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
                        # send an association frame to get a PMKID
                        agent.associate(ap)
                        # deauth all client stations to get a full handshake
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
        if os.geteuid() != 0:
            os.execvp("sudo", ["sudo", "pwnagotchi", "--wizard"])

        def is_valid_hostname(hostname):
            if len(hostname) > 255:
                return False
            if hostname.endswith("."):
                hostname = hostname[:-1]  # strip trailing dot if present
            allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
            return all(allowed.match(x) for x in hostname.split("."))

        def ask_yes_no(prompt):
            """Keeps asking until a valid yes/no is entered."""
            while True:
                val = input(prompt).strip().lower()
                if val in ("y", "yes"):
                    return True
                elif val in ("n", "no"):
                    return False
                else:
                    print("Invalid input. Please answer with Y or N.")

        def ask_non_empty(prompt, default=None, validator=None):
            """
            Asks for a value, optionally with a default.
            Retries on empty or invalid input (if a validator is provided).
            """
            while True:
                val = input(prompt).strip()
                if val == "" and default is not None:
                    # If empty but default is provided, use default
                    return default
                if val == "":
                    print("A value is required. Please try again.")
                    continue
                if validator is not None:
                    if not validator(val):
                        print("Invalid input. Please try again.")
                        continue
                return val

        def ask_positive_int(prompt):
            """Retries until the user provides a non-negative integer."""
            while True:
                val = input(prompt).strip()
                if not val.isdigit():
                    print("Invalid number. Please enter a positive integer.")
                    continue
                int_val = int(val)
                if int_val < 0:
                    print("Please enter a non-negative (or positive) integer.")
                    continue
                return int_val

        def setup_bluetooth_dbus():
            """
            Returns the MAC if successful, or None if the user skipped/failure.
            """

            try:
                # Initialize DBus main loop
                dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

                system_bus = dbus.SystemBus()

                # Get the BlueZ ObjectManager
                manager = dbus.Interface(
                    system_bus.get_object("org.bluez", "/"),
                    "org.freedesktop.DBus.ObjectManager"
                )

                # Find the first available Bluetooth adapter (usually /org/bluez/hci0)
                objects = manager.GetManagedObjects()
                adapter_path = None
                for path, interfaces in objects.items():
                    if "org.bluez.Adapter1" in interfaces:
                        adapter_path = path
                        break

                if not adapter_path:
                    print("No Bluetooth adapter found. Skipping automatic Bluetooth setup.")
                    return None

                # Power on, discoverable, pairable
                adapter_props = dbus.Interface(
                    system_bus.get_object("org.bluez", adapter_path),
                    "org.freedesktop.DBus.Properties"
                )
                adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
                adapter_props.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(True))
                adapter_props.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(True))

                adapter_iface = dbus.Interface(
                    system_bus.get_object("org.bluez", adapter_path),
                    "org.bluez.Adapter1"
                )

                #Tell the user to open bluetooth settings on their phone to make it discoverable
                print("Please open Bluetooth settings on your phone and make it discoverable.")
                print("Press Enter when ready.")
                input()
                # Start Discovery
                print("\nStarting Bluetooth discovery for ~10 seconds...")
                adapter_iface.StartDiscovery()
                time.sleep(10)
                adapter_iface.StopDiscovery()

                # Retrieve an updated list of objects to see discovered devices
                objects = manager.GetManagedObjects()
                device_list = []  # We'll store tuples of (MAC, device_path)

                for path, interfaces in objects.items():
                    if "org.bluez.Device1" in interfaces:
                        # Retrieve the device's MAC from DBus properties
                        dev_props = interfaces["org.bluez.Device1"]
                        mac_addr = dev_props.get("Address")
                        name = dev_props.get("Name", "Unknown")
                        device_list.append((mac_addr, name, path))

                if not device_list:
                    print("No devices discovered. Make sure your phone was in discoverable mode.")
                    return None

                print("\nDiscovered devices:")
                for idx, (mac_addr, name, _) in enumerate(device_list):
                    print(f"  [{idx}]  {mac_addr}  '{name}'")

                # Ask the user to pick by index or MAC
                choice = input("\nEnter index of your phone (or type a MAC address): ").strip()

                if choice.isdigit():
                    choice_index = int(choice)
                    if choice_index < 0 or choice_index >= len(device_list):
                        print("Invalid index selected. Aborting.")
                        return None
                    chosen_mac = device_list[choice_index][0]
                    device_path = device_list[choice_index][2]
                else:
                    # the user typed a MAC address
                    #  to find it in the device_list
                    dev_found = [(m, p) for (m, _, p) in device_list if m.lower() == choice.lower()]
                    if not dev_found:
                        print(f"The MAC address '{choice}' was not found in the list")
                        retry = ask_yes_no("Would you like to try again?\n\n[Y/N]: ")
                        if not retry:
                            return None
                        return setup_bluetooth_dbus()
                    chosen_mac, device_path = dev_found[0]

                # Attempt pairing
                print(f"\nAttempting to Pair with {chosen_mac} ...\n")
                dev_obj = system_bus.get_object("org.bluez", device_path)
                dev_iface = dbus.Interface(dev_obj, "org.bluez.Device1")

                try:
                    dev_iface.Pair()
                except dbus.DBusException as e:
                    print(f"Pairing failed: {e}\nYou may need to confirm on the phone or try again.")
                    # We'll continue and attempt to trust anyway
                    pass

                # Mark the device as trusted
                dev_props_iface = dbus.Interface(dev_obj, "org.freedesktop.DBus.Properties")
                dev_props_iface.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))

                print("Successfully set the device as Trusted.\nPairing steps are complete!")
                return chosen_mac
            except Exception as e:
                print(f"\nEncountered error during DBus Bluetooth setup: {e}")
                return None

        def run_wizard():
            """
            Runs the interactive wizard for building a new pwnagotchi config
            """

            pwn_restore = ask_yes_no("Do you want to restore the previous configuration?\n\n[Y/N]: ")
            if pwn_restore:
                os.system("cp -f /etc/pwnagotchi/config.toml.bak /etc/pwnagotchi/config.toml")
                print("Your previous configuration is restored, and I will restart in 5 seconds.")
                time.sleep(5)
                os.system("service pwnagotchi restart")
                return

            pwn_check = ask_yes_no(
                "This will create a new configuration file and overwrite your current backup, are you sure?\n\n[Y/N]: "
            )
            if not pwn_check:
                print("Ok, doing nothing.")
                return

            # Move existing config to backup
            os.system("mv -f /etc/pwnagotchi/config.toml /etc/pwnagotchi/config.toml.bak")
            with open("/etc/pwnagotchi/config.toml", "a+") as f:
                f.write("# Do not edit this file if you do not know what you are doing!!!\n\n")

                # Ask for pwnagotchi name
                print("\nWelcome to the interactive installation of your personal Pwnagotchi configuration!\n"
                      "My name is Jayofelony, how may I call you?\n")
                pwn_name = ask_non_empty(
                    "Pwnagotchi name (no spaces): ",
                    default="Pwnagotchi",
                    validator=lambda val: is_valid_hostname(val) or val == ""
                )
                if pwn_name == "Pwnagotchi":
                    print("Defaulting to Pwnagotchi.")
                    print("I shall go by Pwnagotchi from now on!")
                else:
                    print(f"I shall go by {pwn_name} from now on!")
                f.write(f'main.name = "{pwn_name}"\n')

                # Whitelist networks
                pwn_whitelist_count = ask_positive_int(
                    "How many networks do you want to whitelist?\n"
                    "Each SSID or BSSID counts as 1 entry.\n"
                    "Amount of networks: "
                )
                if pwn_whitelist_count > 0:
                    f.write("main.whitelist = [\n")
                    for _ in range(pwn_whitelist_count):
                        ssid = input("SSID (Name) (default: ''): ").strip()
                        bssid_amount = ask_positive_int("How many BSSIDs (MAC addresses) do you want to whitelist for "
                                                        f"the SSID '{ssid}'? (default: 1): ")
                        if bssid_amount == 0:
                            bssid_amount = 1
                        for y in range(bssid_amount):
                            bssid = input(f"BSSID #{y+1} (MAC) for {ssid}: ").strip()
                            if bssid:
                                f.write(f'\t"{bssid}",\n')
                        if ssid:
                            f.write(f'\t"{ssid}",\n')
                    f.write("]\n")

                # Bluetooth tether
                pwn_bluetooth = ask_yes_no("Do you want to enable BT-Tether?\n\n[Y/N]: ")
                if pwn_bluetooth:
                    f.write("main.plugins.bt-tether.enabled = true\n\n")

                    # phone name is required
                    pwn_bluetooth_phone_name = ask_non_empty(
                        "What name does your phone use in BT settings?\n(This is required): "
                    )
                    f.write(f'main.plugins.bt-tether.phone-name = "{pwn_bluetooth_phone_name}"\n')

                    # Keep retrying for valid device: 'android' or 'ios'
                    while True:
                        pwn_bluetooth_device = input("What device do you use? [android/ios]\nDevice: ").strip().lower()
                        if pwn_bluetooth_device in ["android", "ios"]:
                            f.write(f'main.plugins.bt-tether.phone = "{pwn_bluetooth_device}"\n')
                            if pwn_bluetooth_device == "android":
                                f.write('main.plugins.bt-tether.ip = "192.168.44.44"\n')
                            else:  # ios
                                f.write('main.plugins.bt-tether.ip = "172.20.10.6"\n')
                            break
                        else:
                            print("Invalid device. Please enter 'android' or 'ios'.")

                    # Now do the DBus-based pairing/trusting steps
                    phone_mac = setup_bluetooth_dbus()
                    if phone_mac:
                        # Write the chosen MAC into the config
                        f.write(f'main.plugins.bt-tether.mac = "{phone_mac}"\n')
                    else:
                        f.write('main.plugins.bt-tether.mac = ""\n')

                # Display settings
                pwn_display_enabled = ask_yes_no("Do you want to enable a display?\n\n[Y/N]: ")
                if pwn_display_enabled:
                    f.write("ui.display.enabled = true\n")
                    pwn_display_type = input(
                        "What display do you use?\n\n"
                        "(Be sure to check for the correct display type @\n"
                        " https://github.com/jayofelony/pwnagotchi/blob/master/pwnagotchi/utils.py#L240-L501 )\n\n"
                        "Display type: "
                    ).strip()
                    if pwn_display_type:
                        f.write(f'ui.display.type = "{pwn_display_type}"\n')

                    invert_colors = ask_yes_no(
                        "\nDo you want to have a white background color?\n"
                        "N = Black background\n"
                        "Y = White background\n\n[Y/N]: "
                    )
                    if invert_colors:
                        f.write("ui.invert = true\n")

            # Final messages
            if pwn_bluetooth:
                if pwn_bluetooth_device == "android":
                    print("\nTo visit the webui when connected via Bluetooth tether on Android, go to: http://192.168.44.44:8080")
                else:
                    print("\nTo visit the webui when connected via Bluetooth tether on iOS, go to: http://172.20.10.6:8080")

            print("\nYour configuration is done, and I will restart in 5 seconds.")
            time.sleep(5)
            os.system("service pwnagotchi restart")

        # Run the refactored wizard
        run_wizard()
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
