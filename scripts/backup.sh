#!/bin/sh

usage() {
	echo "Usage: backup.sh [-honu] [-h] [-u user] [-n host name or ip] [-o output]"
}

while getopts "ho:n:u:" arg; do
	case $arg in
		h)
			usage
			exit
			;;
		n)
			UNIT_HOSTNAME=$OPTARG
			;;
		o)
			OUTPUT=$OPTARG
			;;
		u)
			UNIT_USERNAME=$OPTARG
			;;
		*)
			usage
			exit 1
	esac
done

# name of the ethernet gadget interface on the host
UNIT_HOSTNAME=${UNIT_HOSTNAME:-10.0.0.2}
# output backup tgz file
OUTPUT=${OUTPUT:-${UNIT_HOSTNAME}-backup-$(date +%s).tgz}
# username to use for ssh
UNIT_USERNAME=${UNIT_USERNAME:-pi}
# what to backup
FILES_TO_BACKUP="
    /boot/firmware/cmdline.txt \
    /boot/firmware/config.txt \
    /root/settings.yaml \
    /root/client_secrets.json \
    /root/.api-report.json \
    /root/.ssh \
    /root/.bashrc \
    /root/.profile \
    /home/pi/handshakes \
    /root/peers \
    /etc/modprobe.d/g_ether.conf \
    /etc/pwnagotchi/ \
    /etc/ssh/ \
    /etc/pwnagotchi/log/pwnagotchi.log \
    /etc/pwnagotchi/log/pwnagotchi*.gz \
    /home/pi/.ssh \
    /home/pi/.bashrc \
    /home/pi/.profile \
    /root/.api-report.json \
    /root/.auto-update \
    /root/.bt-tether* \
    /root/.ohc_uploads \
    /root/.wigle_uploads \
    /home/pi/.wpa_sec_uploads"

ping -c 1 "${UNIT_HOSTNAME}" > /dev/null 2>&1 || {
  echo "@ unit ${UNIT_HOSTNAME} can't be reached, make sure it's connected and a static IP assigned to the USB interface."
  exit 1
}

echo "@ backing up $UNIT_HOSTNAME to $OUTPUT ..."
# shellcheck disable=SC2029
ssh "${UNIT_USERNAME}@${UNIT_HOSTNAME}" "sudo find ${FILES_TO_BACKUP} -type f -print0 | xargs -0 sudo tar cv" | gzip -9 > "$OUTPUT"
