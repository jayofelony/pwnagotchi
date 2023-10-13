import logging
import os
import shutil
import time
import pwnagotchi.plugins as plugins
import pwnagotchi
import pydrive2
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


class GdriveSync(plugins.Plugin):
    __author__ = '@jayofelony'
    __version__ = '1.0'
    __license__ = 'GPL3'
    __description__ = 'A plugin to backup various pwnagotchi files and folders to Google Drive. Once every hour from loading plugin.'
    __dependencies__ = {
        'pip': ['pydrive2']
    }

    def __init__(self):
        self.internet = False
        self.ready = False
        self.drive = None
        self.last_upload_timestamp = time.time()
        self.backup = True
        self.backupfiles = [
                    '/root/brain.nn',
                    '/root/brain.json',
                    '/root/.api-report.json',
                    '/root/handshakes',
                    '/root/peers',
                    '/etc/pwnagotchi'
                ]

    # Function to get the folder ID by its name
    def get_folder_id_by_name(self, drive, folder_name):
        file_list = drive.ListFile({'q': "name="+folder_name+" and mimetype='application/vnd.google-apps.folder' and trashed=false"}).GetList()
        if 'files' in file_list and len(file_list['files']) > 0:
            return file_list['files'][0]['id']
        return None

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
                backup_folder_name = self.options['backup_folder']
                backup_folder_id = self.get_folder_id_by_name(self.drive, backup_folder_name)

                if not backup_folder_id:
                    # If the folder doesn't exist, create it
                    folder = self.drive.CreateFile(
                        {'title': backup_folder_name, 'mimeType': 'application/vnd.google-apps.folder'})
                    folder.Upload()
                    backup_folder_id = folder['id']
                    print(f"Created folder '{backup_folder_name}' with ID: {backup_folder_id}")

                # Continue with the rest of the code using backup_folder_id
                file_list = self.drive.ListFile({'q': f"'{backup_folder_id}' in parents and trashed=false"}).GetList()

                if not file_list:
                    # Handle the case where no files were found
                    logging.warning(f"[gDriveSync] No files found in the folder with ID {backup_folder_id}")
                    if self.options['backupfiles'] is not None:
                        self.backupfiles = self.backupfiles + self.options['backupfiles']
                    self.backup_files(self.backupfiles, '/backup')

                    self.upload_to_gdrive('/backup', 'PwnagotchiBackups')
                    self.backup = True

                # Specify the local backup path
                local_backup_path = '/'

                # Create the local backup directory if it doesn't exist
                os.makedirs(local_backup_path, exist_ok=True)

                # Download each file in the folder
                for file in file_list:
                    local_file_path = os.path.join(local_backup_path, file['title'])
                    file.GetContentFile(local_file_path)
                    logging.info(f"[gDriveSync] Downloaded {file['title']} from Google Drive")

                # Optionally, you can use the downloaded files as needed
                # For example, you can copy them to the corresponding directories
                self.backup = True
                with open("/root/.gdrive-backup", "w").close():
                    pass  # Create an empty file
                # reboot so we can start opwngrid with backup id
                pwnagotchi.reboot()

            # all set, gdriveSync is ready to run
            self.ready = True
            logging.info("[gdrivesync] loaded")
        except Exception as e:
            logging.error(f"Error: {e}")
            self.ready = False

    def on_unload(self, ui):
        logging.info("[gdrivesync] unloaded")

    def on_internet_available(self, agent):
        self.internet = True

    def on_handshake(self, agent):
        if not self.ready:
            return
        try:
            if self.internet:
                current_timestamp = time.time()
                # Check if an hour has passed since the last upload
                if current_timestamp - self.last_upload_timestamp >= 3600:
                    self.last_upload_timestamp = current_timestamp
                    logging.info("[gdrivesync] new handshake captured, backing up to gdrive")
                    if self.config['backupfiles'] is not None:
                        self.backupfiles = self.backupfiles + self.config['backupfiles']
                    self.backup_files(self.backupfiles, '/backup')

                    self.upload_to_gdrive('/backup', 'PwnagotchiBackups')
                    display = agent.view()
                    display.update(force=True, new_data={'Backing up to gdrive ...'})
        except Exception as e:
            logging.error(f"Error during handshake processing: {e}")

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
            logging.error(f"Error during backup_path: {e}")

    def upload_to_gdrive(self, backup_path, gdrive_folder):
        try:
            existing_folder = self.get_folder_id_by_name(self.drive, gdrive_folder)
            if existing_folder:
                folder = self.drive.CreateFile({'id': existing_folder})
            else:
                # Create a folder on Google Drive if it doesn't exist
                folder = self.drive.CreateFile({'title': gdrive_folder, 'mimeType': 'application/vnd.google-apps.folder'})
                folder.Upload()

            # Upload files to the created folder
            for root, dirs, files in os.walk(backup_path):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    gdrive_file = self.drive.CreateFile({'title': filename, 'parents': [{'id': folder['id']}]})
                    gdrive_file.Upload()
                    logging.info(f"[gDriveSync] Uploaded {file_path} to Google Drive")

            logging.info(f"[gDriveSync] Backup uploaded to Google Drive")
        except pydrive2.files.ApiRequestError as api_error:
            self.handle_upload_error(api_error, backup_path, gdrive_folder)

        except Exception as e:
            logging.error(f"Error during upload_to_gdrive: {e}")

    def handle_upload_error(self, api_error, backup_path, gdrive_folder):
        if 'Rate Limit Exceeded' in str(api_error):
            logging.warning("[gDriveSync] Rate limit exceeded. Waiting for some time before retrying...")
            # We set to 100 seconds, because there is a limit 20k requests per 100s per user
            time.sleep(100)  # You can adjust the sleep duration based on your needs
            self.upload_to_gdrive(backup_path, gdrive_folder)
        else:
            logging.error(f"[gDriveSync] API Request Error: {api_error}")
