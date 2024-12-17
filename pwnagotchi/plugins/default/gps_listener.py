import json
import logging
import os
import subprocess
import threading

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

"""
# Android
# Termux:API : https://f-droid.org/en/packages/com.termux.api/
# Termux : https://f-droid.org/en/packages/com.termux/
pkg install termux-api socat bc

-----
#!/data/data/com.termux/files/usr/bin/bash

# Server details
SERVER_IP="192.168.44.44"  # IP of the socat receiver
SERVER_PORT="5000"         # UDP port to send data to

# Function to calculate checksum
calculate_checksum() {
  local sentence="$1"
  local checksum=0
  # Loop through each character in the sentence
  for ((i = 0; i < ${#sentence}; i++)); do
    checksum=$((checksum ^ $(printf '%d' "'${sentence:i:1}")))
  done
  # Return checksum in hexadecimal
  printf "%02X" $checksum
}

# Infinite loop to send GPS data
while true; do
  # Get location data
  LOCATION=$(termux-location -p gps)

  # Extract latitude, longitude, altitude, speed, and bearing
  LATITUDE=$(echo "$LOCATION" | jq '.latitude')
  LONGITUDE=$(echo "$LOCATION" | jq '.longitude')
  ALTITUDE=$(echo "$LOCATION" | jq '.altitude')
  SPEED=$(echo "$LOCATION" | jq '.speed') # Speed in meters per second
  BEARING=$(echo "$LOCATION" | jq '.bearing')

  # Convert speed from meters per second to knots and km/h
  SPEED_KNOTS=$(echo "$SPEED" | awk '{printf "%.1f", $1 * 1.943844}')
  SPEED_KMH=$(echo "$SPEED" | awk '{printf "%.1f", $1 * 3.6}')

  # Format latitude and longitude for NMEA
  LAT_DEGREES=$(printf "%.0f" "${LATITUDE%.*}")
  LAT_MINUTES=$(echo "(${LATITUDE#${LAT_DEGREES}} * 60)" | bc -l)
  LAT_DIRECTION=$(if (( $(echo "$LATITUDE >= 0" | bc -l) )); then echo "N"; else echo "S"; fi)
  LON_DEGREES=$(printf "%.0f" "${LONGITUDE%.*}")
  LON_MINUTES=$(echo "(${LONGITUDE#${LON_DEGREES}} * 60)" | bc -l)
  LON_DIRECTION=$(if (( $(echo "$LONGITUDE >= 0" | bc -l) )); then echo "E"; else echo "W"; fi)

  # Format the NMEA GGA sentence
  RAW_NMEA_GGA="GPGGA,123519,$(printf "%02d%07.4f" ${LAT_DEGREES#-} $LAT_MINUTES),$LAT_DIRECTION,$(printf "%03d%07.4f" ${LON_DEGREES#-} $LON_MINUTES),$LON_DIRECTION,1,08,0.9,$(printf "%.1f" $ALTITUDE),M,46.9,M,,"
  CHECKSUM=$(calculate_checksum "$RAW_NMEA_GGA")
  NMEA_GGA="\$${RAW_NMEA_GGA}*${CHECKSUM}"

  # Format the VTG sentence
  RAW_NMEA_VTG="GPVTG,$(printf "%.1f" $BEARING),T,,M,$(printf "%.1f" $SPEED_KNOTS),N,$(printf "%.1f" $SPEED_KMH),K"
  CHECKSUM_VTG=$(calculate_checksum "$RAW_NMEA_VTG")
  NMEA_VTG="\$${RAW_NMEA_VTG}*${CHECKSUM_VTG}"

  # Send data via UDP
  echo "$NMEA_GGA"  
  echo "$NMEA_GGA" | socat - UDP:$SERVER_IP:$SERVER_PORT
  #echo "$NMEA_VTG"
  #echo "$NMEA_VTG" | socat - UDP:$SERVER_IP:$SERVER_PORT
  
  sleep 1
done
-----

# Pwnagotchi
main.plugins.gps_listener.enabled = true

# packages
sudo apt-get install socat
"""

