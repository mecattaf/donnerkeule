# SPDX-License-Identifier: GPL-2.0-only
"""Prevent empty, reset, quarantined or error-bearing captures from passing."""
import copy
import importlib.util
import unittest
from production import ROOT

spec = importlib.util.spec_from_file_location('qualification', ROOT/'tools/framework-desktop/qualification-state.py')
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        text = ''
        for peer in range(2):
            text += f'peer {peer} backend=native rails=2 domain={peer}\n'
            text += '  push_done: requested=1 remote=1 ready=1\n'
            for rail in range(2):
                text += f'  rail=0x{rail} active=1 service_ready=1 data_ready=1 negotiated=1 remote_ready=1 link_speed=20Gb/s\n'
                text += '    descriptor_ready=1 quarantined=0\n'
                text += '    data_tx_completed=10 data_rx_completed=10\n'
        self.before = dict(host='fixture', kernel='7.2.12', boot_id='boot', srcversion=None, module_address='0x1000',
                           ports={'usb4_rdma0/1': '4: ACTIVE'},
                           summary=dict(verbs_registered='1', data_rx_bad_frame='0',
                                        dmabuf_batch_doorbell='1', dmabuf_batch_abi_supported='1',
                                        dmabuf_bulk_calls='10', dmabuf_bulk_frames='100'),
                           raw_peers=text, rails=qualification.parse_peers(text))
        self.after = copy.deepcopy(self.before)
        self.after['summary'].update(dmabuf_bulk_calls='20', dmabuf_bulk_frames='200')
        for rail in self.after['rails'].values():
            rail.update(data_tx_completed='20', data_rx_completed='20')

    def check(self):
        return qualification.compare(self.before, self.after, 4, 'both', True)

    def test_all_four_rails_and_bulk_counter_deltas(self):
        self.before['summary']['dmabuf_cache_bytes'] = '4096'
        self.after['summary']['dmabuf_cache_bytes'] = '0'
        self.before['summary']['data_tx_ack_match_current_max_ms'] = '100'
        self.after['summary']['data_tx_ack_match_current_max_ms'] = '0'
        self.assertEqual(self.check()['dmabuf_bulk_calls'], 10)

    def test_failures_do_not_pass(self):
        for change in ('empty', 'quarantined', 'error', 'reset', 'no_payload', 'no_bulk', 'no_push', 'no_active', 'wrong_kernel'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.after)
                rail = next(iter(self.after['rails'].values()))
                if change == 'empty':
                    self.after['rails'].clear()
                elif change == 'quarantined':
                    rail['quarantined'] = '1'
                elif change == 'error':
                    self.after['summary']['data_rx_bad_frame'] = '1'
                elif change == 'reset':
                    self.after['summary']['dmabuf_bulk_calls'] = '0'
                elif change == 'no_payload':
                    rail['data_tx_completed'] = '10'
                elif change == 'no_bulk':
                    self.after['summary']['dmabuf_bulk_calls'] = '10'
                elif change == 'no_push':
                    self.after['raw_peers'] = self.after['raw_peers'].replace('remote=1 ready=1', 'remote=1 ready=0')
                elif change == 'no_active':
                    self.after['ports'].clear()
                else:
                    self.after['kernel'] = '7.2.13'
                with self.assertRaises(ValueError):
                    self.check()
                self.after = original
