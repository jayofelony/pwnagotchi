import os
import logging
import requests
import time
from threading import Lock
from pwnagotchi.utils import StatusFile, remove_whitelisted
import pwnagotchi.plugins as plugins
from json.decoder import JSONDecodeError


class ohcapi(plugins.Plugin):
    __author__ = "Rohan Dayaram"
    __version__ = "1.1.2"
    __license__ = "GPL3"
    __description__ = (
        "Uploads WPA/WPA2 handshakes to OnlineHashCrack.com using the new API (V2), no dashboard."
    )

    def __init__(self):
        self.ready = False
        self.lock = Lock()
        self.skip = list()
        self.last_run = 0  # Track last time periodic tasks were run

    def on_loaded(self):
        logging.info("[OHC NewAPI] Plugin loaded ")

    def on_config_changed(self, config):
        """
        Called when the plugin is loaded.
        """
        self.api_key = self.options.get("api_key", None)
        if not self.api_key:
            logging.error(f"[OHC NewAPI] Missing required API KEY")
            return

        self.handshakes_dir = config["bettercap"].get("handshakes")
        report_filename = os.path.join(self.handshakes_dir, ".ohc_uploads")
        try:
            self.report = StatusFile(report_filename, data_format="json")
        except JSONDecodeError:
            os.remove(report_filename)
            self.report = StatusFile(report_filename, data_format="json")
        self.whitelist = config["main"].get("whitelist", [])
        self.receive_email = self.options.get("receive_email", "yes")
        self.interval = self.options.get("interval", 60 * 60)  # 1 hour
        self.ready = True
        logging.info("[OHC NewAPI] Plugin ready.")

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
        if (time.time() - self.last_run) < self.interval:
            return
        self.last_run = time.time()  # Record the time of this run
        self._run_tasks(agent)  # Run immediately when internet is detected

    def _extract_essid_bssid_from_hash(self, hash_line):
        parts = hash_line.strip().split("*")
        essid = "unknown_ESSID"
        bssid = "00:00:00:00:00:00"

        if len(parts) > 5:
            essid_hex = parts[5]
            try:
                essid = bytes.fromhex(essid_hex).decode("utf-8", errors="replace")
            except:
                essid = "unknown_ESSID"

        if len(parts) > 3:
            apmac = parts[3]
            if len(apmac) == 12:
                bssid = ":".join(apmac[i : i + 2] for i in range(0, 12, 2))

        if essid == "unknown_ESSID" or bssid == "00:00:00:00:00:00":
            logging.debug(f"[OHC NewAPI] Failed to extract ESSID/BSSID from hash -> {hash_line}")

        return essid, bssid

    def _run_tasks(self, agent):
        """
        Encapsulates the logic of extracting, uploading, and updating tasks.
        """
        with self.lock:
            reported = self.report.data_field_or("reported", default=[])
            processed_stations = self.report.data_field_or("processed_stations", default=[])

            # Find .pcap files
            handshake_filenames = os.listdir(self.handshakes_dir)
            handshake_paths = [
                os.path.join(self.handshakes_dir, filename)
                for filename in handshake_filenames
                if filename.endswith(".pcap")
            ]
            # remove Whitelisted
            handshake_paths = remove_whitelisted(handshake_paths, self.whitelist)

            # If the corresponding .22000 file exists, skip re-upload
            handshake_paths = [
                p for p in handshake_paths if not os.path.exists(p.replace(".pcap", ".22000"))
            ]

            # Filter out already reported and skipped .pcap files
            handshake_new = set(handshake_paths) - set(reported) - set(self.skip)

            if not handshake_new:
                logging.info("[OHC NewAPI] No new PCAP files to process.")
                return
            logging.info(f"[OHC NewAPI] Processing {len(handshake_new)} new PCAP handshakes.")

            all_hashes = []
            successfully_extracted = []
            essid_bssid_map = {}

            for idx, pcap_path in enumerate(handshake_new):
                if hashes := self._extract_hashes_from_handshake(pcap_path):
                    # Extract ESSID and BSSID from the first hash line
                    essid, bssid = self._extract_essid_bssid_from_hash(hashes[0])
                    if (essid, bssid) in processed_stations:
                        logging.debug(
                            f"[OHC NewAPI] Station {essid}/{bssid} already processed, skipping {pcap_path}."
                        )
                        self.skip.append(pcap_path)
                        continue

                    all_hashes.extend(hashes)
                    successfully_extracted.append(pcap_path)
                    essid_bssid_map[pcap_path] = (essid, bssid)
                else:
                    logging.debug(f"[OHC NewAPI] No hashes extracted from {pcap_path}, skipping.")
                    self.skip.append(pcap_path)

            # Now upload all extracted hashes
            if not all_hashes:
                logging.info(
                    "[OHC NewAPI] No hashes were extracted from the new pcaps. Nothing to upload."
                )
                return
            display = agent.view()
            batches = [all_hashes[i : i + 50] for i in range(0, len(all_hashes), 50)]
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
                self.report.update(
                    data={"reported": reported, "processed_stations": processed_stations}
                )
                logging.info("[OHC NewAPI] Successfully reported all new handshakes.")
            else:
                # Upload failed, skip these pcaps for future attempts
                for pcap_path in successfully_extracted:
                    self.skip.append(pcap_path)
                logging.info("[OHC NewAPI] Failed to upload tasks, added to skip list.")

            display.on_normal()

    def _add_tasks(self, hashes, timeout=30):
        clean_hashes = [h.strip() for h in hashes if h.strip()]
        if not clean_hashes:
            return True  # No hashes to add is success

        payload = {
            "api_key": self.api_key,
            "agree_terms": "yes",
            "action": "add_tasks",
            "algo_mode": 22000,
            "hashes": clean_hashes,
            "receive_email": self.receive_email,
        }

        try:
            result = requests.post(
                "https://api.onlinehashcrack.com/v2", json=payload, timeout=timeout
            )
            result.raise_for_status()
            data = result.json()
            logging.info(f"[OHC NewAPI] Add tasks response: {data}")
            return True
        except requests.exceptions.RequestException as e:
            logging.debug(f"[OHC NewAPI] Exception while adding tasks -> {e}")
            return False

    def _extract_hashes_from_handshake(self, pcap_path):
        hashes = []
        hcxpcapngtool = "/usr/bin/hcxpcapngtool"
        hccapx_path = pcap_path.replace(".pcap", ".22000")
        hcxpcapngtool_cmd = f"{hcxpcapngtool} -o {hccapx_path} {pcap_path}"
        os.popen(hcxpcapngtool_cmd).read()
        if os.path.exists(hccapx_path) and os.path.getsize(hccapx_path) > 0:
            logging.debug(f"[OHC NewAPI] Extracted hashes from {pcap_path}")
            with open(hccapx_path, "r") as hccapx_file:
                hashes = hccapx_file.readlines()
        else:
            logging.debug(f"[OHC NewAPI] Failed to extract hashes from {pcap_path}")
            if os.path.exists(hccapx_path):
                os.remove(hccapx_path)
        return hashes
