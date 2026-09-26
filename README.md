# Pwnagotchi
This is the main source for all forks:
- RPiZeroW (32bit) older versions work, no more new releases as it now more a legacy device
- RPiZero2W, RPi3, RPi4, RPi5 (64bit)

**For installation docs check out the [wiki](https://github.com/jayofelony/pwnagotchi/wiki)!**

If you want to sponsor this project you can use GH Sponsor or cryptocurrency:

[GH Sponsor](https://github.com/sponsors/jayofelony)

Or send some ethereum: 0x33ceC4Abe80fDE460a924d596d4dE31Bc0767bb6

**Proudly partnering with [PiSugar](https://www.pisugar.com)!!**

---

[Pwnagotchi](https://pwnagotchi.org/) is a Raspberry Pi leveraging [bettercap](https://www.bettercap.org/) that survives from its surrounding Wi-Fi environment to maximize the crackable WPA key material it captures (either passively, or by performing authentication and association attacks). This material is collected as PCAPNG files containing any form of handshake supported by [hashcat](https://hashcat.net/hashcat/), including [PMKIDs](https://www.evilsocket.net/2019/02/13/Pwning-WiFi-networks-with-bettercap-and-the-PMKID-client-less-attack/), 
full and half WPA handshakes.

![ui](https://i.imgur.com/X68GXrn.png)

The "old" Pwnagotchi used to have AI to help it learn from its environment, but since then AI seemed to destabilize the Wi-Fi firmware. So I have chosen to remove the AI completely to give the Pwnagotchi more up-time and longer battery life when taking it on a walk.

Multiple units within close physical proximity can "talk" to each other, advertising their presence to each other by broadcasting custom information elements using a parasite protocol [@evilsocket](https://x.com/evilsocket) built on top of the existing dot11 standard.

## Documentation

https://github.com/jayofelony/pwnagotchi/wiki 
https://pwnagotchi.org

### USB gadget network configuration

Recent images use `rpi-usb-gadget` to switch the `usb0` link automatically
between a host DHCP client and a Pi-hosted shared network. Management from
Pwnagotchi is opt-in. To select a predictable, non-conflicting shared subnet,
add the following to `/etc/pwnagotchi/config.toml`:

```toml
[usb_gadget]
manage = true
mode = "shared"
interface = "usb0"
shared_address = "10.12.195.1/28"
check_conflicts = true
```

Valid modes are `auto`, `client`, and `shared`. `auto` preserves the upstream
ICS watcher behavior. Settings are applied on boot; they can also be applied
with `sudo systemctl restart pwnagotchi-usb-gadget.service`. Switching the
active mode or shared address can disconnect the current USB/SSH session.

## Links

| &nbsp;    | Official Links                                           |
|-----------|----------------------------------------------------------|
| Website   | [pwnagotchi.org](https://pwnagotchi.org/)                  |
| Chat      | [discord](https://discord.gg/PGgnzFbz4M) |
| Subreddit | [r/pwnagotchi](https://www.reddit.com/r/pwnagotchi/)     |

## License

`pwnagotchi` created by [@evilsocket](https://x.com/evilsocket) and updated by [us](https://github.com/jayofelony/pwnagotchi/graphs/contributors). It is released under the GPL3 license.
