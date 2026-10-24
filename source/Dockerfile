# Targets:
#   asterisk  - Asterisk
#   freepbx   - FreePBX web UI on Apache + mod_php; also runs freepbx-init and fastagi
#   cron      - FreePBX's scheduled jobs and logrotate (supercronic)
#   smtp      - send-only Postfix relay
#
# Base images are written out literally (not via ARG) so Dependabot can update them.

# ---------------------------------------------------------------------------
FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8 AS asterisk-build

ENV DEBIAN_FRONTEND=noninteractive

# Pinned, checksummed upstream sources. Bumped by .github/workflows/upstream-bump.yml
ARG ASTERISK_VERSION=22.11.0
ARG ASTERISK_SHA256=3bd5ee040509a3d3cd9b1ba9520c18e6ec0a7e7981ca68c457dcd36ba3c54d94
# Revision of svn.digium.com/svn/thirdparty/mp3/trunk, plus a hash of the exported tree
ARG ASTERISK_MP3_REV=204
ARG ASTERISK_MP3_TREE_SHA256=6a1952c9bf04e4ae3058ae50f193965dd59b69e52d5af86135c7c1a8e4d19fcb

WORKDIR /usr/src

RUN apt-get update \
  && apt-get -y install --no-install-recommends \
    build-essential pkg-config ca-certificates curl subversion \
    bison flex libnewt-dev libssl-dev libncurses-dev libsqlite3-dev \
    libxml2-dev uuid-dev default-libmysqlclient-dev unixodbc-dev \
    libasound2-dev libogg-dev libvorbis-dev libicu-dev libcurl4-openssl-dev \
    libical-dev libneon27-dev libsrtp2-dev libspandsp-dev \
    automake autoconf libtool-bin

RUN set -eux \
  && curl -fsSL "https://github.com/asterisk/asterisk/releases/download/${ASTERISK_VERSION}/asterisk-${ASTERISK_VERSION}.tar.gz" -o asterisk.tar.gz \
  && echo "${ASTERISK_SHA256}  asterisk.tar.gz" | sha256sum -c - \
  && tar -xzf asterisk.tar.gz \
  && cd "asterisk-${ASTERISK_VERSION}" \
  && contrib/scripts/get_mp3_source.sh -r "${ASTERISK_MP3_REV}" \
  && mp3_tree_sha256="$(cd addons/mp3 && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum | cut -d' ' -f1)" \
  && echo "mp3 tree sha256: ${mp3_tree_sha256}" \
  && test "${mp3_tree_sha256}" = "${ASTERISK_MP3_TREE_SHA256}" \
  && contrib/scripts/install_prereq install \
  && ./configure --with-pjproject-bundled --with-jansson-bundled \
  && make menuselect.makeopts \
  && menuselect/menuselect --disable BUILD_NATIVE --enable format_mp3 menuselect.makeopts \
  && make -j"$(nproc)" \
  && make install DESTDIR=/out \
  && make samples DESTDIR=/out \
  # /var/run is a symlink to /run in the runtime image
  && mkdir -p /out/run && cp -a /out/var/run/. /out/run/ && rm -rf /out/var/run

# Record which Debian packages provide the shared libraries Asterisk links against,
# so runtime stages install exactly those (and Trivy can see them).
RUN set -eux \
  && find /out -type f \( -name '*.so*' -o -perm -u+x \) -print0 \
    | xargs -0 ldd 2>/dev/null \
    | awk '$2 == "=>" && $3 ~ /^\// {print $3}' | sort -u \
    | while read -r lib; do \
        dpkg -S "$lib" 2>/dev/null || dpkg -S "$(realpath "$lib")" 2>/dev/null || dpkg -S "${lib#/usr}" 2>/dev/null || true; \
      done \
    | cut -d: -f1 | sort -u > /out/asterisk-runtime-packages \
  && cat /out/asterisk-runtime-packages

# ---------------------------------------------------------------------------
FROM node:22.23.4-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS node

# ---------------------------------------------------------------------------
FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8 AS base

