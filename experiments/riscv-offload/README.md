# T33gs RISC-V offload spike

Independent firmware worktree: `spike/t33-riscv-offload`, based on `dd5025e2`.
The worktree is `/home/hieunm/workspace/software/lumi-camera/lumi-ipc-firmware-riscv-offload`.
The main checkout's uncommitted changes are not included or modified. This fork
has no `scripts/worktree.sh` or Buildroot submodule, so the linked worktree was
created directly; this spike does not run the firmware Buildroot pipeline.

## Scope

Build the supplied MCU SDK in a private copy, inspect the current MCU owner and
memory layout on the owner's specified camera, and establish board evidence
before attempting a custom worker. The intended outcome is to identify a viable
CPU-offload path while preserving the running camera.

This directory contains a static MIPS read-only inspector, a resident-image
analyzer and an isolated SDK build target. It does not provide an MCU loader.
`inspect.c` only opens `/dev/mem` read-only and maps `PROT_READ`; its `write()`
is exclusively to stdout. The status command does not write mailbox registers,
change clocks or reset the MCU. `dump-resident` reads exactly the existing ISP
driver's 8 KiB allocation and refuses an unexpected boot vector.

Build artifacts and board captures are ignored under `artifacts/`. Vendor SDK
source, proprietary module/blob and any board credentials must stay out of Git.
No passwords are needed in these files.

## Reproduce host builds

Read the parent firmware Makefile and AGENTS.md before changing the build.
The local default toolchain paths are overridable:

```sh
make -C experiments/riscv-offload
make -C experiments/riscv-offload sdk
```

`MIPS_PREFIX` selects the static musl Linux compiler; `RISCV_PREFIX` selects the
bare-metal compiler. `SDK_SOURCE` points to the pristine extracted SDK. `sdk`
requires a fresh `artifacts/sdk-build` directory, copies the input, cleans the
copy, and builds `SENSOR_NUM=1 SENSOR0=sc4336p`. It never edits the input SDK.
Inspect the resulting ELF/bin; a successful build is not board acceptance.
The SDK's `__DATE__`/`__TIME__` strings mean different builds can have different
hashes without source changes.

Host validation passed for the SC4336P image: 942704 bytes, ELF32 little-endian
RV32IMC/ILP32 soft-float, xPack GCC 10.2.0, build exit 0. This run's bin SHA-256:
`54ae3a6d8f4d22414ea3fcdfafa1601e9be074b1a92b5c5bf382149488749d9e`.
Input archive SHA-256:
`34ee41fdd7b842d4cf89ce4f04acfc582a3ea1fe890dbf2d1bb69fad02f63f7a`.

## Board run: 2026-11-05

Target explicitly supplied by owner: `root@10.10.61.241`.

| Item | Observed value |
| --- | --- |
| Kernel | `4.4.94-lumi-t33gs`, PREEMPT |
| Machine | Lumi T33gs SK032T4 PRJ008 SC4336 |
| Boot ID | `fffa23e8-b575-423a-8e8a-a1abc8457bab` |
| RAM split | `mem=96M@0x0 rmem=32M@0x6000000` |
| MCU clock | `div_riscv` / `gate_riscv`: 475 MHz |
| CCU config / control | `0x0000003f` / `0x00000000` |
| Boot vector | `0x07ffe080` |
| Both mailbox words | zero at the sampled times |
| `zeratul_open` | 0 |
| Linux MCU owner | loaded `tx_isp_PRJ008`, owns controller resource and IRQ 12 |
| Current sensor | SC4336, 2560x1440 at 25 fps in ISP diagnostics |
| Active FrameSource | channel 1, scaled 1920x1080 |

The inspector built with `-Wall -Wextra -Werror -Wformat=2` and ran on camera
with exit status 0. The host and staged executable hashes match:
`6b33d16c7ebc6f2a764fe40ad416f5b43616b21b220d7b15b14dee66d1116091`.
It was staged only under `/tmp/lumi-riscv-offload-20261105`. Unsupported command
`reset` returned usage and exit status 2. No camera runtime binary, module,
startup file, U-Boot environment or flash partition was changed.