class GPS(plugins.Plugin):
    __author__ = 'https://github.com/krishenriksen'
    __version__ = "1.0.0"
    __license__ = "GPL3"
    __description__ = "Receive GPS coordinates via termux-location and save whenever an handshake is captured."

    def __init__(self):
        self.listen_ip = self.get_ip_address('bnep0')
        self.listen_port = "5000"
        self.write_virtual_serial = "/dev/ttyUSB1"
        self.read_virtual_serial = "/dev/ttyUSB0"
        self.baud_rate = "19200"
        self.socat_process = None
        self.stop_event = threading.Event()
        self.status_lock = threading.Lock()
        self.status = '-'
        self.socat_thread = threading.Thread(target=self.run_socat)

    def get_ip_address(self, interface):
        try:
            result = subprocess.run(
                ["ip", "addr", "show", interface],
                capture_output=True,
                text=True,
                check=True
            )
            for line in result.stdout.split('\n'):
                if 'inet ' in line:
                    ip_address = line.strip().split()[1].split('/')[0]
                    return ip_address
        except subprocess.CalledProcessError:
            logging.warning(f"Could not get IP address for interface {interface}")
            return None

    def set_status(self, status):
        with self.status_lock:
            self.status = status

    def get_status(self):
        with self.status_lock:
            return self.status

    def on_loaded(self):
        logging.info("GPS Listener plugin loaded")
        self.cleanup_virtual_serial_ports()
        self.create_virtual_serial_ports()
        self.socat_thread.start()

    def cleanup_virtual_serial_ports(self):
        if os.path.exists(self.write_virtual_serial):
            logging.info(f"Removing old {self.write_virtual_serial}")
            os.remove(self.write_virtual_serial)

        if os.path.exists(self.read_virtual_serial):
            logging.info(f"Removing old {self.read_virtual_serial}")
            os.remove(self.read_virtual_serial)

    def create_virtual_serial_ports(self):
        self.socat_process = subprocess.Popen(
            ["socat", "-d", "-d", f"pty,link={self.write_virtual_serial},mode=777",
             f"pty,link={self.read_virtual_serial},mode=777"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def run_socat(self):
        while not self.stop_event.is_set():
            self.socat_process = subprocess.Popen(
                ["socat", f"UDP-RECVFROM:{self.listen_port},reuseaddr,bind={self.listen_ip}", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            self.set_status('C')
  
            with open(self.write_virtual_serial, 'w') as serial_port:
                for line in self.socat_process.stdout:
                    if self.stop_event.is_set():
                        break
                    serial_port.write(line)
                    serial_port.flush()  # Ensure the data is written immediately
                    self.status = 'C'

            self.socat_process.wait()
            if self.stop_event.is_set():
                break

        self.set_status('-')

    def cleanup(self):
        if self.socat_process:
            self.socat_process.terminate()
            self.socat_process.wait() # Ensure the process is reaped
        self.stop_event.set()
        self.socat_thread.join()
        self.cleanup_virtual_serial_ports()

    def on_ready(self, agent):
        if os.path.exists(self.read_virtual_serial):
            logging.info(
                f"enabling bettercap's gps module for {self.read_virtual_serial}"
            )
            try:
                agent.run("gps off")
            except Exception:
                logging.info(f"bettercap gps module was already off")
                pass

            agent.run(f"set gps.device {self.read_virtual_serial}")
            agent.run(f"set gps.baudrate {self.baud_rate}")
            agent.run("gps on")

            logging.info(f"bettercap gps module enabled on {self.read_virtual_serial}")
        else:
            self.set_status('NF')
            logging.warning("no GPS detected")

    def on_handshake(self, agent, filename, access_point, client_station):
        info = agent.session()
        coordinates = info["gps"]
        gps_filename = filename.replace(".pcap", ".gps.json")

        if coordinates and all([
            # avoid 0.000... measurements
            coordinates["Latitude"], coordinates["Longitude"]
        ]):
            self.set_status('S')
            logging.info(f"saving GPS to {gps_filename} ({coordinates})")
            with open(gps_filename, "w+t") as fp:
                json.dump(coordinates, fp)
        else:
            logging.warning("not saving GPS. Couldn't find location.")

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element('gps', LabeledValue(color=BLACK, label='GPS', value='-', position=(ui.width() / 2 - 47, 0), label_font=fonts.Bold, text_font=fonts.Medium))

    def on_unload(self, ui):
        self.cleanup()  

        with ui._lock:
            ui.remove_element('gps')

    def on_ui_update(self, ui):
        ui.set('gps', self.get_status())
