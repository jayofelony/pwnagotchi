# Handles the commandline stuff

import pydrive2
from pydrive2.auth import GoogleAuth
import logging
import os


def add_parsers(subparsers):
    """
    Adds the plugins subcommand to a given argparse.ArgumentParser
    """
    #subparsers = parser.add_subparsers()
    # pwnagotchi google
    parser_google = subparsers.add_parser('google')
    google_subparsers = parser_google.add_subparsers(dest='googlecmd')

    # pwnagotchi google auth
    parser_google_auth = google_subparsers.add_parser('login', help='Login to Google')

    # pwnagotchi google refresh token
    parser_google_refresh = google_subparsers.add_parser('refresh', help="Refresh Google authentication token")
    return subparsers


def used_google_cmd(args):
    """
    Checks if the plugins subcommand was used
    """
    return hasattr(args, 'googlecmd')


def handle_cmd(args):
    """
    Parses the arguments and does the thing the user wants
    """
    if args.googlecmd == 'login':
        return auth()
    elif args.googlecmd == 'refresh':
        return refresh()
    raise NotImplementedError()


def auth():
    # start authentication process
    user_input = input("By completing these steps you give pwnagotchi access to your personal Google Drive!\n"
                       "Personal credentials will be stored only locally for automated verification in the future.\n"
                       "No one else but you have access to these.\n"
                       "Do you agree? \n\n[y(es)/n(o)]\n"
                       "Answer: ")
    if user_input.lower() in ('y', 'yes'):
        if not os.path.exists("/root/client_secrets.json"):
            logging.error("client_secrets.json not found in /root. Please RTFM!")
            return 0
        try:
            gauth = GoogleAuth(settings_file="/root/settings.yaml")
            print(gauth.GetAuthUrl())
            user_input = input("Please copy this URL into a browser, "
                               "complete the verification and then copy/paste the code from addressbar.\n\n"
                               "Code: ")
            gauth.Auth(user_input)
            gauth.SaveCredentialsFile("/root/credentials.json")
        except Exception as e:
            logging.error(f"Error: {e}")
    return 0


def refresh():
    # refresh token for x amount of time (seconds)
    gauth = GoogleAuth(settings_file="/root/settings.yaml")
    try:
        # Try to load saved client credentials
        gauth.LoadCredentialsFile("/root/credentials.json")
        if gauth.access_token_expired:
            if gauth.credentials is not None:
                try:
                    # Refresh the token
                    gauth.Refresh()
                    print("Succesfully refresh access token ..")
                except pydrive2.auth.RefreshError:
                    print(gauth.GetAuthUrl())
                    user_input = input("Please copy this URL into a browser, "
                                       "complete the verification and then copy/paste the code from addressbar.\n\n"
                                       "Code: ")
                    gauth.Auth(user_input)
            else:
                print(gauth.GetAuthUrl())
                user_input = input("Please copy this URL into a browser, "
                                   "complete the verification and then copy/paste the code from addressbar.\n\n"
                                   "Code: ")
                gauth.Auth(user_input)
    except pydrive2.auth.InvalidCredentialsError:
        print(gauth.GetAuthUrl())
        user_input = input("Please copy this URL into a browser, "
                           "complete the verification and then copy/paste the code from addressbar.\n\n"
                           "Code: ")
        gauth.Auth(user_input)
    gauth.SaveCredentialsFile("/root/credentials.json")
    gauth.Authorize()
    print("No refresh required ..")
    return 0
