#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the carry-forward separately from lfthht's immutable measurement."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
baseline = json.loads((root/'docs/framework-desktop-tested-source.json').read_text())
port = json.loads((root/'docs/framework-desktop-port-source.json').read_text())
expected = dict(baseline['source_sha256'])
expected['userspace/usb4_rdma/usb4_rdma.c'] = baseline['provider_source_sha256']
expected.update(port['changes_sha256'])
changed = [name for name, digest in expected.items()
           if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest() != digest]
sources = {str(p.relative_to(root)) for directory in ('kernel', 'proto', 'include')
           for p in (root/directory).rglob('*') if p.suffix in ('.c', '.h')}
changed.extend(sorted(sources - expected.keys()))
if changed:
    raise SystemExit('Port source differs from its manifest: ' + ', '.join(changed))
print(f'PASS: {len(expected)} driver/provider files match the carry-forward manifest; '
      'this does not reproduce or extend the 7.2.6 hardware measurement.')