ENV DEBIAN_FRONTEND=noninteractive

# Fixed IDs: asterisk, freepbx and cron containers share volumes owned by this user.
ARG ASTERISK_UID=1000
ARG ASTERISK_GID=1000

RUN apt-get update \
  && apt-get -y install --no-install-recommends \
    ca-certificates curl tzdata gettext-base procps \
    php8.2-cli php8.2-common php8.2-curl php8.2-mysql php8.2-gd php8.2-mbstring \
    php8.2-intl php8.2-xml php8.2-soap php-pear \
    unixodbc odbc-mariadb sox mpg123 msmtp-mta \
  && groupadd --gid "${ASTERISK_GID}" asterisk \
  && useradd --system --uid "${ASTERISK_UID}" --gid asterisk --home-dir /var/lib/asterisk --no-create-home asterisk \
  && usermod -aG audio,dialout asterisk \
  && rm -rf /var/lib/apt/lists/* \
  # FreePBX's config files live in a volume shared by all containers
  && install -d -o asterisk -g asterisk /var/lib/freepbx \
  && ln -s /var/lib/freepbx/freepbx.conf /etc/freepbx.conf \
  && ln -s /var/lib/freepbx/amportal.conf /etc/amportal.conf \
  && mkdir -p /usr/local/lib/freepbx-docker/entrypoint.d

COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY templates/ /usr/local/share/freepbx-docker/templates/

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# ---------------------------------------------------------------------------
FROM base AS asterisk

COPY --from=asterisk-build /out/ /
COPY entrypoint.d/10-ami-server.sh /usr/local/lib/freepbx-docker/entrypoint.d/

RUN set -eux \
  && apt-get update \
  && xargs -a /asterisk-runtime-packages apt-get -y install --no-install-recommends \
  && rm -rf /var/lib/apt/lists/* \
  && ldconfig \
  && sed -i 's|^;runuser|runuser|; s|^;rungroup|rungroup|' /etc/asterisk/asterisk.conf \
  && mkdir -p /var/run/asterisk \
  && chown -R asterisk:asterisk /etc/asterisk /var/lib/asterisk /var/log/asterisk \
    /var/spool/asterisk /var/run/asterisk /usr/lib/asterisk \
  && asterisk -V

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD asterisk -rx 'core show uptime' >/dev/null || exit 1

CMD ["asterisk", "-f", "-n", "-U", "asterisk", "-G", "asterisk", "-vvv"]

# ---------------------------------------------------------------------------
FROM base AS freepbx

# Sangoma only publishes a mutable "latest" tarball, so the exact file is also mirrored
# as a release asset of this repo; whichever source answers must match the checksum.
ARG FREEPBX_VERSION=17.0.33
ARG FREEPBX_SHA256=57bfe353de693cd9f0f03b4e6cda68da69fd39c4beb9506fc06c8814ec40e538
ARG FREEPBX_MIRROR_REPO=bchrobot/freepbx-docker

COPY apache/remoteip.conf /etc/apache2/conf-available/freepbx-remoteip.conf

RUN apt-get update \
  && apt-get -y install --no-install-recommends \
    apache2 libapache2-mod-php8.2 mariadb-client lame ffmpeg sqlite3 \
    # FreePBX verifies module signatures with gpg
    gnupg \
    # only for the crontab command; the cron container runs the schedule
    cron \
  && rm -rf /var/lib/apt/lists/* \
  && sed -i 's/\(^upload_max_filesize = \).*/\120M/' /etc/php/8.2/apache2/php.ini \
  && sed -i 's/\(^memory_limit = \).*/\1256M/' /etc/php/8.2/apache2/php.ini \
  && sed -i 's/^\(User\|Group\).*/\1 asterisk/' /etc/apache2/apache2.conf \
  && sed -i 's/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf \
  && echo "ServerName localhost" >> /etc/apache2/apache2.conf \
  && a2enmod rewrite remoteip \
  && a2enconf freepbx-remoteip \
  && apache2ctl -t \
  && rm -f /var/www/html/index.html \
  && ln -sf /dev/stdout /var/log/apache2/access.log \
  && ln -sf /dev/stderr /var/log/apache2/error.log \
  && ln -sf /dev/stdout /var/log/apache2/other_vhosts_access.log \
  # fwconsole's reload lock; shared by the FreePBX containers, not by Asterisk
  && install -d -o asterisk -g asterisk /run/asterisk

