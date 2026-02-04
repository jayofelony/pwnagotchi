#!/bin/bash

# Exit immediately on error (-e) or use of unset variables (-u)
set -eu

# Required external tools for gettext-based localization
DEPENDENCIES=( 'xgettext' 'msgfmt' 'msgmerge' )

# Allowed commands for this script
COMMANDS=( 'add' 'update' 'delete' 'compile' )

# Resolve repository root directory (two levels above this script)
REPO_DIR="$(dirname "$(dirname "$(realpath "$0")")")"

# Path to locale files
LOCALE_DIR="${REPO_DIR}/pwnagotchi/locale"

# Python source file containing translatable strings
VOICE_FILE="${REPO_DIR}/pwnagotchi/voice.py"

# Print usage instructions
function usage() {
cat <<EOF

usage: $0 <command> [options]

  Commands:
    add <language>
    delete <language>
    compile <language>
    update <language>

EOF
}

# Check that all required dependencies are installed
for REQ in "${DEPENDENCIES[@]}"; do
  if ! type "$REQ" >/dev/null 2>&1; then
    echo "Dependency check failed for ${REQ}"
    exit 1
  fi
done

# Validate the command argument
if [[ ! "${COMMANDS[*]}" =~ $1 ]]; then
  usage
fi

# Create a new language directory and initialize voice.po
function add_lang() {
  mkdir -p "$LOCALE_DIR/$1/LC_MESSAGES"
  cp -n "$LOCALE_DIR/voice.pot" "$LOCALE_DIR/$1/LC_MESSAGES/voice.po"
}

# Delete an existing language directory
function del_lang() {
  # set -eu is present; so not dangerous
  # shellcheck disable=SC2115
  rm -rf "$LOCALE_DIR/$1"
}

# Compile .po file into a binary .mo file
function comp_lang() {
  msgfmt -o "$LOCALE_DIR/$1/LC_MESSAGES/voice.mo" \
         "$LOCALE_DIR/$1/LC_MESSAGES/voice.po"
}

# Update translations by regenerating the template and merging changes
function update_lang() {
  # Extract translatable strings from voice.py
  xgettext --no-location -d voice -o "$LOCALE_DIR/voice.pot" "$VOICE_FILE"

  # Merge updated template into existing language file
  msgmerge --update "$LOCALE_DIR/$1/LC_MESSAGES/voice.po" \
           "$LOCALE_DIR/voice.pot"
}

# Dispatch command
case "$1" in
  add)
    add_lang "$2"
    ;;
  delete)
    del_lang "$2"
    ;;
  compile)
    comp_lang "$2"
    ;;
  update)
    update_lang "$2"
    ;;
esac
