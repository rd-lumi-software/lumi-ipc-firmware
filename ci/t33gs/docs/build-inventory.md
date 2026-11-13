# T33gs PRJ008 build inventory

## Dependency graph

Buildroot manages the PRJ008 components alongside userspace:

```text
host-uboot-tools + host-kmod → lumi-t33-platform → lumi-t33-runtime
                                     ↓                 ↓
                                 modules           /lumi files
lumi-t33-uboot → u-boot-with-spl.bin
               kernel + rootfs + U-Boot → board post-image → full NOR + OTA
```

The platform package keeps SDK kernel preparation and external modules together:
its sources require checked preimage patches and the vendor GCC 5.4 compiler,
while Buildroot's ordinary Linux package uses TARGET_CROSS. This integration
uses the existing component recipe, rather than changing the userspace compiler
or moving source patches into the firmware repository. Buildroot owns package
stamps, dependency order, target module installation and image installation.
The SDK recipe drops Buildroot's exported `UIMAGE_NAME`, so the source kernel
uses `Linux-4.4.94-lumi-t33gs`, the identity accepted by the OTA updater.
The kernel verifier rejects another name even when its image CRC is valid.

Runtime dependencies remain built by the source repository's recipes (Opus,
relay, streamer, recorder, snapshot, optional voice). Mutable copies live inside
its package build directory; source inputs are the recorded workspace snapshots.
Separating each upstream dependency into an independent package is a future
refinement, not a claim made by this integration.
Its recipe also clears Buildroot's `GIT_DIR=.` before invoking source-owned
Git revision/ABI checks against the isolated checkouts.

## Installed files and service ownership

| Input | Installed files | Owner/finalizer |
| --- | --- | --- |
| `general/overlay` | Base OpenIPC shell/init/network files | Shared overlay; existing rootfs hook |
| `lumi/overlay` | Lumi identity, account presets, clock/hostname helpers | Product overlay + Lumi post-build |
| Board overlay | PRJ008 camera profile, GPIO/AES helpers, network/firewall/SSH and runtime init scripts, fw_env config | PRJ008 overlay |
| SDK assets | Vendor media libraries, sensor tuning, Wi-Fi firmware | Platform package install-target |
| `lumi-t33-platform` | Matched kernel modules and kernel verification/image files | Package install-target/install-images |
| `lumi-t33-runtime` | `/lumi/bin` camera/relay/voice/recording binaries, licenses, certificate | Package install-target |
| PRJ008 finalizer | UID/GID, SDK loader link, AES client, pruning, hardware.env, manifest/updater | Board post-build; shared runtime finalizer |
| PRJ008 post-image | Full image, OTA, checksums, build/runtime/kernel/overlay metadata | Board post-image |

`overlay-overrides.json` records permitted overlay replacement pairs; a new
collision fails the board finalizer. The resulting overlay inventory accompanies
the artifacts. Package/generated-file changes still require rootfs comparison:
overlay inventory alone does not prove the final file content.

The transition keeps existing intentional pruning in the runtime finalizer
(ipctool/ipcinfo, WireGuard/vendor init, old runtime helpers, unused xtables
plugins and extutils diagnostic branches). These are explicit compatibility
steps, not evidence that every hook mutation has already become a package.

## Init and restart boundaries

`rcS` executes `S??* start` in order. PRJ008's board/network/firewall/SSH setup
precedes `S60lumi-streamer`, then `S61lumi-streamer-watch` starts monitoring.
S60 starts the compact supervisor and waits for readiness before starting relay
when provisioned. The supervisor owns runtime child lifecycles; S61 handles
network/relay readiness and only attempts initial runtime start when the start
latch permits it. It does not reopen IMP on Wi-Fi loss. This migration preserves
these boundaries and the OTA order (stop watcher before runtime).

The original legacy rootfs exceeded its slot by 8 KiB for the captured source
set. The first unified rootfs fit because package installation precedes normal
Buildroot stripping, unlike the legacy late-copy hook. All 20 SDK library files
retained identical allocated sections after stripping; no runtime library code
was changed. Experiments with module debugger cleanup and SquashFS tail/export
options remain local experiments and are not part of the implementation.

