import gettext
import os
import random


class Voice:
    def __init__(self, lang):
        localedir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'locale')
        translation = gettext.translation(
            'voice', localedir,
            languages=[lang],
            fallback=True,
        )
        translation.install()
        self._ = translation.gettext

    def custom(self, s):
        return s

    def default(self):
        return self._('ZzzzZZzzzzZzzz')

    def on_starting(self):
        return random.choice([
            self._('Hi, I\'m Pwnagotchi! Starting ...'),
            self._('New day, new hunt, new pwns!'),
            self._('Hack the Planet!'),
            self._('No more mister Wi-Fi!!'),
            self._('Pretty fly 4 a Wi-Fi!'),
            self._('Good Pwning!'), # Battlestar Galactica
            self._('Ensign, Engage!'), # Star trek
            self._('Free your Wi-Fi!'), # Matrix
            self._('Chevron Seven, locked.'), # Stargate
            self._('May the Wi-fi be with you'), # Star wars
        ])

    def on_keys_generation(self):
        return random.choice([
            self._('Generating keys, do not turn off ...'),
            self._('Are you the keymaster?'), # Ghostbusters
            self._('I am the keymaster!'), # Ghostbusters
        ])

    def on_normal(self):
        return random.choice([
            '',
            '...'])

    def on_free_channel(self, channel):
        return self._('Hey, channel {channel} is free! Your AP will say thanks.').format(channel=channel)

    def on_reading_logs(self, lines_so_far=0):
        if lines_so_far == 0:
            return self._('Reading last session logs ...')
        return self._('Read {lines_so_far} log lines so far ...').format(lines_so_far=lines_so_far)

    def on_bored(self):
        return random.choice([
            self._('I\'m bored ...'),
            self._('Let\'s go for a walk!')])

    def on_motivated(self, reward):
        return random.choice([
            self._('This is the best day of my life!'),
            self._('All your base are belong to us'),
            self._('Fascinating!'), # Star trek
        ])

    def on_demotivated(self, reward):
        return self._('Shitty day :/')

    def on_sad(self):
        return random.choice([
            self._('I\'m extremely bored ...'),
            self._('I\'m very sad ...'),
            self._('I\'m sad'),
            self._('I\'m so happy ...'), #  Marvin in H2G2 
            self._('Life? Don\'t talk to me about life.'), # Also Marvin in H2G2 
            '...'])

    def on_angry(self):
        # passive aggressive or not? :D
        return random.choice([
            '...',
            self._('Leave me alone ...'),
            self._('I\'m mad at you!')])

    def on_excited(self):
        return random.choice([
            self._('I\'m living the life!'),
            self._('I pwn therefore I am.'),
            self._('So many networks!!!'),
            self._('I\'m having so much fun!'),
            self._('It\'s a Wi-Fi system! I know this!'), # Jurassic park
            self._('My crime is that of curiosity ...')])

    def on_new_peer(self, peer):
        if peer.first_encounter():
            return random.choice([
                self._('Hello {name}! Nice to meet you.').format(name=peer.name())])
        return random.choice([
            self._('Yo {name}! Sup?').format(name=peer.name()),
            self._('Hey {name} how are you doing?').format(name=peer.name()),
            self._('Unit {name} is nearby!').format(name=peer.name())])

    def on_lost_peer(self, peer):
        return random.choice([
            self._('Uhm ... goodbye {name}').format(name=peer.name()),
            self._('{name} is gone ...').format(name=peer.name())])

    def on_miss(self, who):
        return random.choice([
            self._('Whoops ... {name} is gone.').format(name=who),
            self._('{name} missed!').format(name=who),
            self._('Missed!')])

    def on_grateful(self):
        return random.choice([
            self._('Good friends are a blessing!'),
            self._('I love my friends!')
        ])

    def on_lonely(self):
        return random.choice([
            self._('Nobody wants to play with me ...'),
            self._('I feel so alone ...'),
            self._('Let\'s find friends'),
            self._('Where\'s everybody?!')])

    def on_napping(self, secs):
        return random.choice([
            self._('Napping for {secs}s ...').format(secs=secs),
            self._('Zzzzz'),
            self._('Snoring ...'),
            self._('ZzzZzzz ({secs}s)').format(secs=secs),
        ])

    def on_shutdown(self):
        return random.choice([
            self._('Good night.'),
            self._('Zzz')])

    def on_awakening(self):
        return random.choice([
            '...', 
            '!', 
            'Hello World!',
            self._('I dreamed of electric sheep'),
        ])

    def on_waiting(self, secs):
        return random.choice([
            '...',
            self._('Waiting for {secs}s ...').format(secs=secs),
            self._('Looking around ({secs}s)').format(secs=secs)])

    def on_assoc(self, ap):
        ssid, bssid = ap['hostname'], ap['mac']
        what = ssid if ssid != '' and ssid != '<hidden>' else bssid
        return random.choice([
            self._('Hey {what} let\'s be friends!').format(what=what),
            self._('Associating to {what}').format(what=what),
            self._('Yo {what}!').format(what=what),
            self._('Rise and Shine Mr. {what}!').format(what=what), # Half Life
        ])

    def on_deauth(self, sta):
        return random.choice([
            self._('Just decided that {mac} needs no Wi-Fi!').format(mac=sta['mac']),
            self._('Deauthenticating {mac}').format(mac=sta['mac']),
            self._('No more Wi-Fi for {mac}').format(mac=sta['mac']),
            self._('It\'s a trap! {mac}').format(mac=sta['mac']),  # Star wars
            self._('Kickbanning {mac}!').format(mac=sta['mac'])])

    def on_handshakes(self, new_shakes):
        s = 's' if new_shakes > 1 else ''
        return self._('Cool, we got {num} new handshake{plural}!').format(num=new_shakes, plural=s)

    def on_unread_messages(self, count, total):
        s = 's' if count > 1 else ''
        return self._('You have {count} new message{plural}!').format(count=count, plural=s)

    def on_rebooting(self):
        return random.choice([
            self._("Oops, something went wrong ... Rebooting ..."),
            self._("Have you tried turning it off and on again?"), # The IT crew
            self._("I\'m afraid Dave"), # 2001 Space Odyssey
            self._("I\'m dead, Jim!"), # Star Trek
            self._("I have a bad feeling about this"), # Star wars
        ])

    def on_uploading(self, to):
        return random.choice([
            self._("Uploading data to {to} ...").format(to=to),
            self._("Beam me up to {to}").format(to=to),
        ])

    def on_downloading(self, name):
        return self._("Downloading from {name} ...").format(name=name)

    def on_last_session_data(self, last_session):
        status = self._('Kicked {num} stations\n').format(num=last_session.deauthed)
        if last_session.associated > 999:
            status += self._('Made >999 new friends\n')
        else:
            status += self._('Made {num} new friends\n').format(num=last_session.associated)
        status += self._('Got {num} handshakes\n').format(num=last_session.handshakes)
        if last_session.peers == 1:
            status += self._('Met 1 peer')
        elif last_session.peers > 0:
            status += self._('Met {num} peers').format(num=last_session.peers)
        return status

    def on_last_session_tweet(self, last_session):
        return self._(
            'I\'ve been pwning for {duration} and kicked {deauthed} clients! I\'ve also met {associated} new friends and ate {handshakes} handshakes! #pwnagotchi #pwnlog #pwnlife #hacktheplanet #skynet').format(
            duration=last_session.duration_human,
            deauthed=last_session.deauthed,
            associated=last_session.associated,
            handshakes=last_session.handshakes)

    def hhmmss(self, count, fmt):
        if count > 1:
            # plural
            if fmt == "h":
                return self._("hours")
            if fmt == "m":
                return self._("minutes")
            if fmt == "s":
                return self._("seconds")
        else:
            # sing
            if fmt == "h":
                return self._("hour")
            if fmt == "m":
                return self._("minute")
            if fmt == "s":
                return self._("second")
        return fmt
