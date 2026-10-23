#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only readiness/counter evidence for the attended Framework pair run.

Never loads modules, changes links, or signals a service. Snapshot files are
created exclusively, so an earlier observation cannot be overwritten.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import time

DEBUGFS = Path('/sys/kernel/debug/thunderbolt_ibverbs')
ERROR_COUNTER = re.compile(r'error|bad_|lost|canceled|timeout|overflow|exhausted|repost_failed')
PAYLOAD_COUNTERS = ('data_tx_posted', 'data_tx_completed', 'data_rx_completed',
                    'dmabuf_bulk_calls', 'dmabuf_bulk_frames', 'dmabuf_bulk_fallback',
                    'dmabuf_host_tx_frames', 'dmabuf_host_rx_frames',
                    'dmabuf_cache_hits', 'dmabuf_cache_misses',
                    'dmabuf_copy_chunks', 'dmabuf_copy_bytes')


def parse_peers(text):
    rails, peer, current = {}, None, None
    for line in text.splitlines():
        if line.startswith('peer '):
            peer = line.split()[1]
            current = None
        elif line.startswith('  rail='):
            fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
            current = f'{peer}/{fields["rail"]}'
            rails[current] = fields
        elif current and line.startswith('    '):
            rails[current].update(re.findall(r'(\w+)=([^\s]+)', line))
    return rails


def read_state():
    summary = (DEBUGFS/'summary').read_text()
    peers = (DEBUGFS/'peers').read_text()
    module = Path('/sys/module/thunderbolt_ibverbs')
    srcversion = module/'srcversion'
    ports = {str(path): path.read_text().strip()
             for path in Path('/sys/class/infiniband').glob('usb4_rdma*/ports/*/state')}
    return dict(host=socket.gethostname(), kernel=os.uname().release,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                srcversion=srcversion.read_text().strip() if srcversion.exists() else None,
                module_address=(module/'sections/.text').read_text().strip(),
                ports=ports,
                summary=dict(re.findall(r'^(\w+): (\S+)$', summary, re.M)),
                rails=parse_peers(peers), raw_summary=summary, raw_peers=peers)


def ready(state, count):
    if state['summary'].get('verbs_registered') != '1':
        raise ValueError('verbs device is not registered')
    if not any(value.endswith(': ACTIVE') for value in state['ports'].values()):
        raise ValueError('no usb4_rdma port is ACTIVE (check the provider and naming rules)')
    if len(state['rails']) != count:
        raise ValueError(f'expected exactly {count} rails, got {len(state["rails"])}')
    if len(re.findall(r'^  push_done: requested=1 remote=1 ready=1$', state['raw_peers'], re.M)) != count // 2:
        raise ValueError('pushed-DONE control is not ready on each selected controller')
    required = dict(active='1', service_ready='1', data_ready='1', negotiated='1',
                    remote_ready='1', descriptor_ready='1', quarantined='0', link_speed='20Gb/s')
    for key, rail in state['rails'].items():
        if any(rail.get(name) != value for name, value in required.items()):
            raise ValueError(f'rail {key} is not ready: {rail}')


def compare(before, after, count, traffic, bulk):
    for key in ('host', 'kernel', 'boot_id', 'srcversion', 'module_address'):
        if before[key] != after[key]:
            raise ValueError(f'{key} changed between snapshots')
    ready(before, count)
    ready(after, count)
    if before['rails'].keys() != after['rails'].keys():
        raise ValueError('rail identities changed')
    # Check cumulative counters only. Cache bytes and current queue/latency
    # gauges may decrease legitimately after a normal QP close.
    delta = {}
    for key, value in before['summary'].items():
        if key in PAYLOAD_COUNTERS or (key.startswith('data_') and ERROR_COUNTER.search(key)):
            new = after['summary'].get(key, '')
            if not value.isdecimal() or not new.isdecimal() or int(new) < int(value):
                raise ValueError(f'counter missing or reset: {key}')
            delta[key] = int(new) - int(value)
    errors = {key: value for key, value in delta.items() if value and key.startswith('data_')
              and ERROR_COUNTER.search(key)}
    if errors:
        raise ValueError(f'error counter increments: {errors}')
    directions = ('tx', 'rx') if traffic == 'both' else (traffic,)
    for key, rail in after['rails'].items():
        for direction in directions:
            counter = f'data_{direction}_completed'
            if int(rail[counter]) <= int(before['rails'][key][counter]):
                raise ValueError(f'no {direction} payload completion on rail {key}')
    if bulk and (after['summary'].get('dmabuf_batch_abi_supported') != '1' or
                 after['summary'].get('dmabuf_batch_doorbell') != '1' or
                 delta.get('dmabuf_bulk_calls', 0) <= 0 or delta.get('dmabuf_bulk_frames', 0) <= 0):
        raise ValueError('no evidence that audited descriptor batching ran')
    return delta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    wait = sub.add_parser('wait')
    wait.add_argument('--timeout', type=int, default=240)
    wait.add_argument('--rails', type=int, choices=(2, 4), default=4)
    snap = sub.add_parser('snapshot')
    snap.add_argument('output', type=Path)
    check = sub.add_parser('compare')
    check.add_argument('before', type=Path)
    check.add_argument('after', type=Path)
    check.add_argument('--rails', type=int, choices=(2, 4), default=4)
    check.add_argument('--traffic', choices=('tx', 'rx', 'both'), required=True)
    check.add_argument('--bulk', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'snapshot':
            state = read_state()
            with args.output.open('x') as file:
                json.dump(state, file, indent=2)
        elif args.command == 'compare':
            print(json.dumps(compare(json.loads(args.before.read_text()),
                                     json.loads(args.after.read_text()), args.rails,
                                     args.traffic, args.bulk), indent=2))
        else:
            deadline = time.monotonic() + args.timeout
            while True:
                try:
                    ready(read_state(), args.rails)
                    print(f'PASS: {args.rails} ready rails and pushed-DONE control')
                    break
                except (OSError, ValueError) as error:
                    if time.monotonic() >= deadline:
                        raise ValueError(f'readiness timed out: {error}') from error
                    time.sleep(1)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'qualification-state: {error}\n')


if __name__ == '__main__':
    main()
