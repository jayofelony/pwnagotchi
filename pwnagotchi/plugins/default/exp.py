import logging
import os
import random
import json

import pwnagotchi
import pwnagotchi.agent
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

# Static Variables
MULTIPLIER_ASSOCIATION = 1
MULTIPLIER_DEAUTH = 2
MULTIPLIER_HANDSHAKE = 3
MULTIPLIER_AI_BEST_REWARD = 5
TAG = "[EXP Plugin]"
FACE_LEVELUP = '(≧◡◡≦)'
BAR_ERROR = "|   error  |"
FILE_SAVE = "exp_stats"
FILE_SAVE_LEGACY = "exp"
JSON_KEY_LEVEL = "level"
JSON_KEY_EXP = "exp"
JSON_KEY_EXP_TOT = "exp_tot"


class EXP(plugins.Plugin):
    __author__ = 'GaelicThunder'
    __version__ = '1.0.5'
    __license__ = 'GPL3'
    __description__ = 'Get exp every time a handshake get captured.'

    # Attention number masking
    def LogInfo(self, text):
        logging.info(TAG + " " + text)

    # Attention number masking
    def LogDebug(self, text):
        logging.debug(TAG + " " + text)

    def __init__(self):
        self.percent = 0
        self.calculateInitialXP = False
        self.exp = 0
        self.lv = 1
        self.exp_tot = 0
        # Sets the file type I recommend json
        self.save_file_mode = self.save_file_modes("json")
        self.save_file = self.getSaveFileName(self.save_file_mode)
        # Migrate from old save system
        self.migrateLegacySave()

        # Create save file
        if not os.path.exists(self.save_file):
            self.Save(self.save_file, self.save_file_mode)
        else:
            try:
                # Try loading
                self.Load(self.save_file, self.save_file_mode)
            except:
                # Likely throws an exception if json file is corrupted, so we need to calculate from scratch
                self.calculateInitialXP = True

        # No previous data, try get it
        if self.lv == 1 and self.exp == 0:
            self.calculateInitialXP = True
        if self.exp_tot == 0:
            self.LogInfo("Need to calculate Total Exp")
            self.exp_tot = self.calcActualSum(self.lv, self.exp)
            self.Save(self.save_file, self.save_file_mode)

        self.expneeded = self.calcExpNeeded(self.lv)

    def on_loaded(self):
        # logging.info("Exp plugin loaded for %s" % self.options['device'])
        self.LogInfo("Plugin Loaded")

    def save_file_modes(self, argument):
        switcher = {
            "txt": 0,
            "json": 1,
        }
        return switcher.get(argument, 0)

    def Save(self, file, save_file_mode):
        self.LogDebug('Saving Exp')
        if save_file_mode == 0:
            self.saveToTxtFile(file)
        if save_file_mode == 1:
            self.saveToJsonFile(file)

    def saveToTxtFile(self, file):
        outfile = open(file, 'w')
        print(self.exp, file=outfile)
        print(self.lv, file=outfile)
        print(self.exp_tot, file=outfile)
        outfile.close()

    def loadFromTxtFile(self, file):
        if os.path.exists(file):
            outfile = open(file, 'r+')
            lines = outfile.readlines()
            linecounter = 1
            for line in lines:
                if linecounter == 1:
                    self.exp = int(line)
                elif linecounter == 2:
                    self.lv == int(line)
                elif linecounter == 3:
                    self.exp_tot == int(line)
                linecounter += 1
            outfile.close()

    def saveToJsonFile(self, file):
        data = {
            JSON_KEY_LEVEL: self.lv,
            JSON_KEY_EXP: self.exp,
            JSON_KEY_EXP_TOT: self.exp_tot
        }

        with open(file, 'w') as f:
            f.write(json.dumps(data, sort_keys=True, indent=4, separators=(',', ': ')))

    def loadFromJsonFile(self, file):
        # Tot exp is introduced with json, no check needed
        data = {}
        with open(file, 'r') as f:
            data = json.loads(f.read())

        if bool(data):
            self.lv = data[JSON_KEY_LEVEL]
            self.exp = data[JSON_KEY_EXP]
            self.exp_tot = data[JSON_KEY_EXP_TOT]
        else:
            self.LogInfo("Empty json")

    # TODO: one day change save file mode to file date
    def Load(self, file, save_file_mode):
        self.LogDebug('Loading Exp')
        if save_file_mode == 0:
            self.loadFromTxtFile(file)
        if save_file_mode == 1:
            self.loadFromJsonFile(file)

    def getSaveFileName(self, save_file_mode):
        file = os.path.dirname(os.path.realpath(__file__))
        file = file + "/" + FILE_SAVE
        if save_file_mode == 0:
            file = file + ".txt"
        elif save_file_mode == 1:
            file = file + ".json"
        else:
            # See switcher
            file = file + ".txt"
        return file

    def migrateLegacySave(self):
        legacyFile = os.path.dirname(os.path.realpath(__file__))
        legacyFile = legacyFile + "/" + FILE_SAVE_LEGACY + ".txt"
        if os.path.exists(legacyFile):
            self.loadFromTxtFile(legacyFile)
            self.LogInfo("Migrating Legacy Save...")
            self.Save(self.save_file, self.save_file_mode)
            os.remove(legacyFile)

    def barString(self, symbols_count, p):
        if p > 100:
            return BAR_ERROR
        length = symbols_count - 2
        bar_char = '▥'
        blank_char = ' '
        bar_length = int(round((length / 100) * p))
        blank_length = length - bar_length
        res = '|' + bar_char * bar_length + blank_char * blank_length + '|'
        return res

    def on_ui_setup(self, ui):
        ui.add_element('Lv', LabeledValue(color=BLACK, label='Lv', value=0,
                                          position=(int(self.options["lvl_x_coord"]),
                                                    int(self.options["lvl_y_coord"])),
                                          label_font=fonts.Bold, text_font=fonts.Medium))
        ui.add_element('Exp', LabeledValue(color=BLACK, label='Exp', value=0,
                                           position=(int(self.options["exp_x_coord"]),
                                                     int(self.options["exp_y_coord"])),
                                           label_font=fonts.Bold, text_font=fonts.Medium))

    def on_ui_update(self, ui):
        self.expneeded = self.calcExpNeeded(self.lv)
        self.percent = int((self.exp / self.expneeded) * 100)
        symbols_count = int(self.options["bar_symbols_count"])
        bar = self.barString(symbols_count, self.percent)
        ui.set('Lv', "%d" % self.lv)
        ui.set('Exp', "%s" % bar)

    def calcExpNeeded(self, level):
        # If the pwnagotchi is lvl <1 it causes the keys to be deleted
        if level == 1:
            return 5
        return int((level ** 3) / 2)

    def exp_check(self, agent):
        self.LogDebug("EXP CHECK")
        if self.exp >= self.expneeded:
            self.exp = 1
            self.lv = self.lv + 1
            self.expneeded = self.calcExpNeeded(self.lv)
            self.displayLevelUp(agent)

    def parseSessionStats(self):
        sum = 0
        dir = pwnagotchi.config['main']['plugins']['session-stats']['save_directory']
        # TODO: remove
        self.LogInfo("Session-Stats dir: " + dir)
        for filename in os.listdir(dir):
            self.LogInfo("Parsing " + filename + "...")
            if filename.endswith(".json") & filename.startswith("stats"):
                try:
                    sum += self.parseSessionStatsFile(os.path.join(dir, filename))
                except:
                    self.LogInfo("ERROR parsing File: " + filename)

        return sum

    def parseSessionStatsFile(self, path):
        sum = 0
        deauths = 0
        handshakes = 0
        associations = 0
        with open(path) as json_file:
            data = json.load(json_file)
            for entry in data["data"]:
                deauths += data["data"][entry]["num_deauths"]
                handshakes += data["data"][entry]["num_handshakes"]
                associations += data["data"][entry]["num_associations"]

        sum += deauths * MULTIPLIER_DEAUTH
        sum += handshakes * MULTIPLIER_HANDSHAKE
        sum += associations * MULTIPLIER_ASSOCIATION

        return sum

    # If initial sum is 0, we try to parse it
    def calculateInitialSum(self, agent):
        sessionStatsActive = False
        sum = 0
        # Check if session stats is loaded
        for plugin in pwnagotchi.plugins.loaded:
            if plugin == "session-stats":
                sessionStatsActive = True
                break

        if sessionStatsActive:
            try:
                self.LogInfo("parsing session-stats")
                sum = self.parseSessionStats()
            except:
                self.LogInfo("Error parsing session-stats")


        else:
            self.LogInfo("parsing last session")
            sum = self.lastSessionPoints(agent)

        self.LogInfo(str(sum) + " Points calculated")
        return sum

    # Get Last Sessions Points
    def lastSessionPoints(self, agent):
        summary = 0
        summary += agent.LastSession.handshakes * MULTIPLIER_HANDSHAKE
        summary += agent.LastSession.associated * MULTIPLIER_ASSOCIATION
        summary += agent.LastSession.deauthed * MULTIPLIER_DEAUTH
        return summary

    # Helper function to calculate multiple Levels from a sum of EXPs
    def calcLevelFromSum(self, sum, agent):
        sum1 = sum
        level = 1
        while sum1 > self.calcExpNeeded(level):
            sum1 -= self.calcExpNeeded(level)
            level += 1
        self.lv = level
        self.exp = sum1
        self.expneeded = self.calcExpNeeded(level) - sum1
        if level > 1:
            # get Excited ;-)
            self.displayLevelUp(agent)

    def calcActualSum(self, level, exp):
        lvlCounter = 1
        sum = exp
        # I know it wouldn't work if you change the lvl algorithm
        while lvlCounter < level:
            sum += self.calcExpNeeded(lvlCounter)
            lvlCounter += 1
        return sum

    def displayLevelUp(self, agent):
        view = agent.view()
        view.set('face', FACE_LEVELUP)
        view.set('status', "Level Up!")
        view.update(force=True)

    # Event Handling
    def on_association(self, agent, access_point):
        self.exp += MULTIPLIER_ASSOCIATION
        self.exp_tot += MULTIPLIER_ASSOCIATION
        self.exp_check(agent)
        self.Save(self.save_file, self.save_file_mode)

    def on_deauthentication(self, agent, access_point, client_station):
        self.exp += MULTIPLIER_DEAUTH
        self.exp_tot += MULTIPLIER_DEAUTH
        self.exp_check(agent)
        self.Save(self.save_file, self.save_file_mode)

    def on_handshake(self, agent, filename, access_point, client_station):
        self.exp += MULTIPLIER_HANDSHAKE
        self.exp_tot += MULTIPLIER_HANDSHAKE
        self.exp_check(agent)
        self.Save(self.save_file, self.save_file_mode)

    def on_ai_best_reward(self, agent, reward):
        self.exp += MULTIPLIER_AI_BEST_REWARD
        self.exp_tot += MULTIPLIER_AI_BEST_REWARD
        self.exp_check(agent)
        self.Save(self.save_file, self.save_file_mode)

    def on_ready(self, agent):
        if self.calculateInitialXP:
            self.LogInfo("Initial point calculation")
            sum = self.calculateInitialSum(agent)
            self.exp_tot = sum
            self.calcLevelFromSum(sum, agent)
            self.Save(self.save_file, self.save_file_mode)
