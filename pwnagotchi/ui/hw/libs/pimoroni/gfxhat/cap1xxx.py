"""Cap-touch Driver Library for Microchip CAP1xxx ICs
Supports communication over i2c only.

Currently supported ICs:
CAP1208 - 8 Inputs
CAP1188 - 8 Inputs, 8 LEDs
CAP1166 - 6 Inputs, 6 LEDs
"""

import atexit
import signal
import threading
import time
from sys import version_info

try:
    from smbus import SMBus
except ImportError:
    if version_info[0] < 3:
        raise ImportError("This library requires python-smbus\nInstall with: sudo apt-get install python-smbus")
    elif version_info[0] == 3:
        raise ImportError("This library requires python3-smbus\nInstall with: sudo apt-get install python3-smbus")

try:
    import RPi.GPIO as GPIO
except ImportError:
    raise ImportError("This library requires the RPi.GPIO module\nInstall with: sudo pip install RPi.GPIO")

__version__ = '0.1.4'

# DEVICE MAP
DEFAULT_ADDR = 0x28

# Supported devices
PID_CAP1208 = 0b01101011
PID_CAP1188 = 0b01010000
PID_CAP1166 = 0b01010001

# REGISTER MAP

R_MAIN_CONTROL      = 0x00
R_GENERAL_STATUS    = 0x02
R_INPUT_STATUS      = 0x03
R_LED_STATUS        = 0x04
R_NOISE_FLAG_STATUS = 0x0A

# Read-only delta counts for all inputs
R_INPUT_1_DELTA   = 0x10
R_INPUT_2_DELTA   = 0x11
R_INPUT_3_DELTA   = 0x12
R_INPUT_4_DELTA   = 0x13
R_INPUT_5_DELTA   = 0x14
R_INPUT_6_DELTA   = 0x15
R_INPUT_7_DELTA   = 0x16
R_INPUT_8_DELTA   = 0x17

R_SENSITIVITY     = 0x1F
# B7     = N/A
# B6..B4 = Sensitivity
# B3..B0 = Base Shift
SENSITIVITY = {128: 0b000, 64:0b001, 32:0b010, 16:0b011, 8:0b100, 4:0b100, 2:0b110, 1:0b111}

R_GENERAL_CONFIG  = 0x20
# B7 = Timeout
# B6 = Wake Config ( 1 = Wake pin asserted )
# B5 = Disable Digital Noise ( 1 = Noise threshold disabled )
# B4 = Disable Analog Noise ( 1 = Low frequency analog noise blocking disabled )
# B3 = Max Duration Recalibration ( 1 =  Enable recalibration if touch is held longer than max duration )
# B2..B0 = N/A

R_INPUT_ENABLE    = 0x21


R_INPUT_CONFIG    = 0x22

R_INPUT_CONFIG2   = 0x23 # Default 0x00000111

# Values for bits 3 to 0 of R_INPUT_CONFIG2
# Determines minimum amount of time before
# a "press and hold" event is detected.

# Also - Values for bits 3 to 0 of R_INPUT_CONFIG
# Determines rate at which interrupt will repeat
#
# Resolution of 35ms, max = 35 + (35 * 0b1111) = 560ms

R_SAMPLING_CONFIG = 0x24 # Default 0x00111001
R_CALIBRATION     = 0x26 # Default 0b00000000
R_INTERRUPT_EN    = 0x27 # Default 0b11111111
R_REPEAT_EN       = 0x28 # Default 0b11111111
R_MTOUCH_CONFIG   = 0x2A # Default 0b11111111
R_MTOUCH_PAT_CONF = 0x2B
R_MTOUCH_PATTERN  = 0x2D
R_COUNT_O_LIMIT   = 0x2E
R_RECALIBRATION   = 0x2F

# R/W Touch detection thresholds for inputs
R_INPUT_1_THRESH  = 0x30
R_INPUT_2_THRESH  = 0x31
R_INPUT_3_THRESH  = 0x32
R_INPUT_4_THRESH  = 0x33
R_INPUT_5_THRESH  = 0x34
R_INPUT_6_THRESH  = 0x35
R_INPUT_7_THRESH  = 0x36
R_INPUT_8_THRESH  = 0x37

