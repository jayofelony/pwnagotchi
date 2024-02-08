import logging
import subprocess
import os
import json
import pwnagotchi.plugins as plugins
from threading import Lock

'''
hcxpcapngtool needed, to install:
> git clone https://github.com/ZerBea/hcxtools.git
> cd hcxtools
> apt-get install libcurl4-openssl-dev libssl-dev zlib1g-dev
> make
> sudo make install
'''


class Hashie(plugins.Plugin):
    __author__ = 'Jayofelony'
    __version__ = '1.0.4'
    __license__ = 'GPL3'
    __description__ = '''
                        Attempt to automatically convert pcaps to a crackable format.
                        If successful, the files  containing the hashes will be saved 
                        in the same folder as the handshakes. 
                        The files are saved in their respective Hashcat format:
                          - EAPOL hashes are saved as *.22000
                          - PMKID hashes are saved as *.16800
                        All PCAP files without enough information to create a hash are
                          stored in a file that can be read by the webgpsmap plugin.

                        Why use it?:
                          - Automatically convert handshakes to crackable formats! 
                              We dont all upload our hashes online ;)
                          - Repair PMKID handshakes that hcxpcapngtool misses
                          - If running at time of handshake capture, on_handshake can
                              be used to improve the chance of the repair succeeding
                          - Be a completionist! Not enough packets captured to crack a network?
                              This generates an output file for the webgpsmap plugin, use the
                              location data to revisit networks you need more packets for!

                        Additional information:
                          - Currently requires hcxpcapngtool compiled and installed
                          - Attempts to repair PMKID hashes when hcxpcapngtool cant find the SSID
                            - hcxpcapngtool sometimes has trouble extracting the SSID, so we 
                                use the raw 16800 output and attempt to retrieve the SSID via tcpdump
                            - When access_point data is available (on_handshake), we leverage 
                                the reported AP name and MAC to complete the hash
                            - The repair is very basic and could certainly be improved!
                        Todo:
                          Make it so users dont need hcxpcapngtool (unless it gets added to the base image)
                              Phase 1: Extract/construct 22000/16800 hashes through tcpdump commands
                              Phase 2: Extract/construct 22000/16800 hashes entirely in python
                          Improve the code, a lot
                        '''

    def __init__(self):
        self.lock = Lock()
        self.options = dict()

    def on_loaded(self):
        logging.info("[Hashie] Plugin loaded")

    def on_unloaded(self):
        logging.info("[Hashie] Plugin unloaded")

    # called when everything is ready and the main loop is about to start
    def on_ready(self, agent):
        config = agent.config()
        handshake_dir = config['bettercap']['handshakes']

        logging.info('[Hashie] Starting batch conversion of pcap files')
        with self.lock:
            self._process_stale_pcaps(handshake_dir)

    def on_handshake(self, agent, filename, access_point, client_station):
        with self.lock:
            handshake_status = []
            fullpathNoExt = filename.split('.')[0]
            name = filename.split('/')[-1:][0].split('.')[0]

            if os.path.isfile(fullpathNoExt + '.22000'):
                handshake_status.append('Already have {}.22000 (EAPOL)'.format(name))
            elif self._writeEAPOL(filename):
                handshake_status.append('Created {}.22000 (EAPOL) from pcap'.format(name))

            if os.path.isfile(fullpathNoExt + '.16800'):
                handshake_status.append('Already have {}.16800 (PMKID)'.format(name))
            elif self._writePMKID(filename):
                handshake_status.append('Created {}.16800 (PMKID) from pcap'.format(name))

            if handshake_status:
                logging.info('[Hashie] Good news:\n\t' + '\n\t'.join(handshake_status))

    def _writeEAPOL(self, fullpath):
        fullpathNoExt = fullpath.split('.')[0]
        filename = fullpath.split('/')[-1:][0].split('.')[0]
        subprocess.getoutput('hcxpcapngtool -o {}.22000 {} >/dev/null 2>&1'.format(fullpathNoExt, fullpath))
        if os.path.isfile(fullpathNoExt + '.22000'):
            logging.debug('[Hashie] [+] EAPOL Success: {}.22000 created'.format(filename))
            return True
        return False

    def _writePMKID(self, fullpath):
        fullpathNoExt = fullpath.split('.')[0]
        filename = fullpath.split('/')[-1:][0].split('.')[0]
        subprocess.getoutput('hcxpcapngtool -o {}.16800 {} >/dev/null 2>&1'.format(fullpathNoExt, fullpath))
        if os.path.isfile(fullpathNoExt + '.16800'):
            logging.debug('[Hashie] [+] PMKID Success: {}.16800 created'.format(filename))
            return True
        return False

    def _process_stale_pcaps(self, handshake_dir):
        handshakes_list = [os.path.join(handshake_dir, filename) for filename in os.listdir(handshake_dir) if filename.endswith('.pcap')]
        failed_jobs = []
        successful_jobs = []
        lonely_pcaps = []
        for num, handshake in enumerate(handshakes_list):
            fullpathNoExt = handshake.split('.')[0]
            pcapFileName = handshake.split('/')[-1:][0]
            if not os.path.isfile(fullpathNoExt + '.22000'):  # if no 22000, try
                if self._writeEAPOL(handshake):
                    successful_jobs.append('22000: ' + pcapFileName)
                else:
                    failed_jobs.append('22000: ' + pcapFileName)
            if not os.path.isfile(fullpathNoExt + '.16800'):  # if no 16800, try
                if self._writePMKID(handshake):
                    successful_jobs.append('16800: ' + pcapFileName)
                else:
                    failed_jobs.append('16800: ' + pcapFileName)
                    if not os.path.isfile(fullpathNoExt + '.22000'):  # if no 16800 AND no 22000
                        lonely_pcaps.append(handshake)
                        logging.debug('[hashie] Batch job: added {} to lonely list'.format(pcapFileName))
            if ((num + 1) % 50 == 0) or (num + 1 == len(handshakes_list)):  # report progress every 50, or when done
                logging.info('[Hashie] Batch job: {}/{} done ({} fails)'.format(num + 1, len(handshakes_list), len(lonely_pcaps)))
        if successful_jobs:
            logging.info('[Hashie] Batch job: {} new handshake files created'.format(len(successful_jobs)))
        if lonely_pcaps:
            logging.info('[Hashie] Batch job: {} networks without enough packets to create a hash'.format(len(lonely_pcaps)))
            self._getLocations(lonely_pcaps)

    def _getLocations(self, lonely_pcaps):
        # export a file for webgpsmap to load
        with open('/root/.incompletePcaps', 'w') as isIncomplete:
            count = 0
            for pcapFile in lonely_pcaps:
                filename = pcapFile.split('/')[-1:][0]  # keep extension
                fullpathNoExt = pcapFile.split('.')[0]
                isIncomplete.write(filename + '\n')
                if os.path.isfile(fullpathNoExt + '.gps.json') or os.path.isfile(fullpathNoExt + '.geo.json'):
                    count += 1
            if count != 0:
                logging.info('[Hashie] Used {} GPS/GEO files to find lonely networks, '
                             'go check webgpsmap! ;)'.format(str(count)))
            else:
                logging.info('[Hashie] Could not find any GPS/GEO files '
                             'for the lonely networks'.format(str(count)))

    def _getLocationsCSV(self, lonely_pcaps):
        # in case we need this later, export locations manually to CSV file, needs try/catch format/etc.
        locations = []
        for pcapFile in lonely_pcaps:
            filename = pcapFile.split('/')[-1:][0].split('.')[0]
            fullpathNoExt = pcapFile.split('.')[0]
            if os.path.isfile(fullpathNoExt + '.gps.json'):
                with open(fullpathNoExt + '.gps.json', 'r') as tempFileA:
                    data = json.load(tempFileA)
                    locations.append(filename + ',' + str(data['Latitude']) + ',' + str(data['Longitude']) + ',50')
            elif os.path.isfile(fullpathNoExt + '.geo.json'):
                with open(fullpathNoExt + '.geo.json', 'r') as tempFileB:
                    data = json.load(tempFileB)
                    locations.append(
                        filename + ',' + str(data['location']['lat']) + ',' + str(data['location']['lng']) + ',' + str(data['accuracy']))
        if locations:
            with open('/root/locations.csv', 'w') as tempFileD:
                for loc in locations:
                    tempFileD.write(loc + '\n')
            logging.info('[Hashie] Used {} GPS/GEO files to find lonely networks, '
                         'load /root/locations.csv into a mapping app and go say hi!'.format(len(locations)))
