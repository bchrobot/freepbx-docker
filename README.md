## Introduction

This is a [Docker Compose](https://docs.docker.com/compose/) application for running [FreePBX](https://www.freepbx.org), a Voice over IP manager for [Asterisk](https://www.asterisk.org), in containers.

Upon starting this multi-container application, it will give you a turnkey PBX system for SIP calling. Each container runs a single process. See [docs/architecture.md](docs/architecture.md) for how the pieces fit together, and [docs/production-notes.md](docs/production-notes.md) for moving to a managed platform.

| Service | Role |
| --- | --- |
| `proxy` | Caddy: HTTPS for the web UI, automatic Let's Encrypt certificates |
| `freepbx` | FreePBX web UI (Apache + PHP) |
| `asterisk` | Asterisk PBX |
| `fastagi` | FreePBX's FastAGI server (runs dialplan AGI scripts) |
| `cron` | FreePBX scheduled jobs (module security updates, ...) and logrotate |
| `smtp` | Outbound mail relay (voicemail-to-email, notifications) |
| `db` | MariaDB (replaceable by a hosted MySQL-compatible database) |
| `freepbx-init` | One-shot: installs FreePBX on first start, then exits |
| `pbx-net` | Holds the network namespace shared by the PBX containers |
| `fail2ban` | Bans hosts after failed SIP authentication |

* FreePBX 17.0.33
* PHP 8.2.29
* Asterisk 22.11.0 (LTS)
* MariaDB 10.11.19
* Fail2ban pre-configured with restrictive enforcement rules
* Email notifications
* Logrotate configured also for Asterisk and Freepbx
* Supports data persistence
* Base image Debian [debian:bookworm-slim](https://hub.docker.com/_/debian/), amd64 and arm64
* Apache 2.4.65
* Node.js 22 LTS
* DAHDI channel not supported

### Ports
The following ports are exposed via Docker.

| Port              | Description |
| ----------------- | ----------- |
| `80/tcp`          | HTTP (redirects to HTTPS) |
| `443/tcp`         | HTTPS       |
| `5060/udp`        | PJSIP       |

RTP ports e.g. `16384-32767/udp` require a particular configuration in order to be
properly exposed.\
There's a [known issue](https://github.com/moby/moby/issues/11185) about Docker and its way to expose a large range of ports, since each port exposed loads another process into memory and you may be experiencing a low memory condition.\
As a trade-off, those ports are going to be exposed via Docker host `iptables` manually.\
So [run.sh](run.sh) will take care of iptables configuration, besides building and running the image.

### Host requirements
- `ip`, `iptables` and `awk` commands
- iptables rules inside the Docker chains will bypass any firewall rule on the system
- Iptables rules are temporary, unless you make them persistent in this way (Debian-like):
```bash
sudo apt-get update
sudo apt-get install -y iptables-persistent
sudo systemctl enable netfilter-persistent
sudo systemctl restart netfilter-persistent
sudo systemctl status netfilter-persistent

# Everytime you make a change to iptables, remember to save to disk
sudo sh -c 'iptables-save > /etc/iptables/rules.v4'
```
- Customize Fail2ban preferences by editing the file `source/fail2ban/jail.local`. Currently it bans 2 consecutive failed SIP registration attempts within 30 seconds for 1 week.

- Make sure you have a valid DNS server for Docker containers by adding the following to `/etc/docker/daemon.json` (restart Docker after saving the file):
  ```json
  {
    "dns": ["1.1.1.1"]
  }
  ```

## Usage
1. Create required passwords:
```bash
# for MySQL root user
printf "your-mysql-root-password" > mysql_root_password.txt
printf "yourstrongmysqlfreepbxuserpassword" > freepbxuser_password.txt

# for the Asterisk Manager Interface login used inside the stack
openssl rand -hex 24 > ami_password.txt

# for your upstream SMTP server (e.g. a Gmail app password); create it even if unused
printf "your-smtp-password" > smtp_password.txt

# Set proper file permissions
chmod 600 mysql_root_password.txt freepbxuser_password.txt ami_password.txt smtp_password.txt
```
Passwords must not contain quote characters.

Then copy `.env.example` to `.env` and adjust it:
- `DOMAIN`: the public name of the web UI. Caddy obtains a Let's Encrypt certificate for it, which needs ports 80/443 reachable and a DNS A record. Leave it as `localhost` to use Caddy's local CA.
- `SMTP_RELAYHOST`, `SMTP_RELAY_USER`, `SMTP_FROM`: your upstream SMTP server.
- `PBX_SUBNET`, `PBX_GATEWAY`, `PBX_IP`: only if `172.18.0.0/16` collides with another network on the host.

2. OPTION A: build the images locally:
```bash
sudo docker compose build
```
`source/Dockerfile` has one target per service (`asterisk`, `freepbx`, `cron`, `smtp`). Builds work natively on both amd64 and arm64.

2. OPTION B: use the images published by CI to `ghcr.io/bchrobot/freepbx-docker/{asterisk,freepbx,cron,smtp}:latest` (rebuilt weekly with the latest Debian security fixes). Set `ASTERISK_IMAGE` / `FREEPBX_IMAGE` / `CRON_IMAGE` / `SMTP_IMAGE` to use different images, then jump to the next step

3. Configure RTP ports on the host and build + run the Compose project. FreePBX is installed automatically on the first start (`freepbx-init`):
```bash
sudo bash run.sh
# If you want to override the default RTP port range (16384-32767); it is saved to .env
# and freepbx-init applies the same range to Asterisk:
sudo bash run.sh --rtp 10000-20000
# NOTE
# If you run the script with the default RTP range 16384-32767 and later rerun it with a different range, the iptables rules from the previous range remain in place and you have to delete those rules manually before or after applying the new range.

# Re-run the install/upgrade step manually
sudo bash run.sh --install-freepbx

# Optional, clean up containers, network and volumes
sudo bash run.sh --clean-all
```

Open `https://<DOMAIN>/admin`, create the admin user, and start configuring the system!

### WebRTC
The proxy forwards `/ws` to Asterisk's HTTP server, which FreePBX leaves disabled. To use WebRTC phones, open Settings → Advanced Settings and set "Enable the mini-HTTP Server" to Yes and "HTTP Bind Address" to `0.0.0.0`. The port stays internal to the compose network.

### Using a hosted database
Set `DB_HOST`/`DB_PORT` in `.env`, put the `freepbxuser` password in `freepbxuser_password.txt`, and create the `asterisk` and `asteriskcdrdb` databases and the `freepbxuser` grants yourself (see [init.sql](init.sql)). Then remove the `db` service and the `depends_on: db` entries from `docker-compose.yaml`. FreePBX's configuration files are rendered from these settings on every start.

### Upgrading from the single-container layout
The old `var_data`/`etc_data` volumes are not migrated automatically:
1. Take a full backup with FreePBX's Backup & Restore module on the old stack, and download it.
2. Remove the old stack with `sudo docker compose down`. Keep the old volumes until the new stack is verified.
3. Start the new stack. It installs a fresh FreePBX.
4. Restore the backup through Backup & Restore.

## Security updates
- **Dependabot** opens PRs for base images, compose images and GitHub Actions. All are pinned by tag and digest.
- **CI** (`.github/workflows/build.yml`) scans every image with Trivy, uploads the results to the repository's Security tab, and attaches an SBOM.
- **Weekly rebuild** (`.github/workflows/rebuild.yml`) rebuilds from scratch so Debian package fixes (PHP, Apache, ...) land. It republishes the image and opens a `security` issue if fixable HIGH/CRITICAL findings remain.
- **Upstream bumps** (`.github/workflows/upstream-bump.yml`) open PRs for new Asterisk 22 LTS and FreePBX 17 releases, with verified checksums.
- **Advisory watch** (`.github/workflows/advisory-watch.yml`) opens an issue for each new Asterisk or FreePBX security advisory.

See [docs/supply-chain.md](docs/supply-chain.md) for what each mechanism covers and the known gaps.


**If you find this project useful or inspiring**

<a href="https://www.buymeacoffee.com/emilianospada">
  <img src="https://i.postimg.cc/W1qS7R25/bmc-button-counter.jpg" alt="Buy me a coffee" width="320">
</a>

