#!/bin/bash

echo "Down connections"
IFS=$'\n'
for connection in $(nmcli -g NAME,TYPE c | grep bluetooth | cut -d: -f1)
do
	nmcli connection down "$connection" 2> /dev/null 
done
  
echo "Down devices"
for device in $(bluetoothctl devices  | grep -o "[[:xdigit:]:]\{8,17\}")
do
	nmcli device down $device 2> /dev/null
	bluetoothctl disconnect $device 2> /dev/null
done
echo "Stoping bluetooth daemon"
systemctl stop bluetooth

echo "Down hci0"
hciconfig hci0 down

echo "Removing modules"
rmmod -f -v hci_uart
rmmod -f -v btbcm
rmmod -f -v bnep
rmmod -f -v bluetooth

echo Loading modules

modprobe -v btbcm 
modprobe -v hci_uart 
modprobe -v bnep 
modprobe -v bluetooth

echo "Up hci0"
hciconfig hci0 up
hciconfig hci0 reset

echo "Restart daemons"
systemctl start bluetooth
systemctl restart NetworkManager

echo "Bluetooth on" 
bluetoothctl agent on
