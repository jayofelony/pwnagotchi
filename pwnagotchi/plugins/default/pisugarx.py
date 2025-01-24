import logging

from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import pwnagotchi
import time
import smbus
from flask import abort
from flask import render_template_string
from collections import deque

import threading
PiSugar_addresses = {
    "PiSugar2": 0x75,  # PiSugar2\2Plus
    "PiSugar3": 0x57,  # PiSugar3\3Plus
    "PiSugar2 RTC": 0x32  # PiSugar2\2Plus RTC
}
curve1200 = [
    (4.16, 100.0),
    (4.05, 95.0),
    (4.00, 80.0),
    (3.92, 65.0),
    (3.86, 40.0),
    (3.79, 25.5),
    (3.66, 10.0),
    (3.52, 6.5),
    (3.49, 3.2),
    (3.1, 0.0),
]
curve1200_3= [
    (4.2, 100.0),  # 高电量阶段 (100%)
    (4.0, 80.0),   # 中电量阶段 (80%)
    (3.7, 60.0),   # 中电量阶段 (60%)
    (3.5, 20.0),   # 低电量阶段 (20%)
    (3.1, 0.0)     # 电量耗尽 (0%)
]
curve5000 = [
    (4.10, 100.0),
    (4.05, 95.0),
    (3.90, 88.0),
    (3.80, 77.0),
    (3.70, 65.0),
    (3.62, 55.0),
    (3.58, 49.0),
    (3.49, 25.6),
    (3.32, 4.5),
    (3.1, 0.0),
]


