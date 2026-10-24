# Supply chain and security patching

Every dependency has to be auditable, and its fixes have to arrive without someone remembering to check. Dependabot handles what it can see. The workflows below cover everything else.

| Dependency | How it gets in | Version updates | Vulnerability signal |
|---|---|---|---|
| Base and compose images (`debian`, `mariadb`, `fail2ban`, ...) | `FROM` / `image:`, pinned by tag and digest | Dependabot (`docker`, `docker-compose`) | Trivy image scan |
| Node.js + npm (required by the FreePBX installer and the pm2/UCP modules) | Copied from `node:22-bookworm-slim`, pinned by digest | Dependabot (`docker`) | Trivy image scan |
| GitHub Actions | `uses:` pinned by commit SHA | Dependabot (`github-actions`) | Dependabot alerts |
| Debian packages (PHP 8.2, Apache, unixODBC, ffmpeg, Asterisk's shared libraries, ...) | `apt-get install` | Weekly no-cache rebuild (`rebuild.yml`) | Trivy image scan |
| Asterisk | Source tarball from `github.com/asterisk/asterisk` releases, sha256-pinned | `upstream-bump.yml` (follows the 22 LTS line) | `advisory-watch.yml` (Asterisk GHSAs) |
| Asterisk mp3 addon | `svn export -r <rev>` from svn.digium.com, tree-hash pinned | Manual. The code has been static for years. | None. It is a third-party decoder with no advisory feed. |
| FreePBX core tarball | Sangoma's `freepbx-17.0-latest.tgz`, mirrored as a release asset here, sha256-pinned | `upstream-bump.yml` (detects a new tarball by checksum) | Trivy (vendored composer/npm lockfiles) and `advisory-watch.yml` (FreePBX GHSAs) |
| supercronic (cron container) | Release binary, sha256-pinned per architecture | `upstream-bump.yml` | Trivy (Go binary metadata) |
| Postfix relay (smtp container) | Debian `postfix` on the pinned Debian base | Dependabot (base image), weekly rebuild | Trivy image scan |
| npm packages that UCP/pm2 install at FreePBX install time | `npm install` into the webroot volume | FreePBX module updates | None. They live in a volume outside the image. |
| FreePBX modules installed or upgraded at runtime | `fwconsole ma`, stored in a volume | FreePBX module updates | `advisory-watch.yml`. No image scanner can see this code. |

## Known gaps

- **PHP 8.2:** upstream security support ends 2026-12-31. After that, fixes come only from Debian 12 LTS backports (until about June 2028). FreePBX 17 is tied to Debian 12. Moving to Debian 13 / PHP 8.4 means moving to FreePBX 18.
- **Node.js:** the FreePBX installer refuses to run without `node`, so Node can't be dropped. It comes from the official `node:22` image (LTS until April 2027) instead of Debian's Node 18, which is upstream end of life.
- **Asterisk sounds:** `make install` downloads the core and MOH sound archives from downloads.asterisk.org without a pinned checksum. They are audio files, not code.
- **Runtime FreePBX modules:** these are the largest gap. Recent critical FreePBX CVEs were in modules, which live in a volume outside the image. Keep module security updates enabled, and act on `upstream-advisory` issues.
- **Bump PRs and CI:** PRs opened with `GITHUB_TOKEN` don't trigger CI. Set a `BUMP_TOKEN` secret so the build check runs on bump PRs.

## Decision: our own smtp image instead of `boky/postfix`

`boky/postfix` is actively developed, but its tagged release images are not rebuilt between releases. Scanned in October 2026, `boky/postfix:5.1.0` (January 2026) had 207 fixable HIGH/CRITICAL findings, and the rolling `edge` tag had 16. A plain Debian `postfix` on our pinned base image gets Dependabot base bumps and the weekly rebuild like every other image here, for about 40 lines of entrypoint.

## Decision: build Asterisk from source instead of Sangoma's `.deb` packages

Sangoma's FreePBX 17 apt repo (`deb.freepbx.org/freepbx17-prod`) ships `asterisk22` packages, currently 22.11.0. We don't use them:

- **amd64 only:** the repo publishes no arm64 packages, which rules out native builds on Apple Silicon and on arm64 cloud nodes.
- **No scanner visibility:** Trivy matches dpkg packages against Debian's security tracker, and `asterisk22` isn't a Debian package. So installing the `.deb` wouldn't make Asterisk CVEs visible; the advisory watch is still the signal either way.
- **Reviewability:** a pinned, checksummed source tarball changes only through a reviewed bump PR. An apt repo would change Asterisk silently on every rebuild.

Revisit this if Sangoma publishes arm64 packages, or if building from source becomes a maintenance burden.
