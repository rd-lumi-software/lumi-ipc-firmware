#!/usr/bin/env python3
"""Run the shipped storage state machine with command and device fault injection."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'overlay/lumi/bin/lumi-sd-check'

class StorageCheck(unittest.TestCase):
    def scenario(self, codes='0', *, busy=False, unmount_fail=False,
                 wrong_mount=False, changed=False, no_tool=False, action='start',
                 card=True, recorder_busy=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'sys/mmcblk0/device').mkdir(parents=True)
            (root/'sys/mmcblk0/device/cid').write_text('card-A\n')
            (root/'dev').mkdir()
            if card:
                (root/'dev/mmcblk0p1').touch()
            (root/'mountinfo').write_text('30 20 179:1 / '+('/overlay' if wrong_mount else '/mnt/mmcblk0p1')+' rw - vfat /dev/card-alias rw\n')
            (root/'codes').write_text(codes+'\n')
            (root/'bin').mkdir()
            if not no_tool:
                checker = root/'bin/fsck.fat'
                checker.write_text('''#!/bin/sh
printf 'fsck %s\\n' "$*" >> "$TEST_ROOT/events"
code=$(head -n 1 "$TEST_ROOT/codes")
sed '1d' "$TEST_ROOT/codes" > "$TEST_ROOT/codes.next"
mv "$TEST_ROOT/codes.next" "$TEST_ROOT/codes"
[ "${CHANGE_CARD:-0}" != 1 ] || echo card-B > "$TEST_ROOT/sys/mmcblk0/device/cid"
exit "${code:-0}"
''')
                checker.chmod(0o755)
            script = '''
. "$HELPER"
SYS_BLOCK="$TEST_ROOT/sys"; DEV_ROOT="$TEST_ROOT/dev"
MOUNTINFO="$TEST_ROOT/mountinfo"; RUN_DIR="$TEST_ROOT/run"
is_block() { [ -f "$1" ]; }
mkdir() {
 if [ "$1" = -p ] && [ "$2" = /mnt/mmcblk0p1 ]; then return 0; fi
 command mkdir "$@"
}
stat() { printf 'b3 1\\n'; }
pidof() {
 [ "${BUSY:-0}" = 1 ] && return 0
 [ "${RECORDER_BUSY:-0}" = 1 ] && [ "$1" = ipc-stream-recorder ] && return 0
 return 1
}
sleep() { :; }
timeout() { echo "timeout:$1" >> "$TEST_ROOT/events"; shift; "$@"; }
umount() {
 echo "umount:$*" >> "$TEST_ROOT/events"
 [ "${UNMOUNT_FAIL:-0}" != 1 ] || return 1
 : > "$TEST_ROOT/mountinfo"
}
mount() {
 echo "mount:$*" >> "$TEST_ROOT/events"
 echo '30 20 179:1 / /mnt/mmcblk0p1 rw - vfat /dev/mmcblk0p1 rw' > "$TEST_ROOT/mountinfo"
}
main "$ACTION"
'''
            env = dict(os.environ, TEST_ROOT=tmp, HELPER=str(HELPER),
                       PATH=str(root/'bin')+':/usr/bin:/bin', ACTION=action,
                       BUSY=str(int(busy)), RECORDER_BUSY=str(int(recorder_busy)),
                       UNMOUNT_FAIL=str(int(unmount_fail)), CHANGE_CARD=str(int(changed)))
            result = subprocess.run(['sh','-c',script],env=env,capture_output=True,text=True,timeout=5)
            events=(root/'events').read_text() if (root/'events').exists() else ''
            status=(root/'run/status').read_text().strip() if (root/'run/status').exists() else ''
            return result.returncode,status,events

    def test_clean_card_checked_offline_before_rw(self):
        code,status,events=self.scenario()
        self.assertEqual((code,status),(0,'ready'))
        self.assertLess(events.index('umount:'),events.index('fsck -n'))
        self.assertIn('mount:-t vfat -o rw',events)
        self.assertNotIn('fsck -a',events)

    def test_repair_exit_one_requires_clean_independent_verification(self):
        code,status,events=self.scenario('1\n1\n0')
        self.assertEqual((code,status),(0,'ready'))
        self.assertEqual(events.count('fsck -n'),2)
        self.assertIn('fsck -a /proc/self/fd/9',events)
        self.assertIn('mount:-t vfat -o rw',events)

    def test_incomplete_repair_stays_read_only(self):
        code,status,events=self.scenario('1\n1\n1')
        self.assertEqual((code,status),(1,'read_only'))
        self.assertIn('mount:-t vfat -o ro',events)
        self.assertNotIn('mount:-t vfat -o rw',events)

    def test_timeout_stays_read_only_without_retry(self):
        code,status,events=self.scenario('1\n124')
        self.assertEqual((code,status),(1,'read_only'))
        self.assertEqual(events.count('fsck -a'),1)
        self.assertIn('timeout:30',events)
        self.assertNotIn('mount:-t vfat -o rw',events)

    def test_missing_tool_never_admits_rw(self):
        code,status,events=self.scenario(no_tool=True)
        self.assertEqual((code,status),(1,'read_only'))
        self.assertIn('mount:-t vfat -o ro',events)

    def test_busy_mounted_volume_is_never_repaired(self):
        code,status,events=self.scenario(unmount_fail=True)
        self.assertEqual((code,status),(1,'fault'))
        self.assertNotIn('fsck ',events)

    def test_running_runtime_cannot_be_unmounted(self):
        code,status,events=self.scenario(busy=True)
        self.assertEqual((code,status),(1,'busy'))
        self.assertNotIn('umount:',events)
        self.assertNotIn('fsck ',events)

    def test_mounted_by_alias_outside_sd_target_is_rejected(self):
        code,status,events=self.scenario(wrong_mount=True)
        self.assertEqual((code,status),(1,'fault'))
        self.assertNotIn('umount:',events)
        self.assertNotIn('fsck ',events)

    def test_replaced_card_is_not_mounted(self):
        code,status,events=self.scenario(changed=True)
        self.assertEqual((code,status),(1,'fault'))
        self.assertNotIn('mount:-t',events)

    def test_absent_card_does_not_block_camera_boot(self):
        code,status,events=self.scenario(card=False)
        self.assertEqual((code,status),(0,'missing'))
        self.assertEqual(events,'')

    def test_shutdown_unmounts_and_does_not_run_repair(self):
        code,status,events=self.scenario(action='stop')
        self.assertEqual((code,status),(0,'unmounted'))
        self.assertIn('umount:',events)
        self.assertNotIn('fsck ',events)

    def test_shutdown_does_not_unmount_a_live_recorder(self):
        code,status,events=self.scenario(action='stop',recorder_busy=True)
        self.assertEqual((code,status),(1,'busy'))
        self.assertNotIn('umount:',events)

if __name__=='__main__':unittest.main()
