#!/usr/bin/env python3
"""Host-only production assembly of the reviewed 4.4.94 DMA provider/service."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('prepare', 'module'))
    p.add_argument('--linux-repo', type=Path, required=True)
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--build', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cross')
    a = p.parse_args()
    src = a.linux_repo / 'kernel/ingenic/t33gs-aes-dma4494'
    if a.phase == 'prepare':
        spec = importlib.util.spec_from_file_location('provider_prepare', src / 'provider/prepare.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        c = a.kernel / 'drivers/dma/ingenic/ingenic_dma.c'
        h = a.kernel / 'drivers/dma/ingenic/ingenic_dma.h'
        profile = json.loads((src / 'profile.json').read_text())
        if (a.kernel / 'include/linux/ingenic_aes_dma_report.h').exists():
            # Verify reuse by reversing the exact reviewed patch in a temporary
            # tree and checking both original hashes; never reverse the SDK.
            with tempfile.TemporaryDirectory() as temporary:
                tmp = Path(temporary)
                for rel in ('drivers/dma/ingenic/ingenic_dma.c', 'drivers/dma/ingenic/ingenic_dma.h',
                            'drivers/dma/ingenic/report_impl.h', 'include/linux/ingenic_aes_dma_report.h'):
                    dst = tmp / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(a.kernel / rel, dst)
                subprocess.run(['patch', '--batch', '-R', '-p1', '-d', str(tmp)],
                               input=(src / 'provider/0001-aes-completion-report.patch').read_bytes(), check=True)
                for rel in ('drivers/dma/ingenic/ingenic_dma.c', 'drivers/dma/ingenic/ingenic_dma.h'):
                    if sha(tmp / rel) != profile['source_sha256'][rel]:
                        raise ValueError('Modified report provider: ' + rel)
            for name, rel in (('report_impl.h', 'drivers/dma/ingenic/report_impl.h'),
                              ('ingenic_aes_dma_report.h', 'include/linux/ingenic_aes_dma_report.h')):
                if sha(src / 'provider' / name) != sha(a.kernel / rel):
                    raise ValueError('Modified report API: ' + name)
            return
        for path in (c, h):
            name = str(path.relative_to(a.kernel))
            if sha(path) != profile['source_sha256'][name]:
                raise ValueError('Unexpected provider preimage: ' + name)
        new_c, new_h = module.transform(c.read_text(), h.read_text())
        c.write_text(new_c)
        h.write_text(new_h)
        shutil.copyfile(src / 'provider/report_impl.h', c.parent / 'report_impl.h')
        shutil.copyfile(src / 'provider/ingenic_aes_dma_report.h', a.kernel / 'include/linux/ingenic_aes_dma_report.h')
        return
    a.output.mkdir(parents=True, exist_ok=True)
    for directory in ('service', 'experiment'):
        for path in (src / directory).glob('*.h'):
            shutil.copyfile(path, a.output / path.name)
    for name in ('channel_policy.h', 'protocol_plan.h'):
        shutil.copyfile(src / name, a.output / name)
    shutil.copyfile(src / 'service/service.c', a.output / 'service.c')
    flags = ('EVENT_WAIT', 'WORD_CHECKS', 'COST_PROFILE', 'STREAMING_PAYLOAD',
             'CLEAN_REFRESH', 'INLINE_WORDS', 'SINGLE_OUTPUT_READ', 'CHECKED_RANGES', 'ACTIVE_SLOT')
    (a.output / 'Makefile').write_text(
        'obj-m += lumi_aes_dma4494_service.o\n'
        'lumi_aes_dma4494_service-y := service.o\n'
        'ccflags-y += -Wall -Werror -DLUMI_PROVIDER_REPORT ' +
        ' '.join('-DLUMI_DMA_' + name for name in flags) + '\n')
    subprocess.run(['make', '-C', str(a.kernel), 'O=' + str(a.build), 'ARCH=mips',
                    'CROSS_COMPILE=' + a.cross, 'M=' + str(a.output), 'modules'], check=True)
    module = a.output / 'lumi_aes_dma4494_service.ko'
    data = module.read_bytes()
    expected = b'vermagic=4.4.94-lumi-t33gs preempt mod_unload MIPS32_R2 32BIT'
    if expected not in data:
        raise ValueError('DMA module vermagic mismatch')
    exports = {line.split()[1] for line in (a.build / 'Module.symvers').read_text().splitlines()}
    undefined = subprocess.check_output([a.cross + 'nm', '-u', str(module)], text=True)
    missing = {line.split()[-1] for line in undefined.splitlines()} - exports
    if missing or 'ingenic_aes_dma_get_report' not in exports:
        raise ValueError('Missing kernel exports: ' + repr(missing))
    record = dict(status='PASS_HOST_BUILD_ONLY', module_name='lumi_aes_dma4494_service',
                  module_sha256=sha(module), board_proof=False, gateway_uid=200,
                  kernel_config_sha256=sha(a.build / '.config'),
                  module_source={path.name: sha(path) for path in a.output.iterdir()
                                 if path.suffix in ('.h', '.c') or path.name == 'Makefile'})
    (a.output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
