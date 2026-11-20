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
    def run_trim(self, path, setup=''):
        script = setup + '\n' + FUNCTION + '\ntrim_runtime_log "$1"'
        subprocess.run(['sh', '-c', script, 'test', str(path)], check=True)

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

    def test_partial_busybox_tail_reclaims_space_on_same_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime.log'
            path.write_bytes(b'x' * 2200000)
            inode = path.stat().st_ino
            with path.open('ab', buffering=0) as writer:
                self.run_trim(path, 'tail() { printf partial; }; logger() { :; }')
                self.assertEqual(path.stat().st_ino, inode)
                self.assertEqual(path.stat().st_size, 0)
                writer.write(b'after-trim\n')
                self.assertEqual(path.read_bytes(), b'after-trim\n')
            self.assertEqual(list(Path(directory).glob('*.trim.*')), [])


class RuntimeRecovery(unittest.TestCase):
    def test_budget_resets_after_thirty_minutes_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['sh', '-eu', '-c', '''
                . "$1"
                RECOVERY=$2/recovery
                READY=$2/ready
                ARMED=$2/armed
                INHIBIT=$2/stopped
                OTA_LOCK=$2/ota
                STREAMER_BIN=$2/absent
                : > "$READY"
                printf '2 previous-boot supervisor-exited\\n' > "$RECOVERY"
                test_uptime=100
                trim_runtime_log() { :; }
                streamer_running() { return 0; }
                wlan_ip() { :; }
                mountpoint() { return 0; }
                read() {
                    if [ "$*" = '-r uptime ignored' ]; then
                        uptime=$test_uptime
                    else
                        command read "$@"
                    fi
                }
                sleep() {
                    case "$test_uptime" in
                        100) test_uptime=1899 ;;
                        1899)
                            [ "$(cat "$RECOVERY")" = '2 previous-boot supervisor-exited' ]
                            test_uptime=1900
                            ;;
                        1900)
                            [ "$(cat "$RECOVERY")" = '0 previous-boot supervisor-exited' ]
                            exit 0
                            ;;
                    esac
                }
                watch
            ''', 'test', str(WATCH), directory], check=True, timeout=5)

    def test_persists_attempt_and_refuses_duplicate_or_exhausted_reboot(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['sh', '-eu', '-c', '''
                . "$1"
                RECOVERY=$2/recovery
                INHIBIT=$2/stopped
                REQUESTED=$2/requested
                OTA_LOCK=$2/ota
                streamer_running() { return 1; }
                mountpoint() { return 0; }
                logger() { :; }
                reboot() { printf 'reboot\\n' >> "$RECOVERY.calls"; }
                recover
                read_recovery
                [ "$attempts" = 1 ]
                [ "$reason" = supervisor-exited ]
                recover
                [ "$(wc -l < "$RECOVERY.calls")" = 1 ]
                rm "$REQUESTED"
                recover
                [ "$(wc -l < "$RECOVERY.calls")" = 1 ]
                rm "$REQUESTED"
                write_recovery 1 previous-boot supervisor-exited
                recover
                read_recovery
                [ "$attempts" = 2 ]
                [ "$(wc -l < "$RECOVERY.calls")" = 2 ]
                rm "$REQUESTED"
                recover
                [ "$(wc -l < "$RECOVERY.calls")" = 2 ]
            ''', 'test', str(WATCH), directory], check=True)

    def test_stop_and_ota_inhibit_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['sh', '-eu', '-c', '''
                . "$1"
                RECOVERY=$2/recovery
                INHIBIT=$2/stopped
                REQUESTED=$2/requested
                OTA_LOCK=$2/ota
                streamer_running() { return 1; }
                reboot() { exit 99; }
                : > "$INHIBIT"
                recover
                rm "$INHIBIT"
                : > "$OTA_LOCK"
                recover
                [ ! -e "$REQUESTED" ] && [ ! -e "$RECOVERY" ]
            ''', 'test', str(WATCH), directory], check=True)


if __name__ == '__main__':
    unittest.main()
