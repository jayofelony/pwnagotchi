import logging

from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import pwnagotchi
import time
from pisugar import *
from flask import abort
from flask import render_template_string

class PiSugar(plugins.Plugin):
    __author__ = "jayofelony"
    __version__ = "1.2"
    __license__ = "GPL3"
    __description__ = (
        "A plugin that will add a voltage indicator for the PiSugar batteries. "
        "Rotation of battery status can be enabled or disabled via configuration. "
        "Additionally, when rotation is disabled, you can choose which metric to display."
    )

    def __init__(self):
        self._agent = None
        self.is_new_model = False
        self.options = dict()
        self.ps = None
        try:
            conn, event_conn = connect_tcp()
            self.ps = PiSugarServer(conn, event_conn)
        except Exception as e:
            # Log at debug to avoid clutter since it might be a false positive
            logging.debug("[PiSugarX] Unable to establish connection: %s", repr(e))

        self.ready = False
        self.lasttemp = 69
        self.drot = 0  # display rotation index
        self.nextDChg = 0  # last time display changed
        self.rotation_enabled = True  # default: rotation enabled
        self.default_display = "voltage"  # default display option

    def safe_get(self, func, default=None):
        """
        Helper function to safely call PiSugar getters. When an exception is detected,
        return 'default' and log at debug level.
        """
        if self.ps is None:
            return default
        try:
            return func()
        except Exception as e:
            logging.debug("[PiSugarX] Failed to get data using %s: %s", func.__name__, e)
            return default

    def on_loaded(self):
        logging.info("[PiSugarX] plugin loaded.")
        cfg = pwnagotchi.config['main']['plugins']['pisugarx']
        self.rotation_enabled = cfg.get('rotation', True)
        self.default_display = cfg.get('default_display', 'voltage').lower()

        valid_displays = ['voltage', 'percentage', 'temp']
        if self.default_display not in valid_displays:
            logging.warning(f"[PiSugarX] Invalid default_display '{self.default_display}'. Using 'voltage'.")
            self.default_display = 'voltage'

        logging.info(f"[PiSugarX] Rotation is {'enabled' if self.rotation_enabled else 'disabled'}.")
        logging.info(f"[PiSugarX] Default display (when rotation disabled): {self.default_display}")

    def on_ready(self, agent):
        self.ready = True
        self._agent = agent
        led_amount = self.safe_get(self.ps.get_battery_led_amount, default=0)
        if led_amount == 2:
            self.is_new_model = True
        else:
            self.is_new_model = False

    def on_internet_available(self, agent):
        self._agent = agent
        self.safe_get(self.ps.rtc_web)

    def on_webhook(self, path, request):
        if not self.ready or self.ps is None:
            ret = "<html><head><title>PiSugarX not ready</title></head><body><h1>PiSugarX not ready</h1></body></html>"
            return render_template_string(ret)

        try:
            if request.method == "GET":
                if path == "/" or not path:
                    version = self.safe_get(self.ps.get_version, default='Unknown')
                    model = self.safe_get(self.ps.get_model, default='Unknown')
                    battery_level = self.safe_get(self.ps.get_battery_level, default='N/A')
                    battery_voltage = self.safe_get(self.ps.get_battery_voltage, default='N/A')
                    battery_current = self.safe_get(self.ps.get_battery_current, default='N/A')
                    battery_led_amount = self.safe_get(self.ps.get_battery_led_amount, default='N/A') if model == 'Pisugar 2' else 'Not supported'
                    battery_allow_charging = self.safe_get(self.ps.get_battery_allow_charging, default=False)
                    battery_charging_range = self.safe_get(self.ps.get_battery_charging_range, default='N/A') if self.is_new_model or model == 'Pisugar 3' else 'Not supported'
                    battery_full_charge_duration = getattr(self.ps, 'get_battery_full_charge_duration', lambda: 'N/A')()
                    safe_shutdown_level = self.safe_get(self.ps.get_battery_safe_shutdown_level, default=None)
                    battery_safe_shutdown_level = f"{safe_shutdown_level}%" if safe_shutdown_level is not None else 'Not set'
                    battery_safe_shutdown_delay = self.safe_get(self.ps.get_battery_safe_shutdown_delay, default='N/A')
                    battery_auto_power_on = self.safe_get(self.ps.get_battery_auto_power_on, default=False)
                    battery_soft_poweroff = self.safe_get(self.ps.get_battery_soft_poweroff, default=False) if model == 'Pisugar 3' else False
                    system_time = self.safe_get(self.ps.get_system_time, default='N/A')
                    rtc_adjust_ppm = self.safe_get(self.ps.get_rtc_adjust_ppm, default='Not supported') if model == 'Pisugar 3' else 'Not supported'
                    rtc_alarm_repeat = self.safe_get(self.ps.get_rtc_alarm_repeat, default='N/A')
                    single_tap_enabled = self.safe_get(lambda: self.ps.get_tap_enable(tap='single'), default=False)
                    double_tap_enabled = self.safe_get(lambda: self.ps.get_tap_enable(tap='double'), default=False)
                    long_tap_enabled = self.safe_get(lambda: self.ps.get_tap_enable(tap='long'), default=False)
                    single_tap_shell = self.safe_get(lambda: self.ps.get_tap_shell(tap='single'), default='N/A')
                    double_tap_shell = self.safe_get(lambda: self.ps.get_tap_shell(tap='double'), default='N/A')
                    long_tap_shell = self.safe_get(lambda: self.ps.get_tap_shell(tap='long'), default='N/A')
                    anti_mistouch = self.safe_get(self.ps.get_anti_mistouch, default=False) if model == 'Pisugar 3' else False
                    temperature = self.safe_get(self.ps.get_temperature, default='N/A')

                    ret = '''
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="csrf_token" content="{{ csrf_token() }}">
                        <title>PiSugarX Parameters</title>
                        <style>
                            body {
                                font-family: Arial, sans-serif;
                                line-height: 1.6;
                                margin: 20px;
                                padding: 20px;
                                background-color: #f4f4f9;
                                color: #333;
                            }
                            h1 {
                                color: #444;
                                border-bottom: 2px solid #ddd;
                                padding-bottom: 10px;
                            }
                            table {
                                width: 40%;
                                border-collapse: collapse;
                                margin: 20px 0;
                            }
                            table th, table td {
                                border: 1px solid #ccc;
                                padding: 5px;
                                text-align: left;
                                font-size: 12px;
                            }
                            table thead {
                                background-color: #f9f9f9;
                            }
                            .note {
                                font-size: 0.9em;
                                color: #666;
                                margin-top: 20px;
                            }
                        </style>
                    </head>
                    <body>
                        <h1>PiSugarX Parameters</h1>
                        <table>
                            <thead>
                                <tr>
                                    <th>Parameter</th>
                                    <th>Value</th>
                                </tr>
                            </thead>
                            <tbody>
                    '''
                    ret += f'''
                                <tr><td>Server version</td><td>{version}</td></tr>
                                <tr><td>PiSugar Model</td><td>{model}</td></tr>
                                <tr><td>Battery Level</td><td>{battery_level}%</td></tr>
                                <tr><td>Battery Voltage</td><td>{battery_voltage}V</td></tr>
                                <tr><td>Battery Current</td><td>{battery_current}A</td></tr>
                                <tr><td>Battery LED Amount</td><td>{battery_led_amount}</td></tr>
                                <tr><td>Battery Allow Charging</td><td>{"Yes" if battery_allow_charging and self.is_new_model else "No"}</td></tr>
                                <tr><td>Battery Charging Range</td><td>{battery_charging_range}</td></tr>
                                <tr><td>Duration of Keep Charging When Full</td><td>{battery_full_charge_duration} seconds</td></tr>
                                <tr><td>Battery Safe Shutdown Level</td><td>{battery_safe_shutdown_level}</td></tr>
                                <tr><td>Battery Safe Shutdown Delay</td><td>{battery_safe_shutdown_delay} seconds</td></tr>
                                <tr><td>Battery Auto Power On</td><td>{"Yes" if battery_auto_power_on else "No"}</td></tr>
                                <tr><td>Battery Soft Power Off Enabled</td><td>{"Yes" if battery_soft_poweroff and model == 'Pisugar 3' else "No"}</td></tr>
                                <tr><td>System Time</td><td>{system_time}</td></tr>
                                <tr><td>RTC Adjust PPM</td><td>{rtc_adjust_ppm}</td></tr>
                                <tr><td>RTC Alarm Repeat</td><td>{rtc_alarm_repeat}</td></tr>
                                <tr><td>Single Tap Enabled</td><td>{"Yes" if single_tap_enabled else "No"}</td></tr>
                                <tr><td>Double Tap Enabled</td><td>{"Yes" if double_tap_enabled else "No"}</td></tr>
                                <tr><td>Long Tap Enabled</td><td>{"Yes" if long_tap_enabled else "No"}</td></tr>
                                <tr><td>Single Tap Shell</td><td>{single_tap_shell}</td></tr>
                                <tr><td>Double Tap Shell</td><td>{double_tap_shell}</td></tr>
                                <tr><td>Long Tap Shell</td><td>{long_tap_shell}</td></tr>
                                <tr><td>Mis Touch Protection Enabled</td><td>{"Yes" if anti_mistouch and model == "Pisugar 3" else "No"}</td></tr>
                                <tr><td>Battery Temperature</td><td>{temperature} °C</td></tr>
                            </tbody>
                        </table>
                        <div class="note">
                            <p>Note: Some parameters may not be supported on certain PiSugar models.</p>
                        </div>
                    </body>
                    </html>
                    '''

                    return render_template_string(ret)
                else:
                    abort(404)
            elif request.method == "POST":
                try:
                    ret = '<html><head><title>PiSugarX</title><meta name="csrf_token" content="{{ csrf_token() }}"></head>'
                    pass
                except Exception as e:
                    ret = "<html><head><title>PiSugarX error</title></head>"
                    ret += "<body><h1>%s</h1></body></html>" % repr(e)
                    logging.debug("[PiSugarX] error during POST: %s" % repr(e))
                    return render_template_string(ret), 500
        except Exception as e:
            ret = "<html><head><title>PiSugarX error</title></head>"
            ret += "<body><h1>%s</h1></body></html>" % repr(e)
            logging.debug("[PiSugarX] error: %s" % repr(e))
            return render_template_string(ret), 404

    def on_ui_setup(self, ui):
        # Add the "bat" UI element
        ui.add_element(
            "bat",
            LabeledValue(
                color=BLACK,
                label="BAT",
                value="0%",
                position=(ui.width() / 2 + 15, 0),
                label_font=fonts.Bold,
                text_font=fonts.Medium,
            ),
        )

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element("bat")

    def on_ui_update(self, ui):
        # Make sure "bat" is in the UI state (guard to prevent KeyError)
        if 'bat' not in ui._state._state:
            return

        capacity = self.safe_get(self.ps.get_battery_level, default=0)
        voltage = self.safe_get(self.ps.get_battery_voltage, default=0.00)
        temp = self.safe_get(self.ps.get_temperature, default=0)

        # Check if battery is plugged in
        battery_plugged = self.safe_get(self.ps.get_battery_power_plugged, default=False)

        if battery_plugged:
            # If plugged in, display "CHG"
            ui._state._state['bat'].label = "CHG: "
        else:
            # Otherwise, keep it as "BAT"
            ui._state._state['bat'].label = "BAT: "

        # Handle rotation or default display logic
        if self.rotation_enabled:
            if time.time() > self.nextDChg:
                self.drot = (self.drot + 1) % 3
                self.nextDChg = time.time() + 5

            if self.drot == 0:  # show battery voltage
                ui.set('bat', f"{voltage:.2f}V")
            elif self.drot == 1:  # show battery capacity
                ui.set('bat', f"{capacity:.2f}%")
            else:  # show battery temperature
                ui.set('bat', f"{temp}°C")
        else:
            # Rotation disabled, show only the selected default display
            if self.default_display == 'voltage':
                ui.set('bat', f"{voltage:.2f}V")
            elif self.default_display in ['percentage', 'percent']:
                ui.set('bat', f"{capacity:.2f}%")
            elif self.default_display == 'temp':
                ui.set('bat', f"{temp}°C")

        charging = self.safe_get(self.ps.get_battery_charging, default=None)
        safe_shutdown_level = self.safe_get(self.ps.get_battery_safe_shutdown_level, default=0)
        if charging is not None:
            if capacity <= safe_shutdown_level:
                logging.info(
                    f"[PiSugarX] Empty battery (<= {safe_shutdown_level}%): shutting down"
                )
                ui.update(force=True, new_data={"status": "Battery exhausted, bye ..."})