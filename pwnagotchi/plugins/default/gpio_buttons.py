import logging
import RPi.GPIO as GPIO
import subprocess
import pwnagotchi.plugins as plugins

"""
This plugin uses the BCM GPIO Number - not the physicaly pin number!

Depending on hardware attached to the Pwnagotchi - these GPIO pins may / or may not be in-use.
You will need to do your research for your specific hardware to find what GPIO pins it uses - if any at all.
If the pins are in use by the hardware, they can not be used with buttons.

IF hardware uses a GPIO Pin, the line in config.toml should be commented out or deleted entirely.
Failure to do so may make the 'gotchi unbootable. If that happens you'll need to pull your SD card
and edit the [rootfs]/etc/pwnagotchi/config.toml file on your computer - you've been warned!

The examples below only enter "GPIO Pin X Triggered" into the log.
You will want to set them to your custom commands you would enter into your SSH Shell
eg: "sudo systemctl stop pwnagotchi && sudo pwnagotchi --clear && sudo shutdown -h now"

config.toml

main.plugins.gpio_buttons.enabled = false
#main.plugins.gpio_buttons.gpios.5 = "GPIO Pin 5 Triggered" #physical pin 29 - unused but constant false triggers.
main.plugins.gpio_buttons.gpios.6 = "GPIO Pin 6 Triggered" #physical pin 31
main.plugins.gpio_buttons.gpios.16 = "GPIO Pin 16 Triggered" #physical pin 36
#main.plugins.gpio_buttons.gpios.17 = "GPIO Pin 17 Triggered" #physical pin 11 - used by Waveshare eInk hat
main.plugins.gpio_buttons.gpios.22 = "GPIO Pin 22 Triggered" #physical pin 15
main.plugins.gpio_buttons.gpios.23 = "GPIO Pin 23 Triggered" #physical pin 16
#main.plugins.gpio_buttons.gpios.24 = "GPIO Pin 24 Triggered" #physical pin 18 - used by Waveshare eInk hat
#main.plugins.gpio_buttons.gpios.25 = "GPIO Pin 25 Triggered" #physical pin 22 - used by Waveshare eInk hat
main.plugins.gpio_buttons.gpios.26 = "GPIO Pin 26 Triggered" #physical pin 37
#main.plugins.gpio_buttons.gpios.27 = "GPIO Pin 27 Triggered" #physical pin 13 - used by Waveshare GPS LC29
"""

class GPIOButtons(plugins.Plugin):
    __author__ = 'ratmandu@gmail.com'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'GPIO Button support plugin'
    __help__ = 'https://tieske.github.io/rpi-gpio/modules/GPIO.html'

    def __init__(self):
        self.running = False
        self.ports = {}
        self.commands = None
        self.options = dict()

    def runcommand(self, channel):
        command = self.ports[channel]
        logging.info(f"Button Pressed! Running command: {command}")
        process = subprocess.Popen(command, shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None,
                                   executable="/bin/bash")
        process.wait()

    def on_loaded(self):
        logging.info("GPIO Button plugin loaded.")

        # Reset GPIO state to avoid conflicts
        GPIO.cleanup()

        # get list of GPIOs
        gpios = self.options['gpios']

        # set gpio numbering
        GPIO.setmode(GPIO.BCM)

        for gpio, command in gpios.items():
            gpio = int(gpio)
            self.ports[gpio] = command
            GPIO.setup(gpio, GPIO.IN, GPIO.PUD_UP)
            GPIO.add_event_detect(gpio, GPIO.FALLING, callback=self.runcommand, bouncetime=600)
            # set pimoroni display hat mini LED off/dim
            #GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            #GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            #GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            logging.info("Added command: %s to GPIO #%d", command, gpio)
