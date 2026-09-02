#!/bin/bash
# Sustained channel-hop soak for bcm43430a1/7_45_98.
#
# Requires the radio config that actually works on this port: wlan0 brought up
# once to initialise the MAC, then taken DOWN so the managed vif stops owning
# the channel. With wlan0 UP every hop is rejected by cfg80211 with EBUSY and
# never reaches brcmf_cfg80211_nexmon_set_channel - which is the function that
# produces the -110 failures in the field, so a test run that way proves nothing.
IW=/usr/sbin/iw

sudo ip link set wlan0 down 2>/dev/null
sleep 1

sudo timeout 320 tcpdump -i wlan0mon -nn -w /tmp/hop2.pcap >/dev/null 2>&1 &
TP=$!
sleep 3
sudo python3 /tmp/nexprobe.py monitor --mon 2 >/dev/null

echo "=== sustained hop test: 2s dwell, real set_channel path ==="
CH=(1 6 11 3 9 5 7 2 10 4 8)
fails=0
for i in $(seq 0 59); do
    c=${CH[$((i % 11))]}
    out=$(sudo $IW dev wlan0mon set channel "$c" 2>&1)
    rc=$?
    if [ $rc -ne 0 ]; then
        fails=$((fails + 1))
        echo "hop $i ch$c FAILED rc=$rc: $out"
    fi
    if [ $((i % 5)) -eq 0 ] || [ $rc -ne 0 ]; then
        s=$(sudo python3 /tmp/nexprobe.py sample 2>&1)
        echo "hop $(printf %-2d $i) ch$(printf %-2d $c) $s"
        case "$s" in
            *"NO REPLY"*|*INVALID*)
                echo "*** WEDGED at hop $i (after $((i+1)) channel changes) ***"
                break
                ;;
        esac
    fi
    sleep 2
done

echo "=== hop failures: $fails / 60 ==="
sudo kill $TP 2>/dev/null
wait 2>/dev/null
echo "=== rx frames captured: $(sudo tcpdump -r /tmp/hop2.pcap -nn 2>/dev/null | wc -l) ==="
echo "=== final sanity ==="
sudo python3 /tmp/nexprobe.py sanity
echo "=== dmesg 'Set Channel failed' count: $(sudo dmesg | grep -cE 'Set Channel failed') ==="
echo DONE
