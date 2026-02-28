import pwnagotchi.plugins as plugins
from pwnagotchi.utils import StatusFile
import logging
import os
import subprocess
import time
import socket
import threading
import glob
from flask import render_template_string


class AutoBackup(plugins.Plugin):
    __author__ = "WPA2"
    __version__ = "2.2"
    __license__ = "GPL3"
    __description__ = (
        "Backs up Pwnagotchi configuration and data, keeping recent backups."
    )

    # Hardcoded defaults for Pwnagotchi
    DEFAULT_FILES = [
        "/root/.api-report.json",
        "/root/.ssh",
        "/root/.bashrc",
        "/root/.profile",
        "/root/peers",
        "/etc/pwnagotchi/",
        "/etc/ssh/",
    ]

    DEFAULT_INTERVAL_SECONDS = 60 * 60  # 60 minutes
    DEFAULT_MAX_BACKUPS = 3
    DEFAULT_EXCLUDE = [
        "/etc/pwnagotchi/logs/*",
        "*.bak",
        "*.tmp",
    ]

    def __init__(self):
        self.ready = False
        self.tries = 0
        self.last_not_due_logged = 0
        self.status_file = "/root/.auto-backup"
        self.status = StatusFile(self.status_file)
        self.lock = threading.Lock()
        self.backup_in_progress = False
        self.hostname = socket.gethostname()
        self._agent = None

    def on_loaded(self):
        """Validate only required option: backup_location"""
        if (
            "backup_location" not in self.options
            or self.options["backup_location"] is None
        ):
            logging.error("AUTO-BACKUP: Option 'backup_location' is not set.")
            return

        self.hostname = socket.gethostname()

        # Read config with internal defaults - DO NOT modify self.options
        self.files = self.options.get("files", self.DEFAULT_FILES)
        self.interval_seconds = self.options.get(
            "interval_seconds", self.DEFAULT_INTERVAL_SECONDS
        )
        self.max_backups = self.options.get(
            "max_backups_to_keep", self.DEFAULT_MAX_BACKUPS
        )
        self.exclude = self.options.get("exclude", self.DEFAULT_EXCLUDE)
        self.include = self.options.get("include", [])

        # Handle commands: if old format, use correct default internally
        commands = self.options.get("commands", ["tar", "czf"])
        if isinstance(commands, str) or (
            isinstance(commands, list)
            and len(commands) == 1
            and isinstance(commands[0], str)
            and "{" in str(commands)
        ):
            logging.warning(
                "AUTO-BACKUP: Old command format detected in config, using default: tar czf"
            )
            self.commands = ["tar", "czf"]
        elif not commands:
            self.commands = ["tar", "czf"]
        else:
            self.commands = commands

        # Validate include paths if specified
        if self.include:
            if not isinstance(self.include, list):
                self.include = [self.include]

            for path in self.include:
                if not os.path.exists(path):
                    logging.warning(
                        f"AUTO-BACKUP: include path '{path}' does not exist, will skip if still missing at backup time"
                    )

        self.ready = True
        include_msg = (
            f", includes: {len(self.include)} additional path(s)"
            if self.include
            else ""
        )
        logging.info(
            f"AUTO-BACKUP: Plugin loaded for host '{self.hostname}'. Interval: 60min, Backups kept: {self.max_backups}{include_msg}"
        )

    def is_backup_due(self):
        """Check if backup is due based on interval."""
        try:
            last_backup = os.path.getmtime(self.status_file)
        except OSError:
            return True
        return (time.time() - last_backup) >= self.interval_seconds

    def _cleanup_old_backups(self):
        """Deletes the oldest backups if we exceed the limit."""
        try:
            backup_dir = self.options["backup_location"]
            max_keep = self.max_backups

            # Filter by this device's hostname
            search_pattern = os.path.join(
                backup_dir, f"{self.hostname}-backup-*.tar.gz"
            )
            files = glob.glob(search_pattern)

            if not files:
                logging.debug("AUTO-BACKUP: No backup files found for cleanup")
                return

            # Sort files by modification time (oldest first)
            files.sort(key=os.path.getmtime)

            # Calculate how many to delete
            if len(files) > max_keep:
                num_to_delete = len(files) - max_keep
                logging.info(
                    f"AUTO-BACKUP: Found {len(files)} backups, keeping {max_keep}, deleting {num_to_delete} old backup(s)..."
                )

                for old_file in files[:num_to_delete]:
                    try:
                        os.remove(old_file)
                        logging.info(
                            f"AUTO-BACKUP: Deleted: {os.path.basename(old_file)}"
                        )
                    except OSError as e:
                        logging.error(f"AUTO-BACKUP: Failed to delete {old_file}: {e}")

        except Exception as e:
            logging.error(f"AUTO-BACKUP: Cleanup error: {e}")

    def _run_backup_thread(self, agent, existing_files):
        """Execute backup in separate thread."""
        try:
            backup_location = self.options["backup_location"]

            # Create backup directory if it doesn't exist
            if not os.path.exists(backup_location):
                try:
                    os.makedirs(backup_location)
                    logging.info(
                        f"AUTO-BACKUP: Created backup directory: {backup_location}"
                    )
                except OSError as e:
                    logging.error(
                        f"AUTO-BACKUP: Failed to create backup directory: {e}"
                    )
                    return

            # Add timestamp to filename
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            backup_file = os.path.join(
                backup_location, f"{self.hostname}-backup-{timestamp}.tar.gz"
            )

            # Try to update display if agent is available
            if agent:
                try:
                    display = agent.view()
                    display.set("status", "Backing up...")
                    display.update()
                except:
                    pass

            logging.info(f"AUTO-BACKUP: Starting backup to {backup_file}...")

            # Build command
            command_list = list(self.commands)
            command_list.append(backup_file)

            # Add exclusions
            for pattern in self.exclude:
                command_list.append(f"--exclude={pattern}")

            # Add files to backup
            command_list.extend(existing_files)

            # Execute backup command
            process = subprocess.Popen(
                command_list,
                shell=False,
                stdin=None,
                stdout=open("/dev/null", "w"),
                stderr=subprocess.PIPE,
            )
            _, stderr_output = process.communicate()

            if process.returncode != 0:
                raise OSError(
                    f"Backup command failed with code {process.returncode}: {stderr_output.decode('utf-8').strip()}"
                )

            logging.info(f"AUTO-BACKUP: Backup successful: {backup_file}")

            # Run cleanup after successful backup
            self._cleanup_old_backups()

            # Try to update display if agent is available
            if agent:
                try:
                    display = agent.view()
                    display.set("status", "Backup done!")
                    display.update()
                except:
                    pass

            # Update status file timestamp
            self.status.update()

            # Reset try counter on success
            self.tries = 0

        except Exception as e:
            self.tries += 1
            logging.error(f"AUTO-BACKUP: Backup error (attempt {self.tries}): {e}")
        finally:
            self.backup_in_progress = False

    def on_ready(self, agent):
        """Called when Pwnagotchi is ready. Set up backup scheduler."""
        if not self.ready:
            return

        self._agent = agent

        # Start background scheduler thread
        scheduler_thread = threading.Thread(
            target=self._backup_scheduler_loop, daemon=True, name="AutoBackupScheduler"
        )
        scheduler_thread.start()

        logging.info("AUTO-BACKUP: Periodic backup scheduler started")

    def on_webhook(self, path, request):
        """Handle web UI requests."""
        if request.method == "GET":
            if path == "/" or not path:
                action_path = (
                    request.path
                    if request.path.endswith("/backup")
                    else "%s/backup" % request.path
                )
                ret = '<html><head><title>AUTO Backup</title><meta name="csrf_token" content="{{ csrf_token() }}"></head><body>'
                ret += "<h1>AUTO Backup</h1>"
                ret += "<p>Status: "
                if self.backup_in_progress:
                    ret += "<b>Backup in progress...</b>"
                else:
                    ret += "<b>Ready</b>"
                ret += "</p>"
                ret += '<form method="POST" action="%s">' % action_path
                ret += '<input id="csrf_token" name="csrf_token" type="hidden" value="{{ csrf_token() }}">'
                ret += '<input type="submit" value="Start Manual Backup" class="btn primary">'
                ret += "</form>"
                ret += "<hr>"
                ret += "<h2>Configuration</h2>"
                ret += '<table border="1" cellpadding="5">'
                ret += (
                    "<tr><td><b>Backup Location:</b></td><td>"
                    + self.options.get("backup_location", "Not set")
                    + "</td></tr>"
                )
                ret += (
                    "<tr><td><b>Interval:</b></td><td>"
                    + str(self.interval_seconds // 60)
                    + " minutes</b></td></tr>"
                )
                ret += (
                    "<tr><td><b>Max Backups:</b></td><td>"
                    + str(self.max_backups)
                    + "</td></tr>"
                )
                ret += (
                    "<tr><td><b>Include Paths:</b></td><td>"
                    + (", ".join(self.include) if self.include else "None")
                    + "</td></tr>"
                )
                ret += "</table>"
                ret += "</body></html>"
                return render_template_string(ret)

        elif request.method == "POST":
            if path == "backup" or path == "/backup":
                result = self.manual_backup(self._agent)
                ret = '<html><head><title>AUTO Backup</title><meta name="csrf_token" content="{{ csrf_token() }}"></head><body>'
                ret += "<h1>AUTO Backup</h1>"
                ret += "<p><b>" + result["status"] + "</b></p>"
                ret += '<a href="/plugins/auto_backup/">Back</a>'
                ret += "</body></html>"
                return render_template_string(ret)

        return "Not found"

    def _backup_scheduler_loop(self):
        """Background thread that checks if backup is due every minute."""
        while True:
            try:
                if self.ready:
                    agent = getattr(self, "_agent", None)
                    self._periodic_backup_check(agent)
                time.sleep(60)
            except Exception as e:
                logging.error(f"AUTO-BACKUP: Scheduler error: {e}")

    def _get_backup_files(self):
        """Collect all files to backup."""
        existing_files = list(filter(os.path.exists, self.files))
        if self.include:
            for path in self.include:
                if os.path.exists(path):
                    existing_files.append(path)
                    logging.debug(f"AUTO-BACKUP: Added include path: {path}")
        return existing_files

    def _periodic_backup_check(self, agent=None):
        """Periodic backup check."""
        if agent is None:
            agent = getattr(self, "_agent", None)

        if not self.ready or self.backup_in_progress:
            return

        if self.tries >= 3:
            return

        if not self.is_backup_due():
            return

        existing_files = self._get_backup_files()
        if not existing_files:
            logging.warning("AUTO-BACKUP: No files to backup exist")
            return

        self.backup_in_progress = True
        backup_thread = threading.Thread(
            target=self._run_backup_thread,
            args=(agent, existing_files),
            daemon=True,
            name="AutoBackupThread",
        )
        backup_thread.start()
        logging.debug("AUTO-BACKUP: Backup thread started")

    def manual_backup(self, agent):
        """Manually trigger a backup."""
        if self.backup_in_progress:
            return {"status": "Backup already in progress"}

        existing_files = self._get_backup_files()
        if not existing_files:
            return {"status": "No files to backup"}

        self.backup_in_progress = True
        backup_thread = threading.Thread(
            target=self._run_backup_thread,
            args=(agent, existing_files),
            daemon=True,
            name="AutoBackupThread",
        )
        backup_thread.start()
        logging.info("AUTO-BACKUP: Manual backup triggered")
        return {"status": "Backup started - check logs for details"}
