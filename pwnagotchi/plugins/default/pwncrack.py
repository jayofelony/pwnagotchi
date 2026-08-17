import time
import os
import subprocess
import requests
import logging
import socket
from pwnagotchi.plugins import Plugin
from pwnagotchi.utils import StatusFile

class UploadConvertPlugin(Plugin):
    __author__ = 'Terminatoror'
    __version__ = '1.1.1'
    __license__ = 'GPL3'
    __description__ = 'Converts .pcapng files to .hc22000 and uploads them to pwncrack.org when internet is available.'

    def __init__(self):
        self.server_url = 'http://pwncrack.org/upload_handshake'  # Leave this as is
        self.potfile_url = 'http://pwncrack.org/download_potfile_script'  # Leave this as is
        self.timewait = 600
        self.last_run_time = 0
        self.options = dict()

    def on_loaded(self):
        logging.info('[pwncrack] loading')

    def on_config_changed(self, config):
        self.handshake_dir = config["bettercap"].get("handshakes")
        self.key = self.options.get('key', "")  # Change this to your key
        self.whitelist = config["main"].get("whitelist", [])
        self.combined_file = os.path.join(self.handshake_dir, 'combined.hc22000')
        self.potfile_path = os.path.join(self.handshake_dir, 'cracked.pwncrack.potfile')
        self.uploaded = StatusFile(os.path.join(self.handshake_dir, '.pwncrack_uploads'), data_format='json')

    def on_internet_available(self, agent):
        current_time = time.time()
        remaining_wait_time = self.timewait - (current_time - self.last_run_time)
        if remaining_wait_time > 0:
            logging.debug(f"[pwncrack] Waiting {remaining_wait_time:.1f} more seconds before next run.")
            return
        self.last_run_time = current_time
        logging.info(f"[pwncrack] Running upload process. Key: {self.key}, waiting: {self.timewait} seconds.")
        try:
            self._convert_and_upload()
            self._download_potfile()
        except Exception as e:
            logging.error(f"[pwncrack] Error occurred during upload process: {e}", exc_info=True)

    def _convert_and_upload(self):
        # Convert only new .pcapng files to .hc22000, excluding files matching whitelist items.
        # Each handshake is uploaded exactly once, ever - never re-uploaded even if the
        # .pcapng file grows afterward.
        uploaded = self.uploaded.data_field_or('uploaded', default=[])
        if isinstance(uploaded, dict):
            # Migrate from the previous path -> size format.
            uploaded = list(uploaded.keys())
        pcap_files = [f for f in os.listdir(self.handshake_dir)
                      if f.endswith('.pcapng') and not any(item in f for item in self.whitelist)]

        new_paths = [os.path.join(self.handshake_dir, pcap_file) for pcap_file in pcap_files
                     if os.path.join(self.handshake_dir, pcap_file) not in uploaded]

        if new_paths:
            for full_path in new_paths:
                subprocess.run(['hcxpcapngtool', '-o', self.combined_file, full_path])

            # Ensure the combined file is created
            if not os.path.exists(self.combined_file):
                open(self.combined_file, 'w').close()

            # Upload the combined .hc22000 file
            with open(self.combined_file, 'rb') as file:
                files = {'handshake': file}
                data = {'key': self.key}
                response = requests.post(self.server_url, files=files, data=data)

            # Log the response
            logging.info(f"[pwncrack] Upload response: {response.json()}")
            os.remove(self.combined_file)  # Remove the combined.hc22000 file

            uploaded.extend(new_paths)
            self.uploaded.update(data={'uploaded': uploaded})
        else:
            logging.info("[pwncrack] No new .pcapng files found to convert (or all files are whitelisted).")

    def _download_potfile(self):
        response = requests.get(self.potfile_url, params={'key': self.key})
        if response.status_code == 200:
            with open(self.potfile_path, 'w') as file:
                file.write(response.text)
            logging.info(f"[pwncrack] Potfile downloaded to {self.potfile_path}")
        else:
            logging.error(f"[pwncrack] Failed to download potfile: {response.status_code}")
            logging.error(f"[pwncrack] {response.json()}")  # Log the error message from the server

    def on_unload(self, ui):
        logging.info('[pwncrack] unloading')