# R/W Noise threshold for all inputs
R_NOISE_THRESH    = 0x38

# R/W Standby and Config Registers
R_STANDBY_CHANNEL = 0x40
R_STANDBY_CONFIG  = 0x41
R_STANDBY_SENS    = 0x42
R_STANDBY_THRESH  = 0x43

R_CONFIGURATION2  = 0x44
# B7 = Linked LED Transition Controls ( 1 = LED trigger is !touch )
# B6 = Alert Polarity ( 1 = Active Low Open Drain, 0 = Active High Push Pull )
# B5 = Reduce Power ( 1 = Do not power down between poll )
# B4 = Link Polarity/Mirror bits ( 0 = Linked, 1 = Unlinked )
# B3 = Show RF Noise ( 1 = Noise status registers only show RF, 0 = Both RF and EMI shown )
# B2 = Disable RF Noise ( 1 = Disable RF noise filter )
# B1..B0 = N/A

# Read-only reference counts for sensor inputs
R_INPUT_1_BCOUNT  = 0x50
R_INPUT_2_BCOUNT  = 0x51
R_INPUT_3_BCOUNT  = 0x52
R_INPUT_4_BCOUNT  = 0x53
R_INPUT_5_BCOUNT  = 0x54
R_INPUT_6_BCOUNT  = 0x55
R_INPUT_7_BCOUNT  = 0x56
R_INPUT_8_BCOUNT  = 0x57

# LED Controls - For CAP1188 and similar
R_LED_OUTPUT_TYPE = 0x71
R_LED_LINKING     = 0x72
R_LED_POLARITY    = 0x73
R_LED_OUTPUT_CON  = 0x74
R_LED_LTRANS_CON  = 0x77
R_LED_MIRROR_CON  = 0x79

# LED Behaviour
R_LED_BEHAVIOUR_1 = 0x81 # For LEDs 1-4
R_LED_BEHAVIOUR_2 = 0x82 # For LEDs 5-8
R_LED_PULSE_1_PER = 0x84
R_LED_PULSE_2_PER = 0x85
R_LED_BREATHE_PER = 0x86
R_LED_CONFIG      = 0x88
R_LED_PULSE_1_DUT = 0x90
R_LED_PULSE_2_DUT = 0x91
R_LED_BREATHE_DUT = 0x92
R_LED_DIRECT_DUT  = 0x93
R_LED_DIRECT_RAMP = 0x94
R_LED_OFF_DELAY   = 0x95

# R/W Power buttonc ontrol
R_POWER_BUTTON    = 0x60
R_POW_BUTTON_CONF = 0x61

# Read-only upper 8-bit calibration values for sensors
R_INPUT_1_CALIB   = 0xB1
R_INPUT_2_CALIB   = 0xB2
R_INPUT_3_CALIB   = 0xB3
R_INPUT_4_CALIB   = 0xB4
R_INPUT_5_CALIB   = 0xB5
R_INPUT_6_CALIB   = 0xB6
R_INPUT_7_CALIB   = 0xB7
R_INPUT_8_CALIB   = 0xB8

# Read-only 2 LSBs for each sensor input
R_INPUT_CAL_LSB1  = 0xB9
R_INPUT_CAL_LSB2  = 0xBA

# Product ID Registers
R_PRODUCT_ID      = 0xFD
R_MANUFACTURER_ID = 0xFE
R_REVISION        = 0xFF

# LED Behaviour settings
LED_BEHAVIOUR_DIRECT  = 0b00
LED_BEHAVIOUR_PULSE1  = 0b01
LED_BEHAVIOUR_PULSE2  = 0b10
LED_BEHAVIOUR_BREATHE = 0b11

LED_OPEN_DRAIN = 0 # Default, LED is open-drain output with ext pullup
LED_PUSH_PULL  = 1 # LED is driven HIGH/LOW with logic 1/0

LED_RAMP_RATE_2000MS = 7
LED_RAMP_RATE_1500MS = 6
LED_RAMP_RATE_1250MS = 5
LED_RAMP_RATE_1000MS = 4
LED_RAMP_RATE_750MS  = 3
LED_RAMP_RATE_500MS  = 2
LED_RAMP_RATE_250MS  = 1
LED_RAMP_RATE_0MS    = 0

