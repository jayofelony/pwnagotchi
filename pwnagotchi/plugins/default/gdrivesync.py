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
from pwnagotchi.utils import StatusFile, parse_version as version_to_tuple


class GdriveSync(plugins.Plugin):
    __author__ = '@jayofelony'
    __version__ = '1.0'
    __license__ = 'GPL3'
    __description__ = 'A plugin to backup various pwnagotchi files and folders to Google Drive. Once every hour from loading plugin.'
    __dependencies__ = {
        'pip': ['pydrive2']
    }

    def __init__(self):
        self.lock = Lock()
        self.internet = False
        self.ready = False
        self.drive = None
        self.status = StatusFile('/root/.gdrive-backup')
        self.backup = True
        self.backupfiles = [
            '/root/brain.nn',
            '/root/brain.json',
            '/root/.api-report.json',
            '/root/handshakes',
            '/root/peers',
            '/etc/pwnagotchi'
        ]

    def on_loaded(self):
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
                backup_folder, root_folder, pwnagotchi_folder = self.create_folder_if_not_exists(self.options['backup_folder'])

                # Continue with the rest of the code using backup_folder_id
                root_file_list = self.drive.ListFile({
                                                               'q': f"'{root_folder}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false"}).GetList()
                pwnagotchi_file_list = self.drive.ListFile({'q': f"'{pwnagotchi_folder}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false"}).GetList()

                if not (root_file_list or pwnagotchi_file_list):
                    # Handle the case where no files were found
                    # logging.warning(f"[gDriveSync] No files found in the folder with ID {root_file_list} and {pwnagotchi_file_list}")
                    if self.options['backupfiles'] is not None:
                        self.backupfiles = self.backupfiles + self.options['backupfiles']
                    self.backup_files(self.backupfiles, '/backup')

                    self.upload_to_gdrive('/backup', self.options['backup_folder'],backup_folder, root_folder, pwnagotchi_folder)
                    self.backup = True

                # Specify the local backup path
                local_backup_path = '/'

                # Create the local backup directory if it doesn't exist
                os.makedirs(local_backup_path, exist_ok=True)

                # Download each file in the /root folder
                for root_file in root_file_list:
                    local_file_path = os.path.join(local_backup_path, root_file['title'])
                    root_file.GetContentFile(local_file_path)
                    logging.info(f"[gDriveSync] Downloaded {root_file['title']} from Google Drive")

                # Download each file in the /etc/pwnagotchi folder
                for pwnagotchi_file in pwnagotchi_file_list:
                    local_file_path = os.path.join(local_backup_path, pwnagotchi_file['title'])
                    pwnagotchi_file.GetContentFile(local_file_path)
                    logging.info(f"[gDriveSync] Downloaded {pwnagotchi_file['title']} from Google Drive")

                # Optionally, you can use the downloaded files as needed
                # For example, you can copy them to the corresponding directories
                self.backup = True
                self.status.update()
                # reboot so we can start opwngrid with backup id
                pwnagotchi.reboot()

            # all set, gdriveSync is ready to run
            self.ready = True
            logging.info("[gdrivesync] loaded")
        except Exception as e:
            logging.error(f"Error: {e}")
            self.ready = False

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

            # Now, try to retrieve or create /*BACKUP_FOLDER*/root
            root_folder_id = self.get_or_create_subfolder('root', backup_folder_id)

            # Now, try to retrieve or create /*BACKUP_FOLDER*/etc
            etc_folder_id = self.get_or_create_subfolder('etc', backup_folder_id)

            # Now, try to retrieve or create /*BACKUP_FOLDER*/etc/pwnagotchi
            pwnagotchi_folder_id = self.get_or_create_subfolder('pwnagotchi', etc_folder_id)

            return backup_folder_id, root_folder_id, pwnagotchi_folder_id  # Return the IDs of both root and pwnagotchi folders
        else:
            # If found, also try to retrieve or create /*BACKUP_FOLDER*/root
            root_folder_id = self.get_or_create_subfolder('root', backup_folder_id)

            # Also, try to retrieve or create /*BACKUP_FOLDER*/etc
            etc_folder_id = self.get_or_create_subfolder('etc', backup_folder_id)

            # Also, try to retrieve or create /*BACKUP_FOLDER*/etc/pwnagotchi
            pwnagotchi_folder_id = self.get_or_create_subfolder('pwnagotchi', etc_folder_id)

            return backup_folder_id, root_folder_id, pwnagotchi_folder_id  # Return the IDs of both root and pwnagotchi folders

    def get_or_create_subfolder(self, subfolder_name, parent_folder_id):
        # Try to retrieve the subfolder
        subfolder_id = self.get_folder_id_by_name(self.drive, subfolder_name, parent_folder_id)

        if subfolder_id is None:
            # If not found, create the subfolder
            subfolder = self.drive.CreateFile(
                {'title': subfolder_name, 'mimeType': 'application/vnd.google-apps.folder',
                 'parents': [{'id': parent_folder_id}]})
            subfolder.Upload()
            subfolder_id = subfolder['id']
            logging.info(f"[gDriveSync] Created folder '{subfolder_name}' with ID: {subfolder_id}")

        return subfolder_id

    def on_unload(self, ui):
        logging.info("[gdrivesync] unloaded")

    def on_internet_available(self, agent):
        self.internet = True

    def on_handshake(self, agent):
        if self.lock.locked():
            return
        with self.lock:
            if not self.ready and not self.internet:
                return
            try:
                if self.status.newer_then_hours(self.options['interval']):
                    logging.debug("[update] last check happened less than %d hours ago" % self.options['interval'])
                    return

                logging.info("[gdrivesync] new handshake captured, backing up to gdrive")
                if self.options['backupfiles'] is not None:
                    self.backupfiles = self.backupfiles + self.options['backupfiles']
                self.backup_files(self.backupfiles, '/backup')

                self.upload_to_gdrive('/backup', self.options['backup_folder'])
                self.status.update()
                display = agent.view()
                display.update(force=True, new_data={'Backing up to gdrive ...'})
            except Exception as e:
                logging.error(f"[gDriveSync] Error during handshake processing: {e}")

    def backup_files(self, paths, dest_path):
        for src_path in paths:
            self.backup_path(src_path, dest_path)

    def backup_path(self, src_path, dest_path):
        try:
            if os.path.exists(src_path):
                dest = os.path.join(dest_path, os.path.basename(src_path))
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest)
                else:
                    shutil.copy2(src_path, dest)
        except Exception as e:
            logging.error(f"[gDriveSync] Error during backup_path: {e}")

    def upload_to_gdrive(self, backup_path, gdrive_folder, root_folder_id, pwnagotchi_folder_id):
        try:
            # Upload files to the /root folder
            if root_folder_id is not None:
                root_folder = self.drive.CreateFile({'id': root_folder_id})
                for root, dirs, files in os.walk('/root'):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        gdrive_file = self.drive.CreateFile({'title': filename, 'parents': [{'id': root_folder['id']}]})
                        gdrive_file.Upload()
                        logging.info(f"[gDriveSync] Uploaded {file_path} to Google Drive")

            # Upload files to the /etc/pwnagotchi folder
            if pwnagotchi_folder_id is not None:
                pwnagotchi_folder = self.drive.CreateFile({'id': pwnagotchi_folder_id})
                for root, dirs, files in os.walk('/etc/pwnagotchi'):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        gdrive_file = self.drive.CreateFile(
                            {'title': filename, 'parents': [{'id': pwnagotchi_folder['id']}]})
                        gdrive_file.Upload()
                        logging.info(f"[gDriveSync] Uploaded {file_path} to Google Drive")

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
