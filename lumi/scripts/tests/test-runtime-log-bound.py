#!/usr/bin/env python3
"""Verify retained O_APPEND writers keep the same bounded log inode."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WATCH = Path(__file__).resolve().parents[2] / 'board/t33gs-prj008/overlay/etc/init.d/S61lumi-streamer-watch'
FUNCTION = WATCH.read_text().split('trim_runtime_log() {', 1)[1].split('\nwlan_ip()', 1)[0]
FUNCTION = 'trim_runtime_log() {' + FUNCTION


class RuntimeLogBound(unittest.TestCase):
    def run_trim(self, path):
        subprocess.run(['sh', '-c', FUNCTION + '\ntrim_runtime_log "$1"', 'test', str(path)], check=True)

    def test_open_writer_survives_and_tail_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime.log'
            tail = b'last-record\n' * 1000
            path.write_bytes(b'x' * 2200000 + tail)
            before = path.stat()
            writer = os.open(path, os.O_WRONLY | os.O_APPEND)
            try:
                self.run_trim(path)
                self.assertEqual(path.stat().st_ino, before.st_ino)
                self.assertEqual(path.stat().st_dev, before.st_dev)
                self.assertLess(path.stat().st_size, 1100000)
                self.assertIn(tail, path.read_bytes())
                os.write(writer, b'after-trim\n')
                self.assertTrue(path.read_bytes().endswith(b'after-trim\n'))
                self.assertEqual(list(Path(directory).glob('*.trim.*')), [])
            finally:
                os.close(writer)

    def test_small_missing_and_symlink_logs_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'small'
            path.write_bytes(b'keep\n')
            self.run_trim(path)
            self.assertEqual(path.read_bytes(), b'keep\n')
            target = root / 'target'
            target.write_bytes(b'x' * 2200000)
            link = root / 'link'
            link.symlink_to(target)
            self.run_trim(link)
            self.assertEqual(target.stat().st_size, 2200000)
            self.run_trim(root / 'missing')
            self.assertFalse((root / 'missing').exists())


if __name__ == '__main__':
    unittest.main()
