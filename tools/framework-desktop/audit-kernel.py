#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify the private ring ABI's source against the audited releases.

Reads a Linux source directory or tar archive without extracting it. This is
source evidence only: inspect the built/booted module's BTF and qualify DMA on
the hardware separately. See docs/framework-desktop-7-3.md and docs/framework-desktop-kernels.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

AUDITED = ("7.2.6", "7.2.10", "7.2.12", "7.3")
SHA256 = {
    "drivers/thunderbolt/nhi.c": "b8b78b1a524844c1487dbd2b1ef696610ebc8720caf13a2d2d8ccecfd4c989b4",
    "drivers/thunderbolt/nhi.h": "f0026407a0005510e34cb331dba9b4a360bb93bdb5c63cd0cec0f2273fdc1e5c",
    "drivers/thunderbolt/nhi_regs.h": "e98150dae51b46c1d83d92c0de0fe2b925e61e220a1a14d8cd200a153fc81e45",
    "include/linux/thunderbolt.h": "e883a1c144eb50ea09313631d845400a1bcd47a57334cf24eb19a97cde5c66ee",
}


# 7.3 changes ring modes, service probes and RDMA core/ops. Pin their
# audited bytes independently; the 7.2 sources are not reused as evidence.
SHA256_73 = {**SHA256,
    'drivers/thunderbolt/nhi.c': '5b680a6d921d9f7ec5dd48e5348e645b1bdca66273119cc9b5bdece899a09169',
    'include/linux/thunderbolt.h': '77314f7a9762cbd0296024a1cfe7a1fc54c9ef2568db0229ad614758e1cd22eb',
    'drivers/thunderbolt/domain.c': '0eee4613cb197c09271193e28bce5e81f222b3e533d0ccd01f8a5a99886781a0',
    'drivers/thunderbolt/xdomain.c': '44fc106405ba99a690f28ea3d5447120040bbae3c46ec3322628452b55651a89',
    'include/rdma/ib_umem.h': 'ad0ad205379ca5f217d37d1536ace9bd8a5498de3e104bd493722c10855e5d01',
    'include/rdma/ib_verbs.h': 'd7305b561e22a49c5f9247496ff106e21791062c5f8dd40996bf002fa0d046b3',
    'drivers/infiniband/core/umem.c': 'e022d142174b8355a0f925764b077e9bc5adfe610eb07e6965814c485046a1ab',
    'drivers/infiniband/core/umem_dmabuf.c': '5f18abde2b85cab629df49ea26952130c193c616fe30bdb4620e18efc827bccd',
    'drivers/infiniband/core/verbs.c': '9a070d7909d968068a74b6216594bc1ee97846860f316175a61842032e6a4d73',
    'drivers/infiniband/core/device.c': 'c1951c0a180f83a3189d513d9148f3df2c4ccd1846ab2ef80a2d402855c18a27',
    'drivers/infiniband/core/uverbs_cmd.c': 'b2114b5332ef487c3c95c53f0901f90859fc8a628adcfb8f76672798f34b08a9',
    'drivers/infiniband/core/uverbs_std_types_mr.c': '80dc1ce415950a96fa23d57fba326c3307d588c79f2a4b4dbaf1943f7628406e',
    'drivers/infiniband/core/uverbs_std_types_cq.c': '0c58f38ecbd09a0d16d2e456880b2bdb6b0c32f794f9a9f0bb964a9881d29b8f',
    'drivers/infiniband/core/uverbs_std_types_qp.c': 'fc29785efa10ca5f771f325b95f54ff36d20e28529ed6c5aba7971f0e9081bb7',
}


def audit(version, source, header=None):
    if version not in AUDITED:
        raise ValueError(f"Unaudited kernel: {version}")
    expected = SHA256_73 if version == "7.3" else SHA256
    if source.is_dir():
        content = {name: (source/name).read_bytes() for name in expected}
    else:
        with tarfile.open(source, "r|*") as archive:
            content = {}
            prefix = f"linux-{version}/"
            for member in archive:
                name = member.name.removeprefix(prefix)
                if not member.name.startswith(prefix) or name not in expected:
                    continue
                if not member.isfile():
                    raise ValueError(f"Not a regular source file: {name}")
                content[name] = archive.extractfile(member).read()
                if len(content) == len(expected):
                    break
            if content.keys() != expected.keys():
                raise ValueError('Missing audited files in source archive')
    actual = {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
    changed = [name for name in expected if expected[name] != actual[name]]
    if header and hashlib.sha256(header.read_bytes()).hexdigest() != expected["include/linux/thunderbolt.h"]:
        changed.append(str(header))
    if changed:
        raise ValueError("Kernel source/header differs from audited ABI: " + ", ".join(changed))
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
