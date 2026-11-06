# T33gs wake-word RISC-V firmware

This directory contains the wake-only MCU runtime used with the streamer's
`riscv-wake` backend and the sibling Linux `lumi_riscv_mem` module. Linux keeps
capture, AEC, PCM distribution, wake gating, thresholds and Luvox. The MCU runs
the integer frontend and OK Lumi model, returning raw scores. Opus stays on
Linux; ISP/3A, motion and OSD retain their existing Linux/hardware paths.

## Build

Build `liboklumi-riscv.a` first with `scripts/build_wakeword_riscv.sh riscv` in
the streamer checkout. That script pins the model and TFLM source. Then:

```sh
make -C lumi/board/t33gs-prj008/riscv-wakeword \
  STREAMER_SOURCE=/path/to/lumi-ipc-streamer \
  RISCV_PREFIX=/path/to/bin/riscv-none-embed-
```

The default streamer path selects the adjacent `lumi-ipc-streamer` checkout. `WAKE_ARCHIVE` and `BUILD_DIR` can be overridden. The compiler must
support RV32IMC/ILP32 and newlib `nosys.specs`. No vendor ISP archive is linked.
No build command contacts or alters a camera.

The build independently links at three addresses and proves that relocating the
first image produces exactly the other two. `build/wake.rvpack` carries image
and relocation-table SHA256s. The Linux owner validates the pack and relocates
it into its actual owned allocation; the three link addresses are fixtures,
not fixed camera memory addresses. Build output is ignored and is not a release.

## Runtime contract

`wake-abi.h` is the unchanged752-byte ABI3 shared mailbox. Commands0–3 process
one or two160-sample steps, with optional reset before processing. Command4
disables interrupts, acknowledges completion and returns cooperatively to
resident VIC main; reset startup must not erase its live BSS. Opus/3A commands
and buffers are absent.

The firmware uses a one-MiB allocation supplied by the Linux owner, with the last
4KiB shared and64KiB reserved for stack below it. The linker bounds code, data,
BSS and heap; `_sbrk` refuses allocation beyond that heap. The caller must hold
the sole MCU lease and serialize requests. Manual/Luvox/talkback wake pauses
are controlled by Linux and do not create a second MCU owner.

`coexist.S` depends on a specifically inspected2264-byte resident VIC payload
at0x07ffe000. Its timer entry is resident+0x65a and cooperative return is
resident+0x7ba; these are pinned binary entry points, not a general vendor API.
The Linux module validates the resident code, controller/PMA/mailbox state and
ISP lifetime reference before starting this worker. A different kernel, ISP
module, resident firmware or suspend/lifecycle behavior needs qualification.
Do not load or unload competing firmware or use direct MMIO diagnostics while
the normal owner is active.

## Owner wrappers

`voice-owner.sh` selects the existing voice worker's RISC-V backend and keeps
the normal supervisor topology. Its directory must contain `wake.rvpack`,
`lumi_riscv_mem.ko` and `ipc-voice-worker.riscv`. It loads the module only when
the device is absent, clears inherited diagnostic selectors and execs the
normal worker. No separate guardian or audio process is introduced.

`boot-owner-link.sh` is an opt-in hook after the base runtime creates its RAM
launch directory. It requires `ENABLED` containing `owned-riscv-abi3` and a
valid `runtime.sha256` manifest before selecting `voice-owner.sh`. These
wrappers are source files only; this directory does not add an init hook or
activate a release. Deployment and a verified rollback remain separate steps.

The cleanup build reproduced the previously qualified wake-only pack SHA256
`aee06a5e7362fbff7eb5632c11ce58fb06a7aacbdcd2c0844718ef364d80e32e`
and passed relocation comparison against two independent links. This is a
host build check, not a new deployment or board test. The working camera keeps
its existing release; the operational choice is wake-word on RISC-V only.
