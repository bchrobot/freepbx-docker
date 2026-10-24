# Production notes (future work)

These are design notes for moving from local Docker Compose to a managed platform, using GKE and a Twilio Elastic SIP Trunk as the example. None of this is implemented yet.

## SIP and RTP

Each call carries media on its own UDP port pair, taken from Asterisk's RTP range and advertised in SDP. The far end sends packets straight to `<public IP>:<port>`. That needs a stable public IP that Asterisk knows (`external_media_address`), every port in the range reachable, and no source-port rewriting.

Kubernetes Services can't express port ranges, and kube-proxy NAT breaks symmetric RTP. For a residential landline:

- **Dedicated node:** run the PBX Pod on a one-node pool (taint/toleration) with `hostNetwork: true` and a reserved static external IP. If needed, front that node with a Terraform-managed external passthrough NLB using a UDP all-ports forwarding rule.
- **PJSIP:** set `external_media_address`/`external_signaling_address` to the static IP, `local_net` to the VPC and Pod ranges, `direct_media=no` and `rtp_symmetric=yes`.
- **Narrow RTP range:** a household needs a handful of concurrent calls at about 2 ports each, so `RTP_START=10000`/`RTP_END=10099` is ample.
- **VPC firewall:** allow 5060 and the RTP range only from Twilio's published signaling and media ranges, plus the home's phone/ATA path. Prefer a WireGuard/Tailscale tunnel, since residential IPs change.
- **Accepted trade-off:** there is no HA, so node maintenance drops active calls. Schedule maintenance windows for quiet hours. An SBC/media relay (Kamailio + rtpengine) is only worth revisiting if multi-replica HA becomes a requirement.

## Replacing fail2ban

The only jail, `[asterisk]`, bans SIP authentication failures and extension scanning. It bans on every port (including 80/443) through `DOCKER-USER`. It doesn't cover web logins.

- **Twilio trunk:** a VPC firewall allow-list plus the PJSIP trunk `identify`/ACL keeps strangers off SIP entirely.
- **Phones registering over the internet:** move them onto a VPN, or run fail2ban with `hostNetwork` on the PBX node.
- **Web UI:** add Cloud Armor rate limiting and/or IAP in front of `/admin`.

## Service mapping

| Compose | GKE |
|---|---|
| `pbx-net` + `asterisk`, `freepbx`, `fastagi`, `cron` | One Pod. The containers share localhost exactly as they do here. Use a ReadWriteOnce Persistent Disk for the shared volumes, and an `emptyDir` for `/var/run/asterisk`. |
| `freepbx-init` | An init container. Run Asterisk as a native sidecar (`restartPolicy: Always`, k8s ≥ 1.29) so init can reach AMI. |
| `db` | Cloud SQL for MySQL 8.0 (validate FreePBX 17 support and `sql_mode`), through the Cloud SQL Auth Proxy or private IP. Only `DB_HOST` changes. |
| `proxy` | GKE Gateway / Google Cloud HTTPS load balancer with managed certificates, routing `/ws` to Asterisk and everything else to FreePBX. |
| `smtp` | Keep it as a Deployment, or point `SMTP_HOST` at SendGrid/SES/Google Workspace relay. |
| Compose secrets | Secret Manager through the Secrets Store CSI driver, mounted at the same `/run/secrets/*` paths. |
