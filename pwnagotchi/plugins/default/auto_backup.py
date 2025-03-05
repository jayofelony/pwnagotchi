import pwnagotchi.plugins as plugins
from pwnagotchi.utils import StatusFile
import logging
import os
import subprocess
import time
import socket

class AutoBackup(plugins.Plugin):
    __author__ = 'WPA2'
    __version__ = '1.1.3'
    __license__ = 'GPL3'
    __description__ = 'Backs up files when internet is available, with support for excludes.'

    def __init__(self):
        self.ready = False
        self.tries = 0
        # Used to throttle repeated log messages for "backup not due yet"
        self.last_not_due_logged = 0
        # Store the status file path separately.
        self.status_file = '/root/.auto-backup'
        self.status = StatusFile(self.status_file)

    def on_loaded(self):
        required_options = ['files', 'interval', 'backup_location', 'max_tries']
        for opt in required_options:
            if opt not in self.options or self.options[opt] is None:
                logging.error(f"AUTO-BACKUP: Option '{opt}' is not set.")
                return

        # If no custom command(s) are provided, use the default plain tar command.
        # The command includes a placeholder for {excludes} so that if no excludes are set, it will be empty.
        if 'commands' not in self.options or not self.options['commands']:
            self.options['commands'] = ["tar cf {backup_file} {excludes} {files}"]
        self.ready = True
        logging.info("AUTO-BACKUP: Successfully loaded.")

    def get_interval_seconds(self):
        """
        Convert the interval option into seconds.
        Supports:
          - "daily" for 24 hours,
          - "hourly" for 60 minutes,
          - or a numeric value (interpreted as minutes).
        """
        interval = self.options['interval']
        if isinstance(interval, str):
            if interval.lower() == "daily":
                return 24 * 60 * 60
            elif interval.lower() == "hourly":
                return 60 * 60
            else:
                try:
                    minutes = float(interval)
                    return minutes * 60
                except ValueError:
                    logging.error("AUTO-BACKUP: Invalid interval format. Defaulting to daily interval.")
                    return 24 * 60 * 60
        elif isinstance(interval, (int, float)):
            return float(interval) * 60
        else:
            logging.error("AUTO-BACKUP: Unrecognized type for interval. Defaulting to daily interval.")
            return 24 * 60 * 60

    def is_backup_due(self):
        """
        Determines if enough time has passed since the last backup.
        If the status file does not exist, a backup is due.
        """
        interval_sec = self.get_interval_seconds()
        try:
            last_backup = os.path.getmtime(self.status_file)
        except OSError:
            # Status file doesn't exist—backup is due.
            return True
        now = time.time()
        return (now - last_backup) >= interval_sec

    def on_internet_available(self, agent):
        if not self.ready:
            return

        if self.options['max_tries'] and self.tries >= self.options['max_tries']:
            logging.info("AUTO-BACKUP: Maximum tries reached, skipping backup.")
            return

        if not self.is_backup_due():
            now = time.time()
            # Log "backup not due" only once every 60 seconds.
            if now - self.last_not_due_logged > 60:
                logging.info("AUTO-BACKUP: Backup not due yet based on the interval.")
                self.last_not_due_logged = now
            return

        # Only include files/directories that exist to prevent errors.
        existing_files = list(filter(lambda f: os.path.exists(f), self.options['files']))
        if not existing_files:
            logging.warning("AUTO-BACKUP: No files found to backup.")
            return
        files_to_backup = " ".join(existing_files)

        # Build excludes string if configured.
        # Use get() so that if 'exclude' is missing or empty, we default to an empty list.
        excludes = ""
        exclude_list = self.options.get('exclude', [])
        if exclude_list:
            for pattern in exclude_list:
                excludes += f" --exclude='{pattern}'"

        # Get the backup location from config.
        backup_location = self.options['backup_location']

        # Retrieve the global config from agent. If agent.config is callable, call it.
        global_config = getattr(agent, 'config', None)
        if callable(global_config):
            global_config = global_config()
        if global_config is None:
            global_config = {}
        pwnagotchi_name = global_config.get('main', {}).get('name', socket.gethostname())
        backup_file = os.path.join(backup_location, f"{pwnagotchi_name}-backup.tar")

        try:
            display = agent.view()
            logging.info("AUTO-BACKUP: Starting backup process...")
            display.set('status', 'Backing up ...')
            display.update()

            # Execute each backup command.
            for cmd in self.options['commands']:
                formatted_cmd = cmd.format(backup_file=backup_file, files=files_to_backup, excludes=excludes)
                logging.info(f"AUTO-BACKUP: Running command: {formatted_cmd}")
                process = subprocess.Popen(
                    formatted_cmd,
                    shell=True,
                    stdin=None,
                    stdout=open("/dev/null", "w"),
                    stderr=subprocess.STDOUT,
                    executable="/bin/bash"
                )
                process.wait()
                if process.returncode > 0:
                    raise OSError(f"Command failed with return code: {process.returncode}")

            logging.info(f"AUTO-BACKUP: Backup completed successfully. File created at {backup_file}")
            display.set('status', 'Backup done!')
            display.update()
            self.status.update()
        except OSError as os_e:
            self.tries += 1
            logging.error(f"AUTO-BACKUP: Backup error: {os_e}")
            display.set('status', 'Backup failed!')
            display.update()
