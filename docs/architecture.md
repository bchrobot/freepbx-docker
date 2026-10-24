# Architecture

Each container runs one process. FreePBX and Asterisk are tightly coupled (FreePBX writes Asterisk's config files and drives it over AMI), so the PBX containers are grouped the way Kubernetes groups containers in a Pod: they share one network namespace and a set of volumes.

```
 internet ── 80/443 ──► proxy (Caddy) ──► freepbx:80 ─┐
          ── 5060/udp, RTP ──────────────────────────┐ │
                                                     ▼ ▼
   pbx-net: one network namespace (fixed IP, like a Pod)
   ├─ asterisk ── AMI 127.0.0.1:5038 ◄── freepbx, cron, freepbx-init
   │           └─ AGI 127.0.0.1:4573 ──► fastagi
   ├─ freepbx (Apache)   ├─ fastagi (node)   ├─ cron   └─ freepbx-init (once)
   │
   ├──► db:3306 (MariaDB or a hosted MySQL-compatible database)
   └──► smtp:25 (Postfix relay) ──► upstream SMTP server

   Shared volumes: /etc/asterisk, /var/lib/asterisk, /var/spool/asterisk,
   /var/log/asterisk, /var/www/html, FreePBX config, crontabs
```

| Service | Process | Notes |
|---|---|---|
| `pbx-net` | `pause` | Holds the shared network namespace, so any PBX container can restart without breaking the others. It plays the same role as a Kubernetes Pod's infra container. |
| `asterisk` | `asterisk -f` | Has `php-cli` and a read-only webroot only for the few dialplan `System()` calls into FreePBX PHP scripts (fax-to-email, on-demand recording). |
| `freepbx` | `apache2` | Web UI. Calls to `asterisk -rx` go to an [AMI shim](../source/bin/asterisk-ami), so this image has no Asterisk binary. |
| `fastagi` | `node fastagi-server.js` | FreePBX 17's own FastAGI server. pm2 runs it on a regular install. The dialplan calls `AGI(agi://127.0.0.1/...)`, so AGI scripts run here rather than in Asterisk. |
| `freepbx-init` | [`freepbx-init`](../source/bin/freepbx-init) | One-shot. It installs FreePBX on first start, does nothing (or upgrades modules) afterwards, and refuses to run when the database and the volumes disagree. |
| `cron` | `supercronic` | Runs FreePBX's own crontab from the shared crontabs volume (`fwconsole job --run`, which applies module security updates), plus logrotate. |
| `smtp` | `postfix` | Send-only relay with a persistent queue. The PBX images' `/usr/sbin/sendmail` is msmtp, pointed at this service. |
| `proxy` | `caddy` | TLS and HTTP for the web UI; `/ws` goes to Asterisk for WebRTC. It can be replaced by a cloud load balancer that has the same two routes. |
| `db` | `mariadb` | Replaceable by a hosted database: set `DB_HOST`/`DB_PORT`, and the entrypoint renders `/etc/freepbx.conf` and `/etc/odbc.ini` from them. |

## Configuration rendered at startup

[`docker-entrypoint.sh`](../source/docker-entrypoint.sh) renders the following from environment variables and `*_FILE` secrets:
- ODBC configuration.
- `/etc/freepbx.conf`, once FreePBX is installed.
- The AMI credentials for the shim.
- The `msmtp` settings that point `sendmail` at the `smtp` relay.

`/etc/freepbx.conf` and `/etc/amportal.conf` are symlinks into the `freepbx_conf` volume, so every container sees the copies the installer wrote.

## Mapping to Kubernetes

`pbx-net` becomes the Pod itself. `asterisk`, `freepbx`, `fastagi` and `cron` become containers in one Pod, and `freepbx-init` becomes an init container that waits for an Asterisk sidecar. The volumes become a ReadWriteOnce disk shared by the Pod's containers.
