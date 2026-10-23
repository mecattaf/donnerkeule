# SPDX-License-Identifier: GPL-2.0-only
#!/usr/bin/env python3
"""Exercise the actual optional posting helper with a mocked ring/MMIO device."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from production import ROOT, source_file


class BulkPostingTests(unittest.TestCase):
    def test_descriptor_order_wrap_capacity_and_fallback(self):
        compiler = shutil.which('cc')
        self.assertIsNotNone(compiler, 'A C compiler is required for the posting boundary test')
        added = source_file('kernel/verbs_dmabuf.c')
        first = added.index('struct tbv_bulk_desc {')
        last = added.index('\nfallback:', first)
        last = added.index('\n}', last) + 2
        helper = added[first:last]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory/'helper.c').write_text(helper)
            executable = directory/'posting-test'
            command = [compiler, '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-I', str(directory), '-I', str(ROOT/'kernel/compat'),
                str(Path(__file__).with_name('bulk-post-test.c')), '-o', str(executable)]
            for version, other_arch in (("7,2,6", False), ("7,2,10", False),
                    ("7,2,12", False), ("7,2,5", False), ("7,2,11", False),
                    ("7,2,13", False), ("7,3,0", False), ("7,3,1", False),
                    ("7,4,0", False), ("7,2,12", True), ("7,3,0", True)):
                with self.subTest(version=version, other_arch=other_arch):
                    flags = [f'-DLINUX_VERSION_CODE=KERNEL_VERSION({version})']
                    if other_arch:
                        flags.append('-DTBV_TEST_OTHER_ARCH')
                    # Exercise both native 7.3 and backported header flags.
                    if version in ('7,3,0', '7,2,12'):
                        flags.append('-DRING_FLAG_NO_INTERRUPT=8')
                    result = subprocess.run(command + flags, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
            # A same-version layout change must fail at build time.
            result = subprocess.run(command + ['-DTBV_TEST_LAYOUT_EXTRA=8'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('sizeof(struct tb_ring) != 184', result.stderr)


if __name__ == '__main__':
    unittest.main()
