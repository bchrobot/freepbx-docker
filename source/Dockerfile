FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /usr/src

# Pinned, checksummed upstream sources. Bumped by .github/workflows/upstream-bump.yml
ARG ASTERISK_VERSION=22.11.0
ARG ASTERISK_SHA256=3bd5ee040509a3d3cd9b1ba9520c18e6ec0a7e7981ca68c457dcd36ba3c54d94
# Revision of svn.digium.com/svn/thirdparty/mp3/trunk, plus a hash of the exported tree
ARG ASTERISK_MP3_REV=204
ARG ASTERISK_MP3_TREE_SHA256=6a1952c9bf04e4ae3058ae50f193965dd59b69e52d5af86135c7c1a8e4d19fcb

# Sangoma only publishes a mutable "latest" tarball, so the exact file is also mirrored
# as a release asset of this repo; whichever source answers must match the checksum.
ARG FREEPBX_VERSION=17.0.33
ARG FREEPBX_SHA256=57bfe353de693cd9f0f03b4e6cda68da69fd39c4beb9506fc06c8814ec40e538
ARG FREEPBX_MIRROR_REPO=bchrobot/freepbx-docker

# Install requirements
RUN apt-get update && apt-get -y install \
  build-essential pkg-config cron curl wget \
  bison flex libnewt-dev libssl-dev libncurses5-dev \
  subversion libsqlite3-dev libjansson-dev \
  libxml2-dev uuid uuid-dev default-libmysqlclient-dev \
  lame ffmpeg mpg123 expect \
  # PHP 8.2 Installation
  && echo "postfix postfix/mailname string freepbx.localdomain" | debconf-set-selections \
  && echo "postfix postfix/main_mailer_type string 'Internet Site'" | debconf-set-selections \
  && apt-get install -y apache2 mariadb-client \
  php8.2 php8.2-curl php8.2-cli \
  php8.2-common php8.2-mysql php8.2-gd php8.2-mbstring php8.2-intl \
  php8.2-xml php-pear \
  sox sqlite3 automake libtool autoconf unixodbc-dev \
  libasound2-dev libogg-dev libvorbis-dev libicu-dev libcurl4-openssl-dev \
  odbc-mariadb unixodbc \
  libical-dev libneon27-dev libsrtp2-dev libspandsp-dev libtool-bin \
  nodejs npm ipset iptables php-soap \
  postfix libsasl2-modules mailutils \
  certbot python3-certbot-apache logrotate

# Download and build Asterisk directly in this stage
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
  && ./configure --libdir=/usr/lib64 --with-pjproject-bundled --with-jansson-bundled \
  && make menuselect.makeopts \
  && menuselect/menuselect --disable BUILD_NATIVE --enable format_mp3 menuselect.makeopts \
  && make -j"$(nproc)" \
  && make install \
  && make samples \
  && ldconfig \
  # Create asterisk user and give permissions
  && groupadd asterisk \
  && useradd -r -d /var/lib/asterisk -g asterisk asterisk \
  && usermod -aG audio,dialout asterisk \
  && chown -R asterisk:asterisk /etc/asterisk \
  && chown -R asterisk:asterisk /var/lib/asterisk /var/log/asterisk /var/spool/asterisk \
  && chown -R asterisk:asterisk /usr/lib64/asterisk \
  && sed -i 's|;runuser|runuser|' /etc/asterisk/asterisk.conf \
  && sed -i 's|;rungroup|rungroup|' /etc/asterisk/asterisk.conf \
  && echo "/usr/lib64" >> /etc/ld.so.conf.d/x86_64-linux-gnu.conf \
  && ldconfig \
  # Configure Apache web server
  && sed -i 's/\(^upload_max_filesize = \).*/\120M/' /etc/php/8.2/apache2/php.ini \
  && sed -i 's/\(^memory_limit = \).*/\1256M/' /etc/php/8.2/apache2/php.ini \
  && sed -i 's/^\(User\|Group\).*/\1 asterisk/' /etc/apache2/apache2.conf \
  && sed -i 's/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf \
  && a2enmod rewrite \
  && apache2ctl -t \
  && echo "ServerName localhost" >> /etc/apache2/apache2.conf \
  && rm -rf /usr/src/asterisk-${ASTERISK_VERSION} asterisk.tar.gz /var/www/html/index.html \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /usr/local/src

# FreePBX source
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

COPY odbc/odbcinst.ini /etc/odbcinst.ini
COPY odbc/odbc.ini /etc/odbc.ini
COPY postfix/main.cf /etc/postfix/main.cf
COPY logrotate/asterisk /etc/logrotate.d/asterisk
COPY entrypoint.sh entrypoint.sh

RUN sed -i "s|^smtp_sasl_password_maps.*|smtp_sasl_password_maps = texthash:/run/secrets/postfix_sasl_passwd|" /etc/postfix/main.cf \
  && mkdir -p /var/log/asterisk \
  && touch /var/log/asterisk/full \
  && chown -R asterisk:asterisk /var/log/asterisk

CMD ["/usr/bin/env", "bash", "/usr/local/src/entrypoint.sh"]
