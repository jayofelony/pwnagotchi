import logging
import os
import shutil
import time
import pwnagotchi.plugins as plugins
import pwnagotchi
import pydrive2
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from threading import Lock
from pwnagotchi.utils import StatusFile
import zipfile


class GdriveSync(plugins.Plugin):
    __author__ = '@jayofelony & Moist'
    __version__ = '1.4'
    __license__ = 'GPL3'
    __description__ = 'A plugin to backup various pwnagotchi files and folders to Google Drive. Once every hour from loading plugin.'

    def __init__(self):
        self.options = dict()
        self.lock = Lock()
        self.internet = False
        self.ready = False
        self.status = StatusFile('/root/.gdrive-backup')
        self.backup = True
        self.backupfiles = [
            '/root/brain.json',
            '/root/.api-report.json',
            '/home/pi/handshakes',
            '/root/peers',
            '/etc/pwnagotchi',
            '.etc/profile/',
            '/usr/local/share/pwnagotchi/custom-plugins',
            '/boot/firmware/config.txt',
            '/boot/firmware/cmdline.txt'
        ]

    def on_loaded(self):
        """
            Called when the plugin is loaded
        """
        # client_secrets.json needs to be not empty
        if os.stat("/root/client_secrets.json").st_size == 0:
            logging.error("[gDriveSync] /root/client_secrets.json is empty. Please RTFM!")
            return
        # backup file, so we know if there has been a backup made at least once before.
        if not os.path.exists("/root/.gdrive-backup"):
            self.backup = False

        try:
            gauth = GoogleAuth(settings_file="/root/settings.yaml")
            gauth.LoadCredentialsFile("/root/credentials.json")
            if gauth.credentials is None:
                # Authenticate if they're not there
                gauth.LocalWebserverAuth()
            elif gauth.access_token_expired:
                # Refresh them if expired
                gauth.Refresh()
            gauth.SaveCredentialsFile("/root/credentials.json")
            gauth.Authorize()

            # Create GoogleDrive instance
            self.drive = GoogleDrive(gauth)

            # if backup file does not exist, we will check for backup folder on gdrive.
            if not self.backup:
                # Use self.options['backup_folder'] as the folder ID where backups are stored
                backup_folder = self.create_folder_if_not_exists(self.options['backup_folder'])

                # Continue with the rest of the code using backup_folder_id
                backup_folder_file_list = self.drive.ListFile({'q': f"'{backup_folder}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false"}).GetList()
                if not backup_folder_file_list:
                    # Handle the case where no files were found
                    # logging.warning(f"[gDriveSync] No files found in the folder with ID {root_file_list} and {pwnagotchi_file_list}")
                    if self.options['backupfiles'] is not None:
                        self.backupfiles = self.backupfiles + self.options['backupfiles']
                    self.backup_files(self.backupfiles, '/home/pi/backup')

                    # Create a zip archive of the /backup folder
                    zip_file_path = os.path.join('/home/pi', 'backup.zip')
                    with zipfile.ZipFile(zip_file_path, 'w') as zip_ref:
                        for root, dirs, files in os.walk('/home/pi/backup'):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, '/home/pi/backup')
                                zip_ref.write(file_path, arcname=arcname)

                    # Upload the zip archive to Google Drive
                    self.upload_to_gdrive(zip_file_path, self.get_folder_id_by_name(self.drive, self.options['backup_folder']))
                    self.backup = True
                    self.status.update()

                # Specify the local backup path
                local_backup_path = '/home/pi/'

                # Download the zip archive from Google Drive
                zip_file_id = self.get_latest_backup_file_id(self.options['backup_folder'])
                if zip_file_id:
                    zip_file = self.drive.CreateFile({'id': zip_file_id})
                    zip_file.GetContentFile(os.path.join(local_backup_path, 'backup.zip'))

                    logging.info("[gDriveSync] Downloaded backup.zip from Google Drive")

                    # Extract the zip archive to the root directory
                    with zipfile.ZipFile(os.path.join(local_backup_path, 'backup.zip'), 'r') as zip_ref:
                        zip_ref.extractall('/')

                    self.status.update()
                    shutil.rmtree("/home/pi/backup")
                    os.remove("/home/pi/backup.zip")
                    self.ready = True
                    logging.info("[gdrivesync] loaded")
                    # Restart so we can start opwngrid with the backup id
                    pwnagotchi.restart("AUTO")

                # all set, gdriveSync is ready to run
            self.ready = True
            logging.info("[gdrivesync] loaded")
        except Exception as e:
            logging.error(f"Error: {e}")
            self.ready = False

    def get_latest_backup_file_id(self, backup_folder_id):
        backup_folder_id = self.get_folder_id_by_name(self.drive, backup_folder_id)
        # Retrieve the latest backup file in the Google Drive folder
        file_list = self.drive.ListFile({'q': f"'{backup_folder_id}' in parents and trashed=false"}).GetList()

        if file_list:
            # Sort the files by creation date in descending order
            latest_backup = max(file_list, key=lambda file: file['createdDate'])
            return latest_backup['id']
        else:
            return None

    def get_folder_id_by_name(self, drive, folder_name, parent_folder_id=None):
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"

        file_list = drive.ListFile({'q': query}).GetList()
        for file in file_list:
            if file['title'] == folder_name:
                return file['id']
        return None

    def create_folder_if_not_exists(self, backup_folder_name):
        # First, try to retrieve the existing *BACKUP_FOLDER* folder
        backup_folder_id = self.get_folder_id_by_name(self.drive, backup_folder_name)

        if backup_folder_id is None:
            # If not found, create *BACKUP_FOLDER*
            backup_folder = self.drive.CreateFile(
                {'title': backup_folder_name, 'mimeType': 'application/vnd.google-apps.folder'})
            backup_folder.Upload()
            backup_folder_id = backup_folder['id']
            logging.info(f"[gDriveSync] Created folder '{backup_folder_name}' with ID: {backup_folder_id}")

        return backup_folder_id

    def on_unload(self, ui):
        """
            Called when the plugin is unloaded
        """
        logging.info("[gdrivesync] unloaded")

    def on_internet_available(self, agent):
        """
            Called when internet is available
        """
        self.internet = True

    def on_handshake(self, agent, filename, access_point, client_station):
        display = agent.view()
        if not self.ready and not self.internet:
            return
        if self.lock.locked():
            return
        with self.lock:
            if self.status.newer_then_hours(self.options['interval']):
                logging.debug("[update] last check happened less than %d hours ago" % self.options['interval'])
                return

            logging.info("[gdrivesync] new handshake captured, backing up to gdrive")
            if self.options['backupfiles'] is not None:
                self.backupfiles = self.backupfiles + self.options['backupfiles']
            self.backup_files(self.backupfiles, '/home/pi/backup')

            # Create a zip archive of the /backup folder
            zip_file_path = os.path.join('/home/pi', 'backup.zip')
            with zipfile.ZipFile(zip_file_path, 'w') as zip_ref:
                for root, dirs, files in os.walk('/home/pi/backup'):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, '/home/pi/backup')
                        zip_ref.write(file_path, arcname=arcname)

            # Upload the zip archive to Google Drive
            self.upload_to_gdrive(zip_file_path, self.get_folder_id_by_name(self.drive, self.options['backup_folder']))
            display.on_uploading("Google Drive")

            # Cleanup the local zip file
            os.remove(zip_file_path)
            shutil.rmtree("/home/pi/backup")
            self.status.update()
            display = agent.view()
            display.update(force=True, new_data={'Backing up to gdrive ...'})

    def backup_files(self, paths, dest_path):
        for src_path in paths:
            try:
                if os.path.exists(src_path):
                    dest_relative_path = os.path.relpath(src_path, '/')
                    dest = os.path.join(dest_path, dest_relative_path)

                    if os.path.isfile(src_path):
                        # If it's a file, copy it to the destination preserving the directory structure
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        # Check if the destination file already exists
                        if os.path.exists(dest):
                            # If it exists, remove it to overwrite
                            os.remove(dest)
                    elif os.path.isdir(src_path):
                        # If it's a directory, copy the entire directory to the destination
                        shutil.copytree(src_path, dest)
            except Exception as e:
                logging.error(f"[gDriveSync] Error during backup_path: {e}")

    def upload_to_gdrive(self, backup_path, gdrive_folder):
        try:
            # Upload zip-file to google drive
            # Create a GoogleDriveFile instance for the zip file
            zip_file = self.drive.CreateFile({'title': 'backup.zip', 'parents': [{'id': gdrive_folder}]})

            # Set the content of the file to the zip file
            zip_file.SetContentFile(backup_path)

            # Upload the file to Google Drive
            zip_file.Upload()
            logging.info(f"[gDriveSync] Backup uploaded to Google Drive")
        except pydrive2.files.ApiRequestError as api_error:
            self.handle_upload_error(api_error, backup_path, gdrive_folder)
        except Exception as e:
            logging.error(f"[gDriveSync] Error during upload_to_gdrive: {e}")

    def handle_upload_error(self, api_error, backup_path, gdrive_folder):
        if 'Rate Limit Exceeded' in str(api_error):
            logging.warning("[gDriveSync] Rate limit exceeded. Waiting for some time before retrying...")
            # We set to 100 seconds, because there is a limit 20k requests per 100s per user
            time.sleep(100)  # You can adjust the sleep duration based on your needs
            self.upload_to_gdrive(backup_path, gdrive_folder)
        else:
            logging.error(f"[gDriveSync] API Request Error: {api_error}")