## Basic stoppable thread wrapper
#
#  Adds Event for stopping the execution loop
#  and exiting cleanly.
class StoppableThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop_event = threading.Event()
        self.daemon = True         

    def alive(self):
        try:
            return self.isAlive()
        except AttributeError:
            # Python >= 3.9
            return self.is_alive()

    def start(self):
        if self.alive() == False:
            self.stop_event.clear()
            threading.Thread.start(self)

    def stop(self):
        if self.alive() == True:
            # set event to signal thread to terminate
            self.stop_event.set()
            # block calling thread until thread really has terminated
            self.join()

## Basic thread wrapper class for asyncronously running functions
#
#  Basic thread wrapper class for running functions
#  asyncronously. Return False from your function
#  to abort looping.
class AsyncWorker(StoppableThread):
    def __init__(self, todo):
        StoppableThread.__init__(self)
        self.todo = todo

    def run(self):
        while self.stop_event.is_set() == False:
            if self.todo() == False:
                self.stop_event.set()
                break


class CapTouchEvent():
    def __init__(self, channel, event, delta):
        self.channel = channel
        self.event = event
        self.delta = delta

class Cap1xxx():
    supported = [PID_CAP1208, PID_CAP1188, PID_CAP1166]
    number_of_inputs = 8
    number_of_leds   = 8
  
    def __init__(self, i2c_addr=DEFAULT_ADDR, i2c_bus=1, alert_pin=-1, reset_pin=-1, on_touch=None, skip_init=False):
        if on_touch == None:
            on_touch = [None] * self.number_of_inputs

        self.async_poll = None
        self.i2c_addr   = i2c_addr
        self.i2c        = SMBus(i2c_bus)
        self.alert_pin  = alert_pin
        self.reset_pin  = reset_pin
        self._delta     = 50

        GPIO.setmode(GPIO.BCM)
        if not self.alert_pin == -1:
            GPIO.setup(self.alert_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        if not self.reset_pin == -1:
            GPIO.setup(self.reset_pin,  GPIO.OUT)
            GPIO.setup(self.reset_pin,  GPIO.LOW)
            GPIO.output(self.reset_pin, GPIO.HIGH)
            time.sleep(0.01)
            GPIO.output(self.reset_pin, GPIO.LOW)

        self.handlers = {
            'press'   : [None] * self.number_of_inputs,
            'release' : [None] * self.number_of_inputs,
            'held'    : [None] * self.number_of_inputs
        }

        self.touch_handlers    = on_touch
        self.last_input_status = [False]  * self.number_of_inputs
        self.input_status      = ['none'] * self.number_of_inputs
        self.input_delta       = [0] * self.number_of_inputs
        self.input_pressed     = [False]  * self.number_of_inputs
        self.repeat_enabled    = 0b00000000
        self.release_enabled   = 0b11111111
        
        self.product_id = self._get_product_id()

        if not self.product_id in self.supported:
            raise Exception("Product ID {} not supported!".format(self.product_id))

        if skip_init:
            return

        # Enable all inputs with interrupt by default
        self.enable_inputs(0b11111111)
        self.enable_interrupts(0b11111111)

        # Disable repeat for all channels, but give
        # it sane defaults anyway
        self.enable_repeat(0b00000000)
        self.enable_multitouch(True)

        self.set_hold_delay(210)
        self.set_repeat_rate(210)

        # Tested sane defaults for various configurations
        self._write_byte(R_SAMPLING_CONFIG, 0b00001000) # 1sample per measure, 1.28ms time, 35ms cycle
        self._write_byte(R_SENSITIVITY,     0b01100000) # 2x sensitivity
        self._write_byte(R_GENERAL_CONFIG,  0b00111000)
        self._write_byte(R_CONFIGURATION2,  0b01100000)
        self.set_touch_delta(10)

        atexit.register(self.stop_watching)

    def get_input_status(self):
        """Get the status of all inputs.
        Returns an array of 8 boolean values indicating
        whether an input has been triggered since the
        interrupt flag was last cleared."""
        touched = self._read_byte(R_INPUT_STATUS)
        threshold = self._read_block(R_INPUT_1_THRESH, self.number_of_inputs)
        delta = self._read_block(R_INPUT_1_DELTA, self.number_of_inputs)
        #status = ['none'] * 8
        for x in range(self.number_of_inputs):
            if (1 << x) & touched:
                status = 'none'
                _delta = self._get_twos_comp(delta[x]) 
                #threshold = self._read_byte(R_INPUT_1_THRESH + x)
                # We only ever want to detect PRESS events
                # If repeat is disabled, and release detect is enabled
                if _delta >= threshold[x]: # self._delta:
                    self.input_delta[x] = _delta
                    #  Touch down event
                    if self.input_status[x] in ['press','held']:
                        if self.repeat_enabled & (1 << x):
                            status = 'held'
                    if self.input_status[x] in ['none','release']:
                        if self.input_pressed[x]:
                            status = 'none'
                        else:
                            status = 'press'
                else:
                    # Touch release event
                    if self.release_enabled & (1 << x) and not self.input_status[x] == 'release':
                        status = 'release'
                    else:
                        status = 'none'

                self.input_status[x] = status
                self.input_pressed[x] = status in ['press','held','none']
            else:
                self.input_status[x] = 'none'
                self.input_pressed[x] = False
        return self.input_status

    def _get_twos_comp(self,val):
        if ( val & (1<< (8 - 1))) != 0:
            val = val - (1 << 8)
        return val
        
    def clear_interrupt(self):
        """Clear the interrupt flag, bit 0, of the
        main control register"""
        main = self._read_byte(R_MAIN_CONTROL)
        main &= ~0b00000001
        self._write_byte(R_MAIN_CONTROL, main)

    def _interrupt_status(self):
        if self.alert_pin == -1:
            return self._read_byte(R_MAIN_CONTROL) & 1
        else:
            return not GPIO.input(self.alert_pin)

    def wait_for_interrupt(self, timeout=100):
        """Wait for, interrupt, bit 0 of the main
        control register to be set, indicating an
        input has been triggered."""
        start = self._millis()
        while True:
            status = self._interrupt_status() # self._read_byte(R_MAIN_CONTROL)
            if status:
                return True
            if self._millis() > start + timeout:
                return False
            time.sleep(0.005)

    def on(self, channel=0, event='press', handler=None):
        self.handlers[event][channel] = handler
        self.start_watching()
        return True

    def start_watching(self):
        if not self.alert_pin == -1:
            try:
                GPIO.add_event_detect(self.alert_pin, GPIO.FALLING, callback=self._handle_alert, bouncetime=1)
                self.clear_interrupt()
            except:
                pass
            return True

        if self.async_poll == None:
            self.async_poll = AsyncWorker(self._poll)
            self.async_poll.start()
            return True
        return False

    def stop_watching(self):
        if not self.alert_pin == -1:
            GPIO.remove_event_detect(self.alert_pin)

        if not self.async_poll == None:
            self.async_poll.stop()
            self.async_poll = None
            return True
        return False

    def set_touch_delta(self, delta):
        self._delta = delta

    def auto_recalibrate(self, value):
        self._change_bit(R_GENERAL_CONFIG, 3, value)
        
    def filter_analog_noise(self, value):
        self._change_bit(R_GENERAL_CONFIG, 4, not value)
        
    def filter_digital_noise(self, value):
        self._change_bit(R_GENERAL_CONFIG, 5, not value)

    def set_hold_delay(self, ms):
        """Set time before a press and hold is detected,
        Clamps to multiples of 35 from 35 to 560"""
        repeat_rate = self._calc_touch_rate(ms)
        input_config = self._read_byte(R_INPUT_CONFIG2)
        input_config = (input_config & ~0b1111) | repeat_rate
        self._write_byte(R_INPUT_CONFIG2, input_config)

    def set_repeat_rate(self, ms):
        """Set repeat rate in milliseconds, 
        Clamps to multiples of 35 from 35 to 560"""
        repeat_rate = self._calc_touch_rate(ms)
        input_config = self._read_byte(R_INPUT_CONFIG)
        input_config = (input_config & ~0b1111) | repeat_rate
        self._write_byte(R_INPUT_CONFIG, input_config)

    def _calc_touch_rate(self, ms):
        ms = min(max(ms,0),560)
        scale = int((round(ms / 35.0) * 35) - 35) / 35
        return int(scale)

    def _handle_alert(self, pin=-1):
        inputs = self.get_input_status()
        self.clear_interrupt()
        for x in range(self.number_of_inputs):
            self._trigger_handler(x, inputs[x])

    def _poll(self):
        """Single polling pass, should be called in
        a loop, preferably threaded."""
        if self.wait_for_interrupt():
            self._handle_alert()

    def _trigger_handler(self, channel, event):
        if event == 'none':
            return
        if callable(self.handlers[event][channel]):
            try:
                self.handlers[event][channel](CapTouchEvent(channel, event, self.input_delta[channel]))
            except TypeError:
                self.handlers[event][channel](channel, event)

    def _get_product_id(self):
        return self._read_byte(R_PRODUCT_ID)

    def enable_multitouch(self, en=True):
        """Toggles multi-touch by toggling the multi-touch
        block bit in the config register"""
        ret_mt = self._read_byte(R_MTOUCH_CONFIG)
        if en:
            self._write_byte(R_MTOUCH_CONFIG, ret_mt & ~0x80)
        else:
            self._write_byte(R_MTOUCH_CONFIG, ret_mt | 0x80 )

    def enable_repeat(self, inputs):
        self.repeat_enabled = inputs
        self._write_byte(R_REPEAT_EN, inputs)

    def enable_interrupts(self, inputs):
        self._write_byte(R_INTERRUPT_EN, inputs)

    def enable_inputs(self, inputs):
        self._write_byte(R_INPUT_ENABLE, inputs)

    def _write_byte(self, register, value):
        self.i2c.write_byte_data(self.i2c_addr, register, value)

    def _read_byte(self, register):
        return self.i2c.read_byte_data(self.i2c_addr, register)

    def _read_block(self, register, length):
        return self.i2c.read_i2c_block_data(self.i2c_addr, register, length)

    def _millis(self):
        return int(round(time.time() * 1000))

    def _set_bit(self, register, bit):
        self._write_byte( register, self._read_byte(register) | (1 << bit) )

    def _clear_bit(self, register, bit):
        self._write_byte( register, self._read_byte(register) & ~(1 << bit ) )

    def _change_bit(self, register, bit, state):
        if state:
            self._set_bit(register, bit)
        else:
            self._clear_bit(register, bit)

    def _change_bits(self, register, offset, size, bits):
        original_value = self._read_byte(register)
        for x in range(size):
            original_value &= ~(1 << (offset+x))
        original_value |= (bits << offset)
        self._write_byte(register, original_value)

    def __del__(self):
        self.stop_watching()
        
class Cap1xxxLeds(Cap1xxx):
    def set_led_linking(self, led_index, state):
        if led_index >= self.number_of_leds:
            return False
        self._change_bit(R_LED_LINKING, led_index, state)

    def set_led_output_type(self, led_index, state):
        if led_index >= self.number_of_leds:
            return False
        self._change_bit(R_LED_OUTPUT_TYPE, led_index, state)
 
    def set_led_state(self, led_index, state):
        if led_index >= self.number_of_leds:
            return False
        self._change_bit(R_LED_OUTPUT_CON, led_index, state)

    def set_led_polarity(self, led_index, state):
        if led_index >= self.number_of_leds:
            return False
        self._change_bit(R_LED_POLARITY, led_index, state)

    def set_led_behaviour(self, led_index, value):
        '''Set the behaviour of a LED'''
        offset = (led_index * 2) % 8
        register = led_index / 4
        value &= 0b00000011
        self._change_bits(R_LED_BEHAVIOUR_1 + register, offset, 2, value)

    def set_led_pulse1_period(self, period_in_seconds):
        '''Set the overall period of a pulse from 32ms to 4.064 seconds'''
        period_in_seconds = min(period_in_seconds, 4.064)
        value = int(period_in_seconds * 1000.0 / 32.0) & 0b01111111
        self._change_bits(R_LED_PULSE_1_PER, 0, 7, value)

    def set_led_pulse2_period(self, period_in_seconds):
        '''Set the overall period of a pulse from 32ms to 4.064 seconds'''
        period_in_seconds = min(period_in_seconds, 4.064)
        value = int(period_in_seconds * 1000.0 / 32.0) & 0b01111111
        self._change_bits(R_PULSE_LED_2_PER, 0, 7, value)

    def set_led_breathe_period(self, period_in_seconds):
        period_in_seconds = min(period_in_seconds, 4.064)
        value = int(period_in_seconds * 1000.0 / 32.0) & 0b01111111
        self._change_bits(R_LED_BREATHE_PER, 0, 7, value)

    def set_led_pulse1_count(self, count):
        count -= 1
        count &= 0b111
        self._change_bits(R_LED_CONFIG, 0, 3, count)

    def set_led_pulse2_count(self, count):
        count -= 1
        count &= 0b111
        self._change_bits(R_LED_CONFIG, 3, 3, count)

    def set_led_ramp_alert(self, value):
        self._change_bit(R_LED_CONFIG, 6, value)

    def set_led_direct_ramp_rate(self, rise_rate=0, fall_rate=0):
        '''Set the rise/fall rate in ms, max 2000.

        Rounds input to the nearest valid value.

        Valid values are 0, 250, 500, 750, 1000, 1250, 1500, 2000

        '''
        rise_rate = int(round(rise_rate / 250.0))
        fall_rate = int(round(fall_rate / 250.0))

        rise_rate = min(7, rise_rate)
        fall_rate = min(7, fall_rate)

        rate = (rise_rate << 4) | fall_rate
        self._write_byte(R_LED_DIRECT_RAMP, rate)

    def set_led_direct_duty(self, duty_min, duty_max):
        value = (duty_max << 4) | duty_min
        self._write_byte(R_LED_DIRECT_DUT, value)

    def set_led_pulse1_duty(self, duty_min, duty_max):
        value = (duty_max << 4) | duty_min
        self._write_byte(R_LED_PULSE_1_DUT, value)

    def set_led_pulse2_duty(self, duty_min, duty_max):
        value = (duty_max << 4) | duty_min
        self._write_byte(R_LED_PULSE_2_DUT, value)

    def set_led_breathe_duty(self, duty_min, duty_max):
        value = (duty_max << 4) | duty_min
        self._write_byte(R_LED_BREATHE_DUT, value)

    def set_led_direct_min_duty(self, value):
        self._change_bits(R_LED_DIRECT_DUT, 0, 4, value)

    def set_led_direct_max_duty(self, value):
        self._change_bits(R_LED_DIRECT_DUT, 4, 4, value)

    def set_led_breathe_min_duty(self, value):
        self._change_bits(R_LED_BREATHE_DUT, 0, 4, value)

    def set_led_breathe_max_duty(self, value):
        self._change_bits(R_LED_BREATHE_DUT, 4, 4, value)

    def set_led_pulse1_min_duty(self, value):
        self._change_bits(R_LED_PULSE_1_DUT, 0, 4, value)

    def set_led_pulse1_max_duty(self, value):
        self._change_bits(R_LED_PULSE_1_DUT, 4, 4, value)

    def set_led_pulse2_min_duty(self, value):
        self._change_bits(R_LED_PULSE_2_DUT, 0, 4, value)

    def set_led_pulse2_max_duty(self, value):
        self._change_bits(R_LED_PULSE_2_DUT, 4, 4, value)

class Cap1208(Cap1xxx):
    supported = [PID_CAP1208]

class Cap1188(Cap1xxxLeds):
    number_of_leds  = 8
    supported = [PID_CAP1188]

class Cap1166(Cap1xxxLeds):
    number_of_inputs = 6
    number_of_leds   = 6
    supported = [PID_CAP1166]

def DetectCap(i2c_addr, i2c_bus, product_id):
    bus = SMBus(i2c_bus)

    try:
        if bus.read_byte_data(i2c_addr, R_PRODUCT_ID) == product_id:
            return True
        else:
            return False
    except IOError:
        return False
    