# The FreePBX installer requires node, and its pm2/ucp modules use npm. Copied from
# the official image so Dependabot tracks it (Debian's Node 18 is upstream-EOL).
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
  && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
  && node --version && npm --version

# No Asterisk binary here: `asterisk -rx` and `asterisk -V` go over AMI instead.
COPY --chmod=0755 bin/asterisk-ami /usr/local/bin/asterisk
COPY --chmod=0755 bin/freepbx-init bin/fastagi bin/apache2-foreground /usr/local/bin/
COPY entrypoint.d/10-ami-client.sh /usr/local/lib/freepbx-docker/entrypoint.d/

WORKDIR /usr/local/src

RUN set -eux \
  && for url in \
       "https://github.com/${FREEPBX_MIRROR_REPO}/releases/download/freepbx-${FREEPBX_VERSION}/freepbx-${FREEPBX_VERSION}.tgz" \
       "https://mirror.freepbx.org/modules/packages/freepbx/freepbx-17.0-latest.tgz"; do \
       curl -fsSL --http1.1 "$url" -o freepbx.tgz \
         && echo "${FREEPBX_SHA256}  freepbx.tgz" | sha256sum -c - \
         && break; \
       rm -f freepbx.tgz; \
     done \
  && test -f freepbx.tgz \
  && tar -xzf freepbx.tgz \
  && rm freepbx.tgz

CMD ["apache2-foreground"]

# ---------------------------------------------------------------------------
FROM freepbx AS cron

# Pinned, checksummed upstream binary. Bumped by .github/workflows/upstream-bump.yml
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256_AMD64=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ARG SUPERCRONIC_SHA256_ARM64=4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94

RUN set -eux \
  && arch="$(dpkg --print-architecture)" \
  && case "$arch" in \
       amd64) sha256="${SUPERCRONIC_SHA256_AMD64}" ;; \
       arm64) sha256="${SUPERCRONIC_SHA256_ARM64}" ;; \
       *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
     esac \
  && curl -fsSL "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${arch}" -o /usr/local/bin/supercronic \
  && echo "${sha256}  /usr/local/bin/supercronic" | sha256sum -c - \
  && chmod 0755 /usr/local/bin/supercronic \
  && apt-get update \
  && apt-get -y install --no-install-recommends logrotate \
  && rm -rf /var/lib/apt/lists/* \
  # lets the asterisk user open its own crontab in /var/spool/cron/crontabs
  && usermod -aG crontab asterisk

COPY cron/logrotate.conf /etc/freepbx-docker/logrotate.conf
COPY --chmod=0755 cron/cron-scheduler /usr/local/bin/cron-scheduler

CMD ["cron-scheduler"]

# ---------------------------------------------------------------------------
FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8 AS smtp

ENV DEBIAN_FRONTEND=noninteractive

RUN echo "postfix postfix/main_mailer_type select No configuration" | debconf-set-selections \
  && apt-get update \
  && apt-get -y install --no-install-recommends postfix libsasl2-modules ca-certificates \
  && touch /etc/postfix/main.cf \
  && rm -rf /var/lib/apt/lists/*

COPY --chmod=0755 smtp/smtp-entrypoint /usr/local/bin/smtp-entrypoint

EXPOSE 25
VOLUME /var/spool/postfix
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD bash -c 'exec 3<>/dev/tcp/127.0.0.1/25 && head -1 <&3 | grep -q "^220"' || exit 1
ENTRYPOINT ["/usr/local/bin/smtp-entrypoint"]
CMD ["postfix", "start-fg"]