### Resident firmware and driver lifecycle

Downloaded the currently installed ISP module and inspected its actual symbol
table/disassembly, rather than assuming a local module matched it:

Module SHA-256:
`238e6c05cd7a019824debb1548354e97e6fa3dadeb82dab7cc50d67c082bf76f`.

- `riscv_vic` is 2264 bytes in `.data`, offset `0x1a24`.
- `tx_isp_riscv_probe` selects `rmem_base + rmem_size - 8192`, clears that region
  and copies the payload there. On this camera that is `0x07ffe000`.
- `tx_isp_riscv_run` configures reset/control/vector, clears mailbox/masks and
  timers, resumes the MCU and enables the Linux IRQ.
- The module has MCU mailbox functions for VIC prepare/stop and GPIO switching;
  it can require the MCU later, even when mailboxes are idle now.
- The resident payload implements these commands. The main routine reaches a
  `wfi` loop, with mailbox handling in the exception path. Idle mailboxes do not
  establish that Linux has relinquished the MCU.

Resident dump SHA-256:
`7f2451c84b86f6b46cbf9925b345be3d661caf05890b41143e075a164c2e9edd`.
Raw payload SHA-256:
`1d10a521c76216cc22132dd0a0f8b74cc10e6f3a03c34182e722889be02853f8`.

All payload bytes match after applying the exact startup relocation of 18 words
at offsets `0x890..0x8d8` by base `0x07ffe000`. The sampled BSS state words were
zero. The changed pointers are consistent with execution of the vendor startup;
this is not a custom firmware heartbeat or a new offload job result.

```sh
python3 experiments/riscv-offload/analyze-resident.py \
  experiments/riscv-offload/artifacts/active-riscv-vic.bin \
  experiments/riscv-offload/artifacts/resident-before.bin
```

### CPU sample

A 20-second sample read `/proc/stat` and the task stats for the running core
(PID 1245) and voice worker (PID 1285). Normalization uses delta thread
utime+stime over aggregate CPU jiffies on this single-CPU Linux system. Samples
are sequential, not atomic. There was no controlled acoustic fixture or A/B
offload run; names identify threads, not exclusive algorithm costs.

| Thread | Approximate share of one Linux CPU |
| --- | ---: |
| `ai-_ai_record_t` | 8.74% |
| `voice-inference` | 4.62% |
| `wake-pcm` | 0.65% |
| `ao-_ao_play_thr` | 0.15% |

This prioritizes measurement of audio capture/processing as well as wakeword.
Moving inference alone cannot be assumed to remove the audio capture/AEC work.
Do not describe 4.62% as a measured MCU saving: IPC overhead and MCU runtime
have not been implemented or measured.

### Final camera checks

The `/main` RTSP H.264 track delivered 4660 RTP packets over 12.029 seconds,
with 300 unique timestamps, 299 marker packets and no RTP sequence gaps. This
checks network media delivery; no decoder was run. The final `/health` remained
`ready`, and capture remained running in `/api/v1/media/status`.
The final boot ID was unchanged. The entire 8192-byte resident dump before and
after the inspection/measurement matched byte for byte; CCU/mailbox values also
matched. A static memory snapshot is not a live MCU heartbeat.

## Custom MCU execution remains pending

The new Zeratul SDK image is linked at `0x03b78000..0x04000000`, inside Linux RAM
on this camera. It cannot be loaded there. It is also a different firmware from
the resident VIC helper and is designed to hand off after boot convergence.

The current ISP driver still owns the MCU. A custom heartbeat/worker trial needs
a defined ownership handoff or compatible extension, reserved memory, cache/IPC
contract, and a verified restoration path. A host-connected `/dev/ttyACM0`
exists, but it has not been identified as this camera's recovery UART. The owner
was asked to identify the recovery port. No MCU firmware was loaded or stopped.

Next: verify recovery for this target; identify a source-compatible way to retain
the VIC mailbox contract or explicitly hand off the MCU; then run a bounded
MCU-owned heartbeat and fixture job before attempting live audio offload.