## Board layout

`lumi/board/t33gs-prj008/layout.json` is the firmware-side source of RAM/flash
layout and hardware.env values. The NOR packer and updater consume it. Board
checks compare kernel CMA settings, fw_env.config and the PRJ008 U-Boot fallback
strings plus the compiled U-Boot environment sizes/offset and kernel read command.
The resolved layout is included in the build manifest. U-Boot remains in its
source repository; mismatches fail rather than silently rewriting another repo.

Keep mem96/rmem32/CMA16 during migration. A change to these values needs a
separate board measurement/review; passing layout consistency does not prove a
new allocation is stable.

## Validation records

Validation originally used `/home/hieunm/workspace/builds/lumi-unified-t33gs/`.
After validation, the temporary workspaces were cleaned and the final workspace
was moved to firmware `output/t33gs-local-20261111/`, retaining artifacts and
validation metadata. Its intermediate build/source copies were removed; use a
new full build to compile again. New local builds create their workspace under
firmware `output/t33gs-local-XXXXXX/` and keep artifacts there without exporting
copies to another directory.

Host fixture tests cover full image partition offsets, OTA members/checksums,
SDK tampering/escape, updater layout checks, bad RAM/flash consumers and unreviewed
overlay collisions. Buildroot configuration and show-info must select all three
packages with runtime depending on the platform package.

The 2026-11-11 host run passed 12 packaging/layout/install/init tests and the local
snapshot tests. Comparing the original and layout-driven packers on the same
fixture produced byte-identical 16 MiB full images (SHA-256
`b49274016c0a0ae66b24dea8796344eaeacb2f8936a18050562f92c7253a0f88`)
and byte-identical generated updaters. This is fixture evidence only.
Buildroot show-info selected the platform, runtime and U-Boot packages; a
separate configuration run with voice disabled left its symbol unset. The
runtime installation fixtures covered both voice selections and identity-key
rejection. CI selector self-test passed (99 boards, 136 packages, 56 cases).

The source-snapshot build completed full NOR/OTA with voice enabled, then a
platform package rebuild and `repack -j2` completed through the public Make
interface. The final image is 16,777,216 bytes, its kernel 2,085,120 bytes and
rootfs 12,550,144 bytes (32 KiB below its slot limit). Checksums, uImage identity,
environment CRC, partition placement and OTA member MD5s passed. The rootfs
extracted from the actual SquashFS passed the Lumi verifier. The current board
defconfig also enables FAT checking tools, absent from the older baseline
snapshot; compare package selections before calling the outputs equivalent.

Kernel configs and prepared SDK source trees matched. Module ABI verification
passed for all nine modules. Binary hashes differ where source paths/build
metadata are embedded; this is not a byte-identical full-build parity claim.
Twenty SDK library files retained identical allocated sections; four runtime
shell scripts retained identical non-comment commands. The original baseline
failed its final size gate, so it is not recorded as a successful full build.

Runtime rebuild with voice disabled completed. The resulting full image and
OTA passed the same artifact checks; its rootfs is 11,223,040 bytes and the
extracted image passed the Lumi verifier without `ipc-voice-worker`. The board
finalizer removes stale voice files when disabled, and S60 skips provisioned
voice configuration when that worker is absent. A host init regression exercises
this case. Changing the voice selection in an existing workspace requires a
runtime package rebuild followed by `br-all`, as tested here.

Hardware/memory qualification and an actual GitHub Actions runner build remain
pending. No camera has been flashed by this migration work.

For board memory qualification, record the firmware manifest, active features,
stream settings, duration and concurrent workload. Capture `/proc/meminfo`
(MemAvailable and CmaTotal/CmaFree), `/proc/buddyinfo`, dmesg/logread, allocation
failures/OOM/restarts and stream/record/voice outcome at idle, load and after
recovery. Do not infer rmem headroom from MemAvailable alone; inspect ISP/vendor
allocation failures too. Hardware access and an approved deployment are required
before recording these results.
