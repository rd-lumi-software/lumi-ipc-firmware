#!/usr/bin/env python3
"""Host-side checks for the flash/OTA boundary and source/input validation."""
import hashlib
import gzip
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


firmware = module('firmware')


def cli(*args):
    return subprocess.run([sys.executable, str(HERE / 'firmware.py'), *map(str, args)],
                          check=True, text=True, capture_output=True)


def kernel(name=b'Linux-4.4.94-lumi-t33gs'):
    payload = b'test kernel payload'
    header = bytearray(struct.pack('>7I4B32s', 0x27051956, 0, 0, len(payload),
                                  0x80010000, 0x80010000, zlib.crc32(payload),
                                  5, 5, 2, 3, name))
    struct.pack_into('>I', header, 4, zlib.crc32(header))
    return bytes(header) + payload


def rootfs():
    data = bytearray(4096)
    data[:4] = b'hsqs'
    struct.pack_into('<HH', data, 28, 4, 0)
    struct.pack_into('<Q', data, 40, 96)
    return bytes(data)


class PipelineTests(unittest.TestCase):
    def test_riscv_payload_rejects_corruption_and_layout_mismatch(self):
        spec = importlib.util.spec_from_file_location(
            'rootfs_verifier', HERE.parents[1] / 'lumi/scripts/verify-t33-lumi-image.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as tmp:
            lumi = Path(tmp)
            (lumi / 'bin').mkdir()
            (lumi / 'firmware').mkdir()
            worker = lumi / 'bin/ipc-voice-worker'
            worker.write_bytes(b'/dev/lumi-riscv-mem')
            wrapper = lumi / 'bin/lumi-voice-riscv'
            wrapper.write_text('#!/bin/sh\nexit 0\n')
            wrapper.chmod(0o755)
            image = bytes(256)
            reloc = struct.pack('<3I', 1, 128, 0)
            valid = (struct.pack('<8I', 0x33565752, 1, 0x050d0000,
                                 0x100000, len(image), 0x80, 0xff000, 1)
                     + hashlib.sha256(image).digest() + hashlib.sha256(reloc).digest()
                     + image + reloc)
            payload = lumi / 'firmware/wake.rvpack'
            payload.write_bytes(valid)
            verifier.check_riscv_voice(lumi)
            bad_reloc = struct.pack('<3I', 99, 128, 0)
            bad_table = valid[:64] + hashlib.sha256(bad_reloc).digest() + image + bad_reloc
            for bad in (valid[:95], valid[:-1], valid[:100] + b'x' + valid[101:],
                        b'BAD!' + valid[4:], bad_table):
                payload.write_bytes(bad)
                with self.assertRaises(ValueError):
                    verifier.check_riscv_voice(lumi)
            payload.write_bytes(valid)
            worker.write_bytes(b'CPU only')
            with self.assertRaisesRegex(ValueError, 'lacks the RISC-V'):
                verifier.check_riscv_voice(lumi)
            worker.unlink()
            with self.assertRaisesRegex(ValueError, 'orphan'):
                verifier.check_riscv_voice(lumi)
            payload.unlink()
            verifier.check_riscv_voice(lumi)

    def test_riscv_launcher_selects_image_and_stops_on_driver_failure(self):
        import os
        source = (HERE.parents[1] / 'lumi/board/t33gs-prj008/overlay/lumi/bin/lumi-voice-riscv').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / 'worker'
            worker.write_text('#!/usr/bin/env python3\nimport os,json,sys\n'
                              'json.dump({"backend":os.environ["LUMI_WAKE_BACKEND"],'
                              '"image":os.environ["LUMI_RISCV_IMAGE"],"args":sys.argv[1:],'
                              '"trial":os.environ.get("LUMI_VOICE_PCM_TRIAL")},'
                              'open(os.environ["RECEIPT"],"w"))\n')
            worker.chmod(0o755)
            insmod = root / 'insmod'
            insmod.write_text('#!/bin/sh\nexit "$DRIVER_STATUS"\n')
            insmod.chmod(0o755)
            launcher = root / 'launcher'
            launcher.write_text(source.replace('/lumi/bin/ipc-voice-worker', str(worker)))
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                       RECEIPT=str(root / 'receipt'), LUMI_WAKE_BACKEND='cpu',
                       LUMI_VOICE_PCM_TRIAL='1', DRIVER_STATUS='0')
            subprocess.run(['sh', str(launcher), '--argument'], env=env, check=True)
            self.assertEqual(json.loads((root / 'receipt').read_text()),
                             dict(backend='riscv', image='/lumi/firmware/wake.rvpack',
                                  args=['--argument'], trial=None))
            (root / 'receipt').unlink()
            result = subprocess.run(['sh', str(launcher)], env=dict(env, DRIVER_STATUS='27'))
            self.assertEqual(result.returncode, 27)
            self.assertFalse((root / 'receipt').exists())

    def test_voice_disabled_boot_ignores_previously_provisioned_voice(self):
        init = (HERE.parents[1] / 'lumi/board/t33gs-prj008/overlay/etc/init.d/S60lumi-streamer').read_text()
        voice = init[init.index(' voice=/overlay/lumi-voice'):init.index(' # Keep the lightweight recorder')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('ENABLED', 'READY'):
                (root / name).touch()
            (root / 'voice.conf').write_text('exit 83\n')
            code = ('set -eu\nBIN=$1/missing-bin\nexport LUMI_MODULE_VOICE=1\n'
                    + voice.replace('voice=/overlay/lumi-voice', 'voice=$1')
                    + '\n[ "$LUMI_MODULE_VOICE" = 0 ]\n')
            subprocess.run(['sh', '-c', code, 'voice-disabled', str(root)], check=True)

    def test_kernel_verifier_rejects_uimage_name_incompatible_with_ota(self):
        spec = importlib.util.spec_from_file_location(
            'kernel_verifier', HERE.parents[1] / 'contrib/verify-t33gs-k4494.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'kernelrelease.txt').write_text('4.4.94-lumi-t33gs\n')
            # Valid header/payload CRCs; its name differs from the OTA identity.
            (root / 'uImage').write_bytes(kernel(name=b'Linux--t33'))
            with self.assertRaisesRegex(ValueError, 'uImage name'):
                verifier.validate(root)

    def test_runtime_installer_handles_optional_voice_and_validates_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / 'runtime'
            names = ('lumi-gateway-permissions', 'install-security', 'ipc-stream-core',
                     'ipc-stream-services', 'ipc-stream-supervisor', 'lumi-config',
                     'lumi-snapshot-ffmpeg', 'lumi-t33gs-relay-agent')
            for name in names:
                path = runtime / 'bin' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/bin/sh\nexit 0\n')
                path.chmod(0o755)
            (runtime / 'bin/lumi-t33gs-relay-agent').write_text(
                '#!/bin/sh\nreadonly logfile=/tmp/lumi-t33gs-relay-agent.log\n')
            gateway = runtime / 'bin/ipc-stream-services'
            (runtime / 'bin/ipc-stream-services.build-info').write_text(
                'webrtc_backend=str0m; srtp=t33gs-dma-aes-aes128-gcm-direct-mxu2-ghash\n'
                'features=t33gs-dma-aes,t33gs-dma-gcm-batch,t33gs-dma-gcm-mxu2\n'
                + firmware.digest(gateway) + '  /build/ipc-stream-services.t33gs\n')
            recorder = runtime / 'recording/bin/ipc-stream-recorder'
            recorder.parent.mkdir(parents=True)
            recorder.write_text('recorder')
            recorder.chmod(0o755)
            (runtime / 'bin/relay-agent.t33gs.gz').write_bytes(gzip.compress(b'relay'))
            (runtime / 'tunnel.cert').write_text('public certificate')
            for license in ('LGPLv2.1', 'zlib', 'libjpeg-turbo'):
                (runtime / ('bin/lumi-snapshot-ffmpeg.COPYING.' + license)).write_text(license)
            voice = runtime / 'voice/bin/ipc-voice-worker'
            voice.parent.mkdir(parents=True)
            voice.write_text('voice')
            voice.chmod(0o755)
            copying = root / 'COPYING'
            copying.write_text('kernel license')
            target = root / 'target'
            import os
            payload = root / 'wake.rvpack'
            payload.write_bytes(b'source-built wake payload')
            env = dict(os.environ, T33_RUNTIME_DIR=str(runtime), T33_KERNEL_COPYING=str(copying),
                       T33_RISCV_IMAGE=str(payload))
            script = HERE.parents[1] / 'lumi/scripts/install-t33-runtime.sh'
            def install():
                files = sorted(p for p in runtime.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
                (runtime / 'SHA256SUMS').write_text(''.join(
                    firmware.digest(p) + '  ' + str(p.relative_to(runtime)) + '\n' for p in files))
                subprocess.run(['bash', str(script), str(target)], env=env, check=True,
                               stdout=subprocess.DEVNULL)
            install()
            self.assertEqual((target / 'lumi/bin/relay-agent.t33gs').read_bytes(), b'relay')
            self.assertIn('readonly logfile=/tmp/log/lumi-t33gs-relay-agent.log\n',
                          (target / 'lumi/bin/lumi-t33gs-relay-agent').read_text())
            self.assertTrue((target / 'lumi/bin/ipc-voice-worker').is_file())
            self.assertEqual((target / 'lumi/firmware/wake.rvpack').read_bytes(), payload.read_bytes())
            voice.unlink()
            install()
            self.assertFalse((target / 'lumi/bin/ipc-voice-worker').exists())
            self.assertFalse((target / 'lumi/firmware/wake.rvpack').exists())
            (runtime / 'relay-key.json').write_text('private fixture identity')
            with self.assertRaises(subprocess.CalledProcessError):
                install()

    def test_buildroot_runtime_pins_qualified_gateway_profile(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'package'
            for role in ('lumi-ipc-streamer', 'iot-relay-cloud', 'tflm', 'opus'):
                (package / 'source' / role).mkdir(parents=True)
            voice = package / 'source/lumi-ipc-streamer/scripts/build_voice_runtime.sh'
            voice.parent.mkdir()
            voice.write_text('#!/bin/sh\nRECEIPT="$RECEIPT.voice" make\n')
            (voice.parent / 'build_wakeword_riscv.sh').write_text('#!/bin/sh\nexit 0\n')
            tools = root / 'tools'
            tools.mkdir()
            (tools / 'cmake').write_text('#!/bin/sh\nexit 0\n')
            (tools / 'cmake').chmod(0o755)
            (tools / 'make').write_text(
                '#!/usr/bin/env python3\nimport os,json,sys,pathlib\n'
                'for arg in sys.argv[1:]:\n'
                ' if arg.startswith("BUILD_DIR="):\n'
                '  p=pathlib.Path(arg.split("=",1)[1]);p.mkdir(parents=True,exist_ok=True);(p/"wake.rvpack").write_bytes(b"built")\n'
                'json.dump({k:os.environ.get(k) for k in '
                '["T33GS_GATEWAY_DMA_AES","T33GS_GATEWAY_DMA_GCM_BATCH",'
                '"T33GS_GATEWAY_DMA_GCM_MXU2","T33GS_VOICE_WAKE_BACKEND","GIT_DIR"]},open(os.environ["RECEIPT"],"w"))\n')
            (tools / 'make').chmod(0o755)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       LUMI_RUNTIME_BUILD=str(package), LUMI_WORKSPACE=str(root),
                       T33GS_MUSL_TOOLCHAIN=str(root), T33GS_UCLIBC_TOOLCHAIN=str(root),
                       LUMI_BUILD_VOICE='0', LUMI_INPUTS=str(root), RISCV_PREFIX='/usr/bin/',
                       T33GS_GATEWAY_DMA_AES='0', T33GS_GATEWAY_DMA_GCM_BATCH='0',
                       T33GS_GATEWAY_DMA_GCM_MXU2='0', GIT_DIR='.', RECEIPT=str(root / 'receipt'))
            expected = {
                'T33GS_GATEWAY_DMA_AES': '1', 'T33GS_GATEWAY_DMA_GCM_BATCH': '1',
                'T33GS_GATEWAY_DMA_GCM_MXU2': '1', 'T33GS_VOICE_WAKE_BACKEND': None, 'GIT_DIR': None}
            for enabled in ('0', '1'):
                with self.subTest(voice=enabled):
                    subprocess.run(
                        ['bash', str(HERE.parents[1] / 'lumi/scripts/build-t33-runtime.sh')],
                        env=dict(env, LUMI_BUILD_VOICE=enabled), check=True)
                    self.assertEqual(json.loads((root / 'receipt').read_text()), expected)
                    if enabled == '1':
                        self.assertEqual(json.loads((root / 'receipt.voice').read_text()),
                                         dict(expected, T33GS_VOICE_WAKE_BACKEND='riscv'))

    def test_gateway_profile_rejects_crypto_downgrade_and_stale_elf(self):
        spec = importlib.util.spec_from_file_location(
            'gateway_profile', HERE.parents[1] / 'lumi/scripts/t33-gateway-profile.py')
        profile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(profile)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bin').mkdir()
            binary = root / 'bin/ipc-stream-services'
            binary.write_bytes(b'qualified gateway')
            receipt = root / 'bin/ipc-stream-services.build-info'
            valid = ('webrtc_backend=str0m; srtp=' + profile.BACKEND + '\n'
                     'features=t33gs-dma-aes,t33gs-dma-gcm-batch,t33gs-dma-gcm-mxu2\n'
                     + profile.digest(binary) + '  /build/ipc-stream-services.t33gs\n')
            receipt.write_text(valid)
            destination = root / 'gateway-profile.json'
            profile.create(root, destination)
            profile.validate(json.loads(destination.read_text()), binary)
            for bad in [valid.replace(profile.BACKEND, 't33gs-dma-aes-aes128-gcm'),
                        valid.replace(',t33gs-dma-gcm-mxu2', ''),
                        valid + 'features=t33gs-dma-aes\n',
                        valid.replace(profile.digest(binary), '0' * 64)]:
                receipt.write_text(bad)
                with self.assertRaises(ValueError):
                    profile.create(root, destination)
            receipt.write_text(valid)
            binary.write_bytes(b'unrelated gateway')
            with self.assertRaises(ValueError):
                profile.validate(json.loads(destination.read_text()), binary)
            receipt.unlink()
            with self.assertRaises(FileNotFoundError):
                profile.create(root, destination)

    def test_board_layout_rejects_overlap_and_mismatched_consumers(self):
        nor = firmware.nor_packer()
        board = HERE.parents[1] / 'lumi/board/t33gs-prj008'
        firmware.check_board(board / 't33.fragment', fw_env=board / 'overlay/etc/fw_env.config')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'layout.json'
            layout = json.loads(json.dumps(nor.LAYOUT))
            layout['partitions'][2]['offset'] += 32768
            path.write_text(json.dumps(layout))
            with self.assertRaisesRegex(ValueError, 'partition'):
                nor.load_layout(path)
            bad_env = Path(temp) / 'fw_env.config'
            bad_env.write_text('/dev/mtd4 0x0 0x4000 0x10000\n')
            with self.assertRaisesRegex(ValueError, 'environment layout'):
                firmware.check_board(fw_env=bad_env)
            cfg = Path(temp) / 'kernel.config'
            cfg.write_text('CONFIG_CMA=y\nCONFIG_CMA_SIZE_MBYTES=32\n')
            with self.assertRaisesRegex(ValueError, 'Kernel layout mismatch'):
                firmware.check_board(kernel_config=cfg)

    def test_overlay_collision_requires_explicit_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for layer in ('general/overlay', 'lumi/overlay'):
                path = root / layer / 'etc/config'
                path.parent.mkdir(parents=True)
                path.write_text(layer)
            board = root / 'lumi/board/t33gs-prj008'
            board.mkdir(parents=True)
            allow = board / 'overlay-overrides.json'
            allow.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Unreviewed overlay override'):
                firmware.overlay_inventory(root)
            allow.write_text(json.dumps({'etc/config': ['general/overlay', 'lumi/overlay']}))
            self.assertEqual(firmware.overlay_inventory(root)['etc/config']['source'], 'lumi/overlay')

    def test_board_updater_retains_ram_flash_and_checks_identity(self):
        source = (HERE.parents[1] / 'lumi/overlay/usr/sbin/sysupgrade').read_text()
        result = firmware.adapt_updater(source)
        self.assertIn('enter_ramfs()', result)
        self.assertIn('skip_selfupdate=1', result)
        self.assertIn('vendor=ingenic', result)
        self.assertIn('set -- root', result)
        self.assertIn('Wrong T33gs NOR layout', result)
        self.assertIn('= "Linux-4.4.94-lumi-t33gs"', result)
        self.assertIn('ksoc=t33', result)
        self.assertNotIn('vendor=$(ipcinfo -v)', result)
        self.assertNotIn('check_soc "$(head -1 $y/etc/hostname', result)
        self.assertNotIn('compare_versions "$kernel_version"', result)
        self.assertIn('md5sum -s -c', result)
        self.assertIn('refusing live-rootfs flashing', result)
        with tempfile.NamedTemporaryFile(mode='w') as script:
            script.write(result)
            script.flush()
            subprocess.run(['/bin/sh', '-n', script.name], check=True)
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'lumi-sysupgrade'
            cli('install-updater', HERE.parents[1] / 'lumi/overlay/usr/sbin/sysupgrade',
                destination)
            self.assertEqual(destination.read_text(), result)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o755)
        with self.assertRaisesRegex(ValueError, 'contract changed'):
            firmware.adapt_updater(source.replace('vendor=$(ipcinfo -v)', 'vendor=changed'))

    def test_updater_accepts_current_map_and_rejects_old_rootfs_layout(self):
        source = (HERE.parents[1] / 'lumi/overlay/usr/sbin/sysupgrade').read_text()
        guard = firmware.adapt_updater(source).split('free_resources() {', 1)[1].split(
            '/etc/init.d/S61lumi-streamer-watch stop', 1)[0]
        with tempfile.TemporaryDirectory() as temp:
            mtd = Path(temp) / 'mtd'
            current = ('dev: size erasesize name\n'
                       'mtd0: 00040000 00008000 "boot"\n'
                       'mtd1: 00280000 00008000 "kernel"\n'
                       'mtd2: 00c00000 00008000 "root"\n'
                       'mtd3: 00138000 00008000 "rootfs_data"\n'
                       'mtd4: 00008000 00008000 "env"\n')
            script = 'die() { exit 21; }\n' + guard.replace('/proc/mtd', str(mtd))
            for layout, code in ((current, 0), (current.replace('00c00000', '00400000'), 21)):
                mtd.write_text(layout)
                result = subprocess.run(['/bin/sh', '-c', script])
                self.assertEqual(result.returncode, code)

    def test_full_layout_and_sysupgrade_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'artifacts'
            inputs = Path(temp)
            (inputs / 'uboot').write_bytes(b'uboot')
            (inputs / 'kernel').write_bytes(kernel())
            (inputs / 'rootfs').write_bytes(rootfs())
            (inputs / 'sources.json').write_text('{}')
            cli('package', '--uboot', inputs / 'uboot', '--kernel', inputs / 'kernel',
                '--rootfs', inputs / 'rootfs', '--sources', inputs / 'sources.json',
                '--inputs-sha256', 'a' * 64, '--output', out)
            image = (out / 'lumi-t33gs-full.bin').read_bytes()
            self.assertEqual(len(image), 16 * 1024 * 1024)
            self.assertEqual(image[0x40000:0x40000 + len(kernel())], kernel())
            self.assertEqual(image[0x2c0000:0x2c1000], rootfs())
            self.assertEqual(image[0xec0000:0xff8000], b'\xff' * 0x138000)
            with tarfile.open(out / 'lumi-t33gs-ota.tgz') as tar:
                self.assertEqual(set(tar.getnames()), {'uImage.t33', 'rootfs.squashfs.t33',
                    'uImage.t33.md5sum', 'rootfs.squashfs.t33.md5sum'})
                for name in ('uImage.t33', 'rootfs.squashfs.t33'):
                    data = tar.extractfile(name).read()
                    expected = hashlib.md5(data).hexdigest() + '  ' + name + '\n'
                    self.assertEqual(tar.extractfile(name + '.md5sum').read().decode(), expected)
            for line in (out / 'SHA256SUMS').read_text().splitlines():
                checksum, name = line.split('  ')
                self.assertEqual(firmware.digest(out / name), checksum)
            with self.assertRaises(FileExistsError):
                firmware.package(b'uboot', kernel(), rootfs(), {}, 'a' * 64, out)

    def test_corrupt_or_oversized_input_is_not_published(self):
        for boot, kern, root in ((b'uboot', kernel()[:-1] + b'x', rootfs()),
                                  (b'uboot', kernel(name=b'Linux--t33'), rootfs()),
                                  (b'x' * 262145, kernel(), rootfs()),
                                  (b'uboot', kernel(), b'not squashfs'),
                                  (b'uboot', kernel(), rootfs() + bytes(12 * 1024 * 1024))):
            with self.subTest(size=len(root)), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / 'artifacts'
                with self.assertRaises(ValueError):
                    firmware.package(boot, kern, root, {}, 'a' * 64, out)
                self.assertFalse(out.exists())

    def test_archive_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ('a', 'b'):
                firmware.package(b'uboot', kernel(), rootfs(), {}, 'a' * 64, Path(temp) / name)
            self.assertEqual((Path(temp) / 'a/lumi-t33gs-ota.tgz').read_bytes(),
                             (Path(temp) / 'b/lumi-t33gs-ota.tgz').read_bytes())

    def test_sdk_checksums_cannot_escape_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'bundle'
            root.mkdir()
            outside = Path(temp) / 'outside'
            outside.write_text('data')
            (root / 'link').symlink_to(outside)
            for name in ('../outside', 'link'):
                sums = root / 'SHA256SUMS'
                sums.write_text(firmware.digest(outside) + '  ' + name + '\n')
                with self.assertRaisesRegex(ValueError, 'path|escapes'):
                    firmware.verify_inputs(root, firmware.digest(sums))
            with self.assertRaisesRegex(ValueError, 'differs'):
                firmware.verify_inputs(root, '0' * 64)

    def test_complete_sdk_and_tamper_detection(self):
        names = ('sdk/kernel-4.4.94.7z', 'sdk/drivers.7z',
                 'uclibc/bin/mips-linux-uclibc-gcc', 'musl/bin/mipsel-linux-muslsf-gcc',
                 'imp/include/imp/imp_isp.h', 'board/opt/ingenic-t33/lib/libimp.so',
                 'board/opt/ingenic-t33/lib/ld-uClibc-0.9.33.2.so',
                 'board/etc/sensor/sc4336-PRJ008-day.bin',
                 'board/etc/sensor/sc4336-PRJ008-night.bin', 'board/lib/firmware/wifi.bin',
                 'aic8800.tar.gz', 'tunnel.cert', 'PROVENANCE.md')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
                path.chmod(0o755)
            link = 'board/opt/ingenic-t33/lib/libc.so'
            (root / link).symlink_to('libimp.so')
            names = (*names, link)
            sums = root / 'SHA256SUMS'
            sums.write_text(''.join(firmware.digest(root / n) + '  ./' + n + '\n' for n in names))
            expected = firmware.digest(sums)
            self.assertEqual(json.loads(cli('check-inputs', root, '--sha256', expected).stdout)['files'], len(names))
            (root / 'board/lib/firmware/wifi.bin').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                firmware.verify_inputs(root, expected)


if __name__ == '__main__':
    unittest.main()
