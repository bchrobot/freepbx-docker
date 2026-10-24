#!/usr/bin/env python3
"""Bump pinned upstream sources in source/Dockerfile.

Dependabot cannot track Dockerfile ARG versions, so this script does it for the
sources the image downloads directly. It rewrites the ARG lines in place and
prints a summary line for the pull request title; opening the PR is left to the
workflow.

Usage: upstream-bump.py <asterisk|freepbx>
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

DOCKERFILE = Path("source/Dockerfile")

# Asterisk LTS line to follow. Moving to the next LTS is a deliberate change.
ASTERISK_SERIES = "22"
FREEPBX_LATEST_URL = "https://mirror.freepbx.org/modules/packages/freepbx/freepbx-17.0-latest.tgz"


def http_get(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "freepbx-docker-upstream-bump"})
    if accept:
        req.add_header("Accept", accept)
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def read_arg(name):
    match = re.search(rf"^ARG {name}=(.*)$", DOCKERFILE.read_text(), re.M)
    if not match:
        sys.exit(f"ARG {name} not found in {DOCKERFILE}")
    return match.group(1)


def write_args(values):
    text = DOCKERFILE.read_text()
    for name, value in values.items():
        text = re.sub(rf"^ARG {name}=.*$", f"ARG {name}={value}", text, count=1, flags=re.M)
    DOCKERFILE.write_text(text)


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def bump_asterisk():
    current = read_arg("ASTERISK_VERSION")
    releases = json.loads(http_get("https://api.github.com/repos/asterisk/asterisk/releases?per_page=100"))
    stable = [
        r["tag_name"]
        for r in releases
        if not r["prerelease"] and re.fullmatch(rf"{ASTERISK_SERIES}\.\d+\.\d+", r["tag_name"])
    ]
    if not stable:
        sys.exit(f"no stable Asterisk {ASTERISK_SERIES}.x release found")
    latest = max(stable, key=version_key)
    if version_key(latest) <= version_key(current):
        print(f"asterisk: {current} is current")
        return None

    base = f"https://github.com/asterisk/asterisk/releases/download/{latest}"
    published = http_get(f"{base}/asterisk-{latest}.sha256").decode().split()[0]
    tarball = http_get(f"{base}/asterisk-{latest}.tar.gz")
    actual = hashlib.sha256(tarball).hexdigest()
    if actual != published:
        sys.exit(f"asterisk {latest}: published sha256 {published} does not match download {actual}")

    write_args({"ASTERISK_VERSION": latest, "ASTERISK_SHA256": actual})
    return f"Asterisk {current} -> {latest}"


def bump_freepbx():
    current_version = read_arg("FREEPBX_VERSION")
    current_sha = read_arg("FREEPBX_SHA256")
    tarball = http_get(FREEPBX_LATEST_URL)
    sha = hashlib.sha256(tarball).hexdigest()
    if sha == current_sha:
        print(f"freepbx: {current_version} is current")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"freepbx-new.tgz"
        path.write_bytes(tarball)
        with tarfile.open(path) as tar:
            module_xml = tar.extractfile("freepbx/module.xml").read().decode()
        version = re.search(r"<version>([^<]+)</version>", module_xml).group(1)
        if version_key(version) < version_key(current_version):
            sys.exit(f"freepbx: upstream latest {version} is older than pinned {current_version}")

        # Mirror the exact file as a release asset so this pin stays buildable after
        # Sangoma replaces "latest".
        asset = Path(tmp) / f"freepbx-{version}.tgz"
        path.rename(asset)
        tag = f"freepbx-{version}"
        exists = subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
        if not exists:
            subprocess.run(
                ["gh", "release", "create", tag, str(asset),
                 "--title", f"FreePBX {version} source mirror",
                 "--notes", f"Unmodified copy of {FREEPBX_LATEST_URL} (sha256 {sha}).",
                 "--latest=false"],
                check=True,
            )

    write_args({"FREEPBX_VERSION": version, "FREEPBX_SHA256": sha})
    return f"FreePBX {current_version} -> {version}"


def main():
    bumpers = {"asterisk": bump_asterisk, "freepbx": bump_freepbx}
    if len(sys.argv) != 2 or sys.argv[1] not in bumpers:
        sys.exit(f"usage: {sys.argv[0]} <{'|'.join(bumpers)}>")
    summary = bumpers[sys.argv[1]]()
    output = os.environ.get("GITHUB_OUTPUT")
    if summary and output:
        with open(output, "a") as fh:
            fh.write(f"summary={summary}\n")
    if summary:
        print(summary)


if __name__ == "__main__":
    main()
