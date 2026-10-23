#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify the private ring ABI's source against the audited stable releases.

Reads a Linux source directory or tar archive without extracting it. This is
source evidence only: inspect the built/booted module's BTF and qualify DMA on
the hardware separately. See docs/framework-desktop-kernels.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

AUDITED = ("7.2.6", "7.2.10", "7.2.12")
SHA256 = {
    "drivers/thunderbolt/nhi.c": "b8b78b1a524844c1487dbd2b1ef696610ebc8720caf13a2d2d8ccecfd4c989b4",
    "drivers/thunderbolt/nhi.h": "f0026407a0005510e34cb331dba9b4a360bb93bdb5c63cd0cec0f2273fdc1e5c",
    "drivers/thunderbolt/nhi_regs.h": "e98150dae51b46c1d83d92c0de0fe2b925e61e220a1a14d8cd200a153fc81e45",
    "include/linux/thunderbolt.h": "e883a1c144eb50ea09313631d845400a1bcd47a57334cf24eb19a97cde5c66ee",
}


def audit(version, source, header=None):
    if version not in AUDITED:
        raise ValueError(f"Unaudited kernel: {version}")
    if source.is_dir():
        content = {name: (source/name).read_bytes() for name in SHA256}
    else:
        with tarfile.open(source, "r|*") as archive:
            content = {}
            prefix = f"linux-{version}/"
            for member in archive:
                name = member.name.removeprefix(prefix)
                if not member.name.startswith(prefix) or name not in SHA256:
                    continue
                if not member.isfile():
                    raise ValueError(f"Not a regular source file: {name}")
                content[name] = archive.extractfile(member).read()
                if len(content) == len(SHA256):
                    break
            if content.keys() != SHA256.keys():
                raise ValueError('Missing audited files in source archive')
    actual = {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
    changed = [name for name in SHA256 if SHA256[name] != actual[name]]
    if header and hashlib.sha256(header.read_bytes()).hexdigest() != SHA256["include/linux/thunderbolt.h"]:
        changed.append(str(header))
    if changed:
        raise ValueError("NHI source differs from audited ABI: " + ", ".join(changed))
    return {"version": version, "source_sha256": actual, "hardware_qualified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", choices=AUDITED)
    parser.add_argument("source", type=Path)
    parser.add_argument("--header", type=Path, help="Also check the actual kernel.dev thunderbolt.h")
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.version, args.source, args.header), indent=2))
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"audit-kernel: {error}\n")
