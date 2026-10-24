# Architecture

Each container runs one process. FreePBX and Asterisk are tightly coupled (FreePBX writes Asterisk's config files and drives it over AMI), so the PBX containers are grouped the way Kubernetes groups containers in a Pod: they share one network namespace and a set of volumes.

```
                 ┌──────────────── pbx-net (pause: owns IP, ports 80, 5060/udp) ───────────────┐
                 │  asterisk        freepbx (Apache)    fastagi (node)     freepbx-init (once) │
                 │     │  ▲ AMI 127.0.0.1:5038 ─┘           ▲                                  │
                 │     └──── AGI 127.0.0.1:4573 ────────────┘                                  │
                 └─────────────────────────────────────────────────────────────────────────────┘
                        │ ODBC/CDR, PDO                 shared volumes: /etc/asterisk, /var/lib/asterisk,
                        ▼                               /var/spool/asterisk, /var/log/asterisk, /var/www/html, ...
                       db (MariaDB, or any MySQL-compatible host via DB_HOST)
```

| Service | Process | Notes |
|---|---|---|
| `pbx-net` | `pause` | Holds the shared network namespace, so any PBX container can restart without breaking the others. It plays the same role as a Kubernetes Pod's infra container. |
| `asterisk` | `asterisk -f` | Has `php-cli` and a read-only webroot only for the few dialplan `System()` calls into FreePBX PHP scripts (fax-to-email, on-demand recording). |
| `freepbx` | `apache2` | Web UI. Calls to `asterisk -rx` go to an [AMI shim](../source/bin/asterisk-ami), so this image has no Asterisk binary. |
| `fastagi` | `node fastagi-server.js` | FreePBX 17's own FastAGI server. pm2 runs it on a regular install. The dialplan calls `AGI(agi://127.0.0.1/...)`, so AGI scripts run here rather than in Asterisk. |
| `freepbx-init` | [`freepbx-init`](../source/bin/freepbx-init) | One-shot. It installs FreePBX on first start, does nothing (or upgrades modules) afterwards, and refuses to run when the database and the volumes disagree. |
| `db` | `mariadb` | Replaceable by a hosted database: set `DB_HOST`/`DB_PORT`, and the entrypoint renders `/etc/freepbx.conf` and `/etc/odbc.ini` from them. |

## Configuration rendered at startup

[`docker-entrypoint.sh`](../source/docker-entrypoint.sh) renders the following from environment variables and `*_FILE` secrets:
- ODBC configuration.
- `/etc/freepbx.conf`, once FreePBX is installed.
- The AMI credentials for the shim.

`/etc/freepbx.conf` and `/etc/amportal.conf` are symlinks into the `freepbx_conf` volume, so every container sees the copies the installer wrote.

## Mapping to Kubernetes

`pbx-net` becomes the Pod itself. `asterisk`, `freepbx` and `fastagi` become containers in one Pod, and `freepbx-init` becomes an init container that waits for an Asterisk sidecar. The volumes become a ReadWriteOnce disk shared by the Pod's containers.
