#!/usr/bin/env bash
# Shared entrypoint for the asterisk, freepbx and cron images.
# Renders configuration from environment variables and secrets, then execs the command.
set -euo pipefail

TEMPLATE_DIR=/usr/local/share/freepbx-docker/templates

# Read a value from VAR, or from the file named by VAR_FILE (docker/k8s secrets).
file_env() {
  local var="$1" default="${2:-}"
  local file_var="${var}_FILE"
  if [[ -n "${!var:-}" && -n "${!file_var:-}" ]]; then
    echo "error: both $var and $file_var are set" >&2
    exit 1
  fi
  local value="$default"
  if [[ -n "${!var:-}" ]]; then
    value="${!var}"
  elif [[ -n "${!file_var:-}" ]]; then
    value="$(<"${!file_var}")"
  fi
  export "$var"="$value"
}

render() {
  local template="$1" dest="$2" mode="${3:-0644}"
  local vars
  vars="$(grep -oE '\$\{[A-Z_][A-Z0-9_]*\}' "$TEMPLATE_DIR/$template" | sort -u | tr -d '\n')"
  install -m "$mode" -o asterisk -g asterisk /dev/null "$dest"
  envsubst "$vars" <"$TEMPLATE_DIR/$template" >"$dest"
}

export DB_HOST="${DB_HOST:-db}"
export DB_PORT="${DB_PORT:-3306}"
export DB_NAME="${DB_NAME:-asterisk}"
export CDR_DB_NAME="${CDR_DB_NAME:-asteriskcdrdb}"
export DB_USER="${DB_USER:-freepbxuser}"
file_env DB_PASSWORD
export ODBC_DRIVER_PATH
ODBC_DRIVER_PATH="$(dpkg -L odbc-mariadb | grep -m1 '/libmaodbc\.so$')"

render odbcinst.ini.tmpl /etc/odbcinst.ini
render odbc.ini.tmpl /etc/odbc.ini

# The FreePBX installer writes the first freepbx.conf itself and treats one without
# amportal.conf as a half-finished install, so only render it once installed.
if [[ -n "$DB_PASSWORD" && -f /etc/amportal.conf ]]; then
  # Escape for a single-quoted PHP string.
  DB_PASSWORD_PHP="${DB_PASSWORD//\\/\\\\}"
  export DB_PASSWORD_PHP="${DB_PASSWORD_PHP//\'/\\\'}"
  render freepbx.conf.tmpl /etc/freepbx.conf 0640
fi

# FreePBX CLI entry points live in the asterisk_lib volume.
for cli_name in fwconsole amportal; do
  if [[ -e "/var/lib/asterisk/bin/${cli_name}" ]]; then
    ln -sfn "/var/lib/asterisk/bin/${cli_name}" "/usr/sbin/${cli_name}"
  fi
done

if [[ -d /usr/local/lib/freepbx-docker/entrypoint.d ]]; then
  for hook in /usr/local/lib/freepbx-docker/entrypoint.d/*.sh; do
    [[ -e "$hook" ]] && source "$hook"
  done
fi

exec "$@"
