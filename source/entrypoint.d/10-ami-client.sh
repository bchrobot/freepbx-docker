# Sourced by docker-entrypoint.sh in the freepbx image.
# Credentials for /usr/local/bin/asterisk, the AMI shim that stands in for the CLI.
file_env AMI_USER freepbx-docker
file_env AMI_PASSWORD
mkdir -p /etc/freepbx-docker
install -m 0600 -o asterisk -g asterisk /dev/null /etc/freepbx-docker/ami.conf
cat >/etc/freepbx-docker/ami.conf <<CONF
host = "${AMI_HOST:-127.0.0.1}"
port = ${AMI_PORT:-5038}
user = "${AMI_USER}"
secret = "${AMI_PASSWORD}"
CONF
