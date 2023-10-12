# Handles the commandline stuff

import os
import logging
import glob
import re
import shutil
from fnmatch import fnmatch
from pwnagotchi.utils import download_file, unzip, save_config, parse_version, md5
from pwnagotchi.plugins import default_path


def add_parsers(parser):
    """
    Adds the plugins subcommand to a given argparse.ArgumentParser
    """
    subparsers = parser.add_subparsers()
    # pwnagotchi google
    parser_plugins = subparsers.add_parser('google')
    plugin_subparsers = parser_plugins.add_subparsers(dest='googlecmd')

    # pwnagotchi plugins search
    parser_plugins_search = plugin_subparsers.add_parser('search', help='Search for pwnagotchi plugins')
    parser_plugins_search.add_argument('pattern', type=str, help="Search expression (wildcards allowed)")

    return parser


def used_plugin_cmd(args):
    """
    Checks if the plugins subcommand was used
    """
    return hasattr(args, 'plugincmd')


def handle_cmd(args, config):
    """
    Parses the arguments and does the thing the user wants
    """
    if args.plugincmd == 'update':
        return update(config)
    elif args.plugincmd == 'search':
        args.installed = True # also search in installed plugins
        return list_plugins(args, config, args.pattern)
    elif args.plugincmd == 'install':
        return install(args, config)
    elif args.plugincmd == 'uninstall':
        return uninstall(args, config)
    elif args.plugincmd == 'list':
        return list_plugins(args, config)
    elif args.plugincmd == 'enable':
        return enable(args, config)
    elif args.plugincmd == 'disable':
        return disable(args, config)
    elif args.plugincmd == 'upgrade':
        return upgrade(args, config, args.pattern)
    elif args.plugincmd == 'edit':
        return edit(args, config)

    raise NotImplementedError()