class PiSugarServer:
    def __init__(self):
        """
        PiSugar initialization, if unable to connect to any version of PiSugar, return false
        """
        self._bus = smbus.SMBus(1)
        self.modle = None
        self.i2creg = []
        self.address = 0
        self.battery_voltage = 0
        self.voltage_history = deque(maxlen=10) 
        self.battery_level = 0
        self.battery_charging = 0
        self.temperature = 0
        self.power_plugged = False
        self.allow_charging = True
        while self.modle is None:
            if self.check_device(PiSugar_addresses["PiSugar2"]) is not None:
                self.address = PiSugar_addresses["PiSugar2"]
                if self.check_device(PiSugar_addresses["PiSugar2"], 0Xc2) != 0:
                    self.modle = "PiSugar2Plus"
                else:
                    self.modle = "PiSugar2"
                self.device_init()
            elif self.check_device(PiSugar_addresses["PiSugar3"]) is not None:
                self.modle = 'PiSugar3'
                self.address = PiSugar_addresses["PiSugar3"]
            else:
                self.modle = None
                logging.error(
                    "No PiSugar device was found. Please check if the PiSugar device is powered on.")
                time.sleep(5)

        # self.update_value()
        self.start_timer()
        while len(self.i2creg) < 256:
            time.sleep(1)

    def start_timer(self):

        # 创建一个线程来执行定时函数
        timer_thread = threading.Thread(target=self.update_value)
        timer_thread.daemon = True  # 设置为守护线程，主程序退出时自动结束
        timer_thread.start()

    def update_value(self):
        """每三秒更新pisugar状态，包括触发自动关机"""
        while True:
            try:
                self.i2creg = []
                for i in range(0, 256, 32):
                    # 计算当前读取的起始寄存器地址
                    current_register = 0 + i
                    # 计算当前读取的数据长度
                    current_length = min(32, 256 - i)
                    # 读取数据块
                    chunk = self._bus.read_i2c_block_data(
                        self.address, current_register, current_length)
                    # 将读取的数据块添加到结果列表中
                    self.i2creg.extend(chunk)
                    time.sleep(0.1)
                logging.debug(f"Data length: {len(self.i2creg)}")
                logging.debug(f"Data: {self.i2creg}")
                if self.modle == 'PiSugar3':
                    low = self.i2creg[0x23]
                    high = self.i2creg[0x22]
                    self.battery_voltage = (((high << 8) + low) / 1000)
                    self.temperature = self.i2creg[0x04]-40
                    ctr1 = self.i2creg[0x02]  # 读取控制寄存器 1
                    self.power_plugged = (ctr1 & (1 << 7)) != 0  # 检查电源是否插入
                    self.allow_charging = (ctr1 & (1 << 6)) != 0  # 检查是否允许充电
                elif self.modle == 'PiSugar2':
                    high = self.i2creg[0xa3]
                    low = self.i2creg[0xa2]
                    self.battery_voltage = (2600.0 - (((high | 0b11000000) << 8) + low) * 0.26855) / \
                        1000.0 if high & 0x20 else (
                            2600.0 + (((high & 0x1f) << 8) + low) * 0.26855) / 1000.0
                    self.power_plugged = (self.i2creg[0x55] & 0b00010000) != 0

                elif self.modle == 'PiSugar2Plus':
                    low = self.i2creg[0xd0]
                    high = self.i2creg[0xd1]
                    self.battery_voltage = (
                        (((high & 0b00111111) << 8) + low) * 0.26855 + 2600.0)/1000
                    self.power_plugged = self.i2creg[0xdd] == 0x1f
                
                self.voltage_history.append(self.battery_voltage)
                self.battery_level=self.convert_battery_voltage_to_level()
                time.sleep(3)
            except:
                logging.error(f"read error")
            time.sleep(3)

    def check_device(self, address, reg=0):
        """Check if a device is present at the specified address"""
        try:
            return self._bus.read_byte_data(address, reg)
        except OSError as e:
            logging.debug(f"Device not found at address {address}: {e}")
            return None

    def device_init(self):

        if self.modle == "PiSugar2Plus":
            '''初始化GPIO'''
            self._bus.write_byte_data(self.address, 0x52, self._bus.read_byte_data(
                self.address, 0x52) | 0b00000010)
            self._bus.write_byte_data(self.address, 0x54, self._bus.read_byte_data(
                self.address, 0x54) | 0b00000010)
            self._bus.write_byte_data(self.address, 0x52, self._bus.read_byte_data(
                self.address, 0x52) | 0b00000100)
            self._bus.write_byte_data(self.address, 0x29, self._bus.read_byte_data(
                self.address, 0x29) & 0b10111111)
            self._bus.write_byte_data(self.address, 0x52, self._bus.read_byte_data(
                self.address, 0x52) & 0b10011111 | 0b01000000)
            self._bus.write_byte_data(self.address, 0xc2, self._bus.read_byte_data(
                self.address, 0xc2) | 0b00010000)
            logging.debug(f"PiSugar2Plus GPIO 初始化完毕")
            '''Init boost intensity, 0x3f*50ma, 3A'''
            self._bus.write_byte_data(self.address, 0x30, self._bus.read_byte_data(
                self.address, 0x30) & 0b11000000 | 0x3f)
            logging.debug(f"PiSugar2Plus 电流设置完毕")

        elif self.modle == "PiSugar2":
            '''初始化GPIO'''
            self._bus.write_byte_data(self.address, 0x51, (self._bus.read_byte_data(
                self.address, 0x51) & 0b11110011) | 0b00000100)
            self._bus.write_byte_data(self.address, 0x53, self._bus.read_byte_data(
                self.address, 0x53) | 0b00000010)
            self._bus.write_byte_data(self.address, 0x51, (self._bus.read_byte_data(
                self.address, 0x51) & 0b11001111) | 0b00010000)
            self._bus.write_byte_data(self.address, 0x26, self._bus.read_byte_data(
                self.address, 0x26) & 0b10110000)
            self._bus.write_byte_data(self.address, 0x52, (self._bus.read_byte_data(
                self.address, 0x52) & 0b11110011) | 0b00000100)
            self._bus.write_byte_data(self.address, 0x53, (self._bus.read_byte_data(
                self.address, 0x53) & 0b11101111) | 0b00010000)
            logging.debug(f"PiSugar2 GPIO 初始化完毕")
        pass

    def convert_battery_voltage_to_level(self):
        """
        将电池电压转换为电量百分比。

        :param voltage: 当前电池电压
        :param curve: 电池阈值曲线，格式为 [(电压1, 电量1), (电压2, 电量2), ...]
        :return: 电量百分比
        """
        if (self.modle == "PiSugar2Plus") | (self.modle == "PiSugar3Plus"):
            curve = curve5000
        elif self.modle == "PiSugar2":
            curve = curve1200
        elif self.modle == "PiSugar3":
            curve = curve1200_3
         # 将当前电压加入历史记录

        # 如果历史记录不足 5 次，直接返回平均值（避免截尾后无有效数据）
        if len(self.voltage_history) < 5:
            avg_voltage = sum(self.voltage_history) / len(self.voltage_history)
        else:
            # 排序后去掉最高 2 个和最低 2 个
            sorted_history = sorted(self.voltage_history)
            trimmed_history = sorted_history[2:-2]  # 去掉前两个和后两个
            avg_voltage = sum(trimmed_history) / len(trimmed_history)  # 计算截尾平均
        # 遍历电池曲线的每一段
        for (v1, p1), (v2, p2) in zip(curve, curve[1:]):
            # 如果电压在当前区间内
            if v2 <= avg_voltage <= v1:
                # 使用线性插值计算电量
                return p2 + (p1 - p2) * (avg_voltage - v2) / (v1 - v2)

        # 如果电压超出曲线范围，返回最低或最高电量
        return curve[-1][1] if avg_voltage < curve[-1][0] else curve[0][1]

    def get_version(self):
        """
        Get the firmware version of the PiSugar3.
        If not PiSugar3, return None
        :return: Version string or None
        """
        if self.modle == 'PiSugar3':
            try:
                return bytes(self.i2creg[0xe2:0xee]).decode('ascii')
            except OSError as e:
                logging.error(f"Failed to read version from PiSugar3: {e}")
                return None
        return None

    def get_model(self):
        """
        Get the model of the PiSugar hardware.

        :return: Model string.
        """
        return self.modle

    def get_battery_level(self):
        """
        Get the current battery level in percentage.

        :return: Battery level as a percentage (0-100).
        """
        return self.battery_level

    def get_battery_voltage(self):
        """
        Get the current battery voltage.

        :return: Battery voltage in volts.
        """
        return self.battery_voltage

    def get_battery_current(self):
        """
        Get the current battery current.

        :return: Battery current in amperes.
        """
        pass

    def get_battery_allow_charging(self):
        """
        Check if battery charging is allowed.

        :return: True if charging is allowed, False otherwise.
        """
        return self.allow_charging

    def get_battery_charging_range(self):
        """
        Get the battery charging range.

        :return: Charging range string.
        """
        pass

    def get_battery_full_charge_duration(self):
        """
        Get the duration of keeping the battery charging when full.

        :return: Duration in seconds.
        """
        pass

    def get_battery_safe_shutdown_level(self):
        """
        Get the safe shutdown level for the battery.

        :return: Safe shutdown level as a percentage.
        """
        pass

    def get_battery_safe_shutdown_delay(self):
        """
        Get the safe shutdown delay.

        :return: Delay in seconds.
        """
        pass

    def get_battery_auto_power_on(self):
        """
        Check if auto power on is enabled.

        :return: True if enabled, False otherwise.
        """
        pass

    def get_battery_soft_poweroff(self):
        """
        Check if soft power off is enabled.

        :return: True if enabled, False otherwise.
        """
        pass

    def get_system_time(self):
        """
        Get the system time.

        :return: System time string.
        """
        pass

    def get_rtc_adjust_ppm(self):
        """
        Get the RTC adjust PPM.

        :return: RTC adjust PPM value.
        """
        pass

    def get_rtc_alarm_repeat(self):
        """
        Get the RTC alarm repeat setting.

        :return: RTC alarm repeat string.
        """
        pass

    def get_tap_enable(self, tap):
        """
        Check if a specific tap (single, double, long) is enabled.

        :param tap: Type of tap ('single', 'double', 'long').
        :return: True if enabled, False otherwise.
        """
        pass

    def get_tap_shell(self, tap):
        """
        Get the shell command associated with a specific tap.

        :param tap: Type of tap ('single', 'double', 'long').
        :return: Shell command string.
        """
        pass

    def get_anti_mistouch(self):
        """
        Check if anti-mistouch protection is enabled.

        :return: True if enabled, False otherwise.
        """
        pass

    def get_temperature(self):
        """
        Get the current temperature.

        :return: Temperature in degrees Celsius.
        """
        return self.temperature

    def get_battery_power_plugged(self):
        """
        Check if the battery is plugged in.

        :return: True if plugged in, False otherwise.
        """
        return self.power_plugged

    def get_battery_charging(self):
        """
        Check if the battery is currently charging.

        :return: True if charging, False otherwise.
        """
        pass

    def rtc_web(self):
        """
        Synchronize RTC with web time.
        """
        pass

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
            self.ps = PiSugarServer()
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
            ui._state._state['bat'].label = "CHG"
        else:
            # Otherwise, keep it as "BAT"
            ui._state._state['bat'].label = "BAT"

        # Handle rotation or default display logic
        if self.rotation_enabled:
            if time.time() > self.nextDChg:
                self.drot = (self.drot + 1) % 3
                self.nextDChg = time.time() + 5

            if self.drot == 0:  # show battery voltage
                ui.set('bat', f"{voltage:.2f}V")
            elif self.drot == 1:  # show battery capacity
                ui.set('bat', f"{capacity:.0f}%")
            else:  # show battery temperature
                ui.set('bat', f"{temp}°C")
        else:
            # Rotation disabled, show only the selected default display
            if self.default_display == 'voltage':
                ui.set('bat', f"{voltage:.2f}V")
            elif self.default_display in ['percentage', 'percent']:
                ui.set('bat', f"{capacity:.0f}%")
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

