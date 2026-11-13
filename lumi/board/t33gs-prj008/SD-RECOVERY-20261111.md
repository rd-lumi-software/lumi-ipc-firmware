# .241 SD power-loss recovery, 2026-11-11

Owner authorized erasure, formatting and recurrence repair. Target 10.10.61.241, T33gs/SC4336, CID02544d534133324724263000a7010300. No changes deployed to .171 in this follow-up. Private diagnostics: `/home/hieunm/workspace/builds/lumi-fullfw-241-20261111/sd-diagnostics`. No passwords, raw configuration, Wi-Fi key-bearing dmesg or recording payloads are committed here.

## Diagnosis

Captured metadata had identical FAT copies and two JSON directory entries referring to FREE first clusters. `archive/days/000000020768.json`, first cluster753249, matches native fat_get_cluster error i_pos1421767 exactly. One authoritative `index/entries` JSON similarly points to FREE cluster712600. An exhaustive metadata traversal found no malformed MP4 cluster chain; payload integrity was not established. Twelve orphan allocated clusters held JSON matching the damaged metadata. This is consistent with interrupted FAT directory replacement after power loss; it does not prove the electrical cause or card-controller health. No observed MMC CRC/timeout/block-I/O error establishes a separate physical failure.

Host fsck.fat4.2 against a sparse metadata-only copy, never flashed, reproduced both truncations. Automatic repair returned1; a separate no-write check returned0. Repair exit1 alone is ambiguous and is never treated as sufficient admission to writable recording.

Exactly one supported POST /api/v1/storage/format used observed CID, generation3 and confirm_erase:true. Formatting202 generation4 transitioned Ready generation5. No old recording rescue was requested. Runtime executables were immutable /lumi and no SD executable/FD/cwd was retained during format. Fresh recording/audio resumed.

## Accepted source and firmware

Recorder change `deac051677f625e5a814778ae43397cc337202dd`, task/ledgers `b92bf62`: writable bootstrap preserves malformed/empty index bytes using exclusive non-overwriting quarantine, syncs before source unlink, rebuilds derived recording shards from valid authoritative metadata and keeps I/O errors fatal. Read-only snapshots remain nonmutating; no reconstruction from MP4 is claimed. Harness run2026-11-11T14-17-37.146075902Z passed storage-library tests, fmt, diff and independent review. First run failed because host AAC build prerequisite was missing; it was built and the same task rerun with FDK_AAC_PREFIX. No model/config/gate changes. Report:2runs,1pass,0reviewfail,0ladderclimbs. Only main and retained Module diagrams worktrees remain.

Firmware board source adds S55lumi-storage and /lumi/bin/lumi-sd-check, and enables Buildroot dosfstools fsck.fat in both T33 defconfigs. Boot unmounts the selected card, checks FAT before S60 runtime, repairs only offline, and permits RW only after independent exit0 verification. Missing checker, failed/incomplete repair or timeout falls back to RO. Guard checks CID and device major/minor mount identity, rejects other mounts and live runtime. Orderly shutdown waits for recorder release then unmounts. Twelve fault-injection host tests pass; native BusyBox parsed comment-stripped helpers and native fsck loaded and checked a separate RAM fixture through /proc/self/fd/9. This is not native physical power-cut simulation.

Incremental build used the previous verified pinned glibc2.39 container, T33 hard-float uClibc recorder toolchain/SDK/AAC and existing hard-float musl Buildroot output. Private old post-build source needed an idempotence correction for its prior /opt/ingenic-t33/lib symlink; correction receipt retained privately. Live owner build refactor/UI edits were preserved. Runtime delta is exactly recorder plus sd-check helper; core, gateway, voice, image/FPS settings unchanged.

Rootfs SHA25633a49ee4a6067ab6b322160dcdd4424200e31dcc6a00be2d3bd343ee86b215e8,12566528bytes,16384bytes partition headroom. OTA SHA256896631583a59cc1df9793ea2f1914be5ea56e1cb6c33df7a544b1a3c5eb2657b. Correction after auditing the deployed updater: invocation `-z -r --archive=...` rewrote BOTH kernel and rootfs because `--archive` sets both update flags. The kernel bytes remained identical (AES-DMA kernel SHA256a5455f127fbf1614923a6aee64dc33eaf946d0d4d433b4d3b0892231112c50c2). The earlier rootfs-only description was incorrect; no rootfs-only flash is claimed. Native read-only image preflight,40-file manifest and flash-prefix readback all passed. Bootloader/environment checks and persistent firewall/S60 hashes remain unchanged. Full-flash backups are retained privately.

## Native recovery and playback

First updated boot178664e9-ca93-458f-86cb-54f91d2e501c checked FAT offline successfully, then resumed continuous300s/main/audio recording. Stopped supervisor/watch, confirmed runtime PIDs gone, injected two uniquely named empty/malformed test index files and one malformed synthetic day shard, synced and invoked S55stop. Verified card unmounted before reboot; no same-boot SDK reopen.

Second boot075bdff2-f4d9-4bd8-8160-7d230488e7cf checked FAT clean, quarantined all three injected JSONs and resumed real new audio/video recording. Original JSON paths absent; quarantine SHA256 values exactly match injected bytes. Healthy recordings remained in catalog. Only synthetic corruption was injected; no native FAT chain damage or physical power cut was performed. Both updated boots had no observed FAT/MMC error. Test evidence is native-recovery-verification.txt and native-recovery-reboot.txt.

Post-update direct Chromium/WebRTC playback PASS: 201 decoded frames,3 pause/seek/resume ACKs,0HTTP fallback. Unmodified Web Viewer PASS: 20 clip trong ngày · đã tải 24 bản ghi, decoded frames6→68, page errors[]. Sessions closed sequentially.

## Limits still observed

15s live sample25.158FPS, one0.198s freeze;30s repeat25.041FPS, one0.399s freeze,0lostpackets, first image880ms, steady CPU69.82%, MemAvailable56108KiB. Both browser transports/cleanup passed, but the stricter zero-freeze performance assertion FAILED; no zero-freeze claim. The initial sample's3844ms first image and70.46% whole-test CPU remain evidence rather than omitted outliers.

Native log also shows recording audio session1 pcm_header_read EAGAIN followed by session2 credit_write broken pipe; recorder rotated audio_unavailable/audio_available clips and resumed audio. These are a separate pre-existing-path audio continuity finding, not evidence of FAT corruption or a completed fix. A continuous uninterrupted300s segment has not been established by this validation. Physical power-cut endurance, full card capacity/controller health and electrical supply quality remain unverified. FAT is nontransactional; software cannot guarantee immunity to arbitrary sudden power removal. Boot recovery may discard irreparable metadata and current unwritten media; this fix restores service for the verified class of damage.
