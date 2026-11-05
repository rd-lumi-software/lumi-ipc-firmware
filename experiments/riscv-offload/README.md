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
analyzer, an isolated SDK build target and a bounded RAM-only MCU trial runner.
The trial runner actively borrows the ISP MCU and must not be run as a service.
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

## Read-only board run: 2026-11-05

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

## RAM-only MCU execution trial: 2026-11-05

Owner subsequently authorized implementation and identified `/dev/ttyACM0` as
this camera's UART. Login over that port returned the same kernel and boot ID
as SSH. UART remained connected throughout the trial; no reboot was needed.

### Implementation and bounds

`worker.S`, `worker.c`, `worker.ld` and `worker-abi.h` build a standalone RV32IMC
worker at the existing resident allocation. Its reset entry is `0x07ffe080`,
stack top is `0x07fff000`, and the 368-byte shared structure starts at
`0x07fff800`. Code is limited by the linker to the first 2048 bytes. The worker
uses no heap, Linux RAM, peripheral GPIO, microphone, network or ISP mailbox.
Machine interrupts are disabled for the short borrowed interval. This is not an
extension preserving the resident VIC mailbox service while it is running.

`trial.c` checks the exact expected resident snapshot, vector, control, PMA
configuration, IRQ masks and idle mailbox/BSS state before allowing writes.
It saves an exclusive-create rollback file and forks a guardian before stopping
the MCU. A child replaces only that 8 KiB RAM allocation, boots the worker,
checks heartbeat and submits 32 deterministic 160-sample PCM16 frames. Fixtures
include silence, alternating signed extrema, a ramp and a deterministic pattern.
The MIPS side compares exact 64-bit energy, peak magnitude and zero crossings.

The parent retains the original RAM image and restores it after the child exits,
fails or exceeds three seconds. Signals INT/TERM/HUP also request restoration.
It restarts VIC with the inspected vendor stop/start register sequence. These
guards do not provide serialization against the proprietary ISP driver, and
cannot recover a dead kernel or SIGKILL of the guardian; UART reboot is the
fallback. The test must stay bounded, with stable capture and verified recovery.

### Observed results

1. A deliberately altered expected snapshot was rejected with exit status 2 and
   the message `Preflight mismatch; no MCU writes performed`.
2. First worker image executed and published `magic=4c554d49`, but heartbeat
   based on `mcycle` did not advance during the 500 ms wait. It reported no trap.
   The exact counter configuration was not diagnosed. Guardian restored VIC and
   returned failure. During this run RTSP had zero sequence gaps but a maximum
   timestamp arrival gap of 515.256 ms; it was not free of video jitter.
3. The corrected worker used `CCU_TIME_L`, matching vendor
   `riscv_timer.c:get_mtime()`, and a register-only delay to bound shared-memory
   polling traffic. Heartbeat reached 2; all 32 jobs passed; guardian reported
   `VIC_RESTORED=1 trial_timeout=0 child_status=0`. Trial runner exit status was 0.
4. Compute timing was 5587..6231 CCU timer ticks per 160-sample frame, about
   11.76..13.12 microseconds at the observed 475 MHz. Output fields are named
   `min_cycles`/`max_cycles` for historical reasons; they are CCU timer deltas,
   not `mcycle` instruction counters. Timing excludes transport, polling and
   Linux-side fixture generation/verification. It is not a wake-word benchmark.
5. Concurrent RTSP in the successful run delivered 5806 video RTP packets,
   374 unique timestamps and 373 marker packets over 15.006 seconds, with zero
   sequence gaps and a 68.456 ms maximum timestamp arrival gap. This is a short
   delivery check, not video decoding, a controlled latency comparison or a soak.
6. Final API health was `ready`, capture remained running with epoch 1, and the
   boot ID stayed `fffa23e8-b575-423a-8e8a-a1abc8457bab`. UART also confirmed the
   unchanged boot ID. Control/vector/PMA/mailbox registers returned to the
   inspected values. The resident payload again matches the original relocated
   VIC image. Runtime stack bytes changed after restarting VIC, so the full
   8192-byte RAM dump is not expected to remain identical across this trial.

Successful worker SHA-256:
`652123b4a5bd2463332b87ef056592d1b587cb67461dcd2adefcf6ab2278ca78`.
Trial runner SHA-256:
`78a502b9f6b7fe244779e4cf878f8b457ff383bae902026c64f812633ae2572f`.
First failed worker SHA-256:
`00dd47b04e641fe1b369da8dd5b15636087d5beb168ab9f62d7f7200982d4393`.

Evidence is in `artifacts/trial01.log`, `trial02.log`, `trial-negative.log`,
`rtsp-during-trial.json`, `rtsp-trial02.json`, `posttrial02-analysis.json`,
`posttrial02-state.txt`, API JSONs and `uart-trial-20261105.log`.
On-device copies and rollback images are under `/tmp/lumi-riscv-offload-20261105`.
No persistent startup, flash, environment or application binary was replaced.
The camera is currently running original VIC, not the experimental worker.

### Reproduction boundaries

Build with `make -C experiments/riscv-offload`. Verify the correct UART, current
board/boot/module/layout and fresh resident snapshot first; an old snapshot can
be rejected after VIC has restarted. Inspect the loaded image with
`analyze-resident.py` and preserve the backup on the host. Stage the worker,
runner and exact snapshot in a new RAM directory. The runner invocation is:

```sh
./t33-mcu-trial worker.bin expected-resident.bin new-rollback.bin
```

This command actively replaces MCU RAM temporarily. Keep UART available, run a
concurrent media check, collect exit status/logs, and verify VIC restoration and
camera health afterward. Do not put it in init, a supervisor or a cron job.

## Live audio offload remains unimplemented

The new Zeratul SDK image is linked at `0x03b78000..0x04000000`, inside Linux RAM
on this camera. It cannot be loaded there. It is also a different firmware from
the resident VIC helper and is designed to hand off after boot convergence.

The bounded trial proves custom RISC-V execution, shared-memory visibility for
this layout, correct fixture computation and short-run restoration. It does not
establish a permanent ownership handoff, a general cache-coherency contract,
concurrent VIC service, live PCM delivery, frontend/inference or CPU savings.

Next: retain the VIC mailbox contract or add a supported driver handoff, reserve
worker memory independently, and connect PCM from the existing Linux audio owner.
Only then measure frontend/model parity, end-to-end deadlines and actual MIPS CPU
reduction under concurrent video/audio. The earlier 4.62% inference sample is a
baseline, not a saving measured by these fixture jobs.
