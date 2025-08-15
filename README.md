# Pwnagotchi
This is the main source for all forks:
- RPiZeroW (32bit)
- RPiZero2W, RPi3, RPi4, RPi5 (64bit)

**For installation docs check out the [wiki](https://github.com/jayofelony/pwnagotchi/wiki)!**

If you want to sponsor this project you can use GH Sponsor or cryptocurrency:

[GH Sponsor](https://github.com/sponsors/jayofelony)

Or send some ethereum: 0x33ceC4Abe80fDE460a924d596d4dE31Bc0767bb6

**Proudly partnering with [PiSugar](https://www.pisugar.com)!!**

---

[Pwnagotchi](https://pwnagotchi.org/) is a Raspberry Pi leveraging [bettercap](https://www.bettercap.org/) that survives from its surrounding Wi-Fi environment to maximize the crackable WPA key material it captures (either passively, or by performing authentication and association attacks). This material is collected as PCAP files containing any form of handshake supported by [hashcat](https://hashcat.net/hashcat/), including [PMKIDs](https://www.evilsocket.net/2019/02/13/Pwning-WiFi-networks-with-bettercap-and-the-PMKID-client-less-attack/), 
full and half WPA handshakes.

![ui](https://i.imgur.com/X68GXrn.png)

The "old" Pwnagotchi used to have AI to help it learn from its environment, but since then AI seemed to destabilize the Wi-Fi firmware. So I have chosen to remove the AI completely to give the Pwnagotchi more up-time and longer battery life when taking it on a walk.

Multiple units within close physical proximity can "talk" to each other, advertising their presence to each other by broadcasting custom information elements using a parasite protocol I've built on top of the existing dot11 standard.

## Documentation

https://github.com/jayofelony/pwnagotchi/wiki 
https://pwnagotchi.org

## Links

| &nbsp;    | Official Links                                           |
|-----------|----------------------------------------------------------|
| Website   | [pwnagotchi.org](https://pwnagotchi.org/)                  |
| Chat      | [discord](https://discord.gg/PGgnzFbz4M) |
| Subreddit | [r/pwnagotchi](https://www.reddit.com/r/pwnagotchi/)     |

## License

`pwnagotchi` created by [@evilsocket](https://x.com/evilsocket) and updated by [us](https://github.com/jayofelony/pwnagotchi/graphs/contributors). It is released under the GPL3 license.
