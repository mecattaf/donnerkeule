#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inventory the 7.2.12 -> 7.3 Thunderbolt/RDMA core and public-header delta.

Accepts source directories or tar archives. Does not extract archives, execute
source, load modules, or examine the host runtime. Hardware HCA drivers under
drivers/infiniband/hw are outside this software USB4 driver's review scope.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile

SCOPES = ("drivers/thunderbolt/", "drivers/infiniband/core/",
          "include/rdma/", "include/uapi/rdma/")
EXTRA_HEADERS = tuple("include/linux/" + name + ".h" for name in
                      ("thunderbolt", "dma-buf", "dma-mapping", "scatterlist",
                       "mm", "mm_types", "pagemap"))
FUNCTIONS = ("ring_work", "__tb_ring_enqueue", "ring_iowrite_cons",
             "ring_iowrite_prod", "tb_ring_flush", "tb_ring_throttling")


def selected(name):
    return name.startswith(SCOPES) or name in EXTRA_HEADERS


def read_source(path, version):
    if path.is_dir():
        return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*")
                if p.is_file() and selected(str(p.relative_to(path)))}
    content = {}
    prefix = f"linux-{version}/"
    with tarfile.open(path, "r|*") as archive:
        for member in archive:
            name = member.name.removeprefix(prefix)
            if member.name.startswith(prefix) and member.isfile() and selected(name):
                content[name] = archive.extractfile(member).read()
    return content


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compare(old, new):
    changed, unchanged = {}, {}
    for name in sorted(old.keys() | new.keys()):
        hashes = [digest(s[name]) if name in s else None for s in (old, new)]
        if hashes[0] == hashes[1]:
            unchanged[name] = hashes[0]
        else:
            changed[name] = dict(zip(("7.2.12", "7.3"), hashes))
    functions = {}
    for name in FUNCTIONS:
        pattern = rf"^(?:static )?[^\n]*\b{name}\([^;{{]*?^\{{[\s\S]*?^\}}"
        hashes = []
        for source in (old, new):
            matches = re.findall(pattern, source["drivers/thunderbolt/nhi.c"].decode(), re.M)
            if len(matches) != 1:
                raise ValueError(f"Expected one NHI function: {name}")
            hashes.append(digest((matches[0] + "\n").encode()))
        functions[name] = {"identical": hashes[0] == hashes[1],
                           "sha256": dict(zip(("7.2.12", "7.3"), hashes))}
    return {"versions": ["7.2.12", "7.3"], "scope": list(SCOPES) + list(EXTRA_HEADERS),
            "file_counts": {"7.2.12": len(old), "7.3": len(new),
                            "changed_or_added": len(changed), "unchanged": len(unchanged)},
            "changed_sha256": changed, "unchanged_sha256": unchanged,
            "nhi_functions": functions, "hardware_qualified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_source", type=Path)
    parser.add_argument("new_source", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(read_source(args.old_source, "7.2.12"),
                             read_source(args.new_source, "7.3")), indent=2))
