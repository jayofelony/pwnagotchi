#!/usr/bin/env bash
#
# A Combined backup/restore script for linux
# Usage:
#   backup-restore.sh backup [ -n HOST ] [ -u USER ] [ -o OUTPUT ]
#   backup-restore.sh restore [ -n HOST ] [ -u USER ] [ -b BACKUP_FILE ]
#

###############################################################################
# GLOBAL USAGE
###############################################################################
usage() {
  echo "Usage:"
  echo "  $0 backup  [ -n HOST ] [ -u USER ] [ -o OUTPUT ]"
  echo "  $0 restore [ -n HOST ] [ -u USER ] [ -b BACKUP_FILE ]"
  echo
  echo "Subcommands:"
  echo "  backup      Backup files from the remote device."
  echo "  restore     Restore files to the remote device."
  echo
  echo "Common Options:"
  echo "  -n HOST     Hostname or IP of remote device (default: 10.0.0.2)"
  echo "  -u USER     Username for SSH (default: pi)"
  echo
  echo "Options for 'backup':"
  echo "  -o OUTPUT   Path/name of the output archive (default: \$HOST-backup-\$(date +%s).tgz)"
  echo
  echo "Options for 'restore':"
  echo "  -b BACKUP   Path to the local backup archive to restore."
  echo
  echo "Examples:"
  echo "  $0 backup"
  echo "  $0 backup -n 10.0.0.2 -u pi -o my-backup.tgz"
  echo "  $0 restore -b 10.0.0.2-backup-123456789.tgz"
  echo
}

###############################################################################
# BACKUP FUNCTION
###############################################################################
do_backup() {
  # Defaults
  UNIT_HOSTNAME="10.0.0.2"
  UNIT_USERNAME="pi"
  OUTPUT=""

  # Parse arguments specific to backup
  while getopts "hn:u:o:" arg; do
    case $arg in
      h)
        usage
        exit 0
        ;;
      n)
        UNIT_HOSTNAME=$OPTARG
        ;;
      u)
        UNIT_USERNAME=$OPTARG
        ;;
      o)
        OUTPUT=$OPTARG
        ;;
      *)
        usage
        exit 1
        ;;
    esac
  done

  # If OUTPUT was not specified, set a default
  if [[ -z "$OUTPUT" ]]; then
    OUTPUT="${UNIT_HOSTNAME}-backup-$(date +%s).tgz"
  fi

  # List of files/directories to backup
  # (the same list you used in your backup.sh script)
  FILES_TO_BACKUP="
/root/settings.yaml
/root/client_secrets.json
/root/.api-report.json
/root/.ssh
/root/.bashrc
/root/.profile
/home/pi/handshakes
/root/peers
/etc/pwnagotchi/
/usr/local/share/pwnagotchi/custom-plugins
/etc/ssh/
/home/pi/.bashrc
/home/pi/.profile
/home/pi/.wpa_sec_uploads
"
  # Convert multiline variable into a space-separated list
  FILES_TO_BACKUP=$(echo "$FILES_TO_BACKUP" | tr '\n' ' ')

  echo "@ Checking connectivity to $UNIT_HOSTNAME ..."
  if ! ping -c 1 "$UNIT_HOSTNAME" &>/dev/null; then
    echo "@ unit ${UNIT_HOSTNAME} can't be reached, check network or USB interface IP."
    exit 1
  fi

  echo "@ Backing up ${UNIT_HOSTNAME} to ${OUTPUT} ..."
  # -n => do not read from stdin
  ssh -n "${UNIT_USERNAME}@${UNIT_HOSTNAME}" \
    "sudo tar -cf - ${FILES_TO_BACKUP}" \
  | gzip -9 > "${OUTPUT}"

  echo "@ Backup finished. Archive: ${OUTPUT}"
}

###############################################################################
# RESTORE FUNCTION
###############################################################################
do_restore() {
  # Defaults
  UNIT_HOSTNAME="10.0.0.2"
  UNIT_USERNAME="pi"
  BACKUP_FILE=""

  # Parse arguments specific to restore
  while getopts "hn:u:b:" arg; do
    case $arg in
      h)
        usage
        exit 0
        ;;
      n)
        UNIT_HOSTNAME=$OPTARG
        ;;
      u)
        UNIT_USERNAME=$OPTARG
        ;;
      b)
        BACKUP_FILE=$OPTARG
        ;;
      *)
        usage
        exit 1
        ;;
    esac
  done

  # If no backup file given, try to find the latest
  if [[ -z "$BACKUP_FILE" ]]; then
    BACKUP_FILE=$(ls -rt "${UNIT_HOSTNAME}"-backup-*.tgz 2>/dev/null | tail -n1)
    if [[ -z "$BACKUP_FILE" ]]; then
      echo "@ Can't find backup file. Please specify one with '-b'."
      exit 1
    fi
    echo "@ Found backup file: $BACKUP_FILE"
    echo -n "@ Continue restoring this file? (y/n) "
    read -r CONTINUE
    CONTINUE=$(echo "${CONTINUE}" | tr "[:upper:]" "[:lower:]")
    if [[ "${CONTINUE}" != "y" ]]; then
      exit 1
    fi
  fi

  echo "@ Checking connectivity to $UNIT_HOSTNAME ..."
  if ! ping -c 1 "$UNIT_HOSTNAME" &>/dev/null; then
    echo "@ unit ${UNIT_HOSTNAME} can't be reached, make sure it's connected and a static IP assigned."
    exit 1
  fi

  echo "@ Restoring $BACKUP_FILE to $UNIT_HOSTNAME ..."
  cat "${BACKUP_FILE}" | ssh "${UNIT_USERNAME}@${UNIT_HOSTNAME}" "sudo tar xzv -C /"

  echo "@ Restore finished."
}

###############################################################################
# MAIN ENTRY POINT
###############################################################################
# We expect the first argument to be either 'backup', 'restore', or '-h'.
SUBCOMMAND=$1
if [[ -z "$SUBCOMMAND" ]]; then
  usage
  exit 1
fi
shift  # Shift past subcommand

case "$SUBCOMMAND" in
  backup)
    do_backup "$@"
    ;;
  restore)
    do_restore "$@"
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage
    exit 1
    ;;
esac
