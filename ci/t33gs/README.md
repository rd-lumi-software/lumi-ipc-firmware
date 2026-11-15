# CI/CD firmware Lumi T33gs

Pipeline nằm trong repo **lumi-ipc-firmware**, không phải thư mục workspace
`lumi-camera` (thư mục này không có `.git`). Target hiện tại là **T33gs PRJ008,
SC4336, NOR 16 MiB, kernel 4.4.94**. Không dùng preset T33 kernel 3.10 đã nghỉ.
T23 cần pipeline riêng theo toolchain, runtime và layout của T23.

## Luồng build

1. Kiểm tra SHA commit của các repo và SHA-256 của bộ SDK.
2. Clone firmware cùng streamer, linux patches/drivers, U-Boot, relay, TFLM,
   Opus và Buildroot vào workspace mới. Không lấy binary từ `output/` cũ.
3. Chọn defconfig board; Buildroot build kernel, ISP/sensor/audio, motor,
   TNPU, Wi-Fi và dependency index qua package platform.
4. Buildroot build U-Boot và package runtime gồm Opus, voice (tùy chọn),
   relay, streamer/gateway, recorder và snapshot.
5. Build userspace, cài runtime và module cùng bản kernel;
   kiểm tra ELF/ABI, manifest và cấu hình rootfs.
6. Đóng gói full NOR, OTA, manifest nguồn và checksum. Upload artifact; có thể
   tạo **draft release**. Chưa có bước tự động flash camera.

`sources.json` khai báo các repo. TFLM, Opus và Buildroot đã pin trong file;
các repo Lumi được pin bằng repository variables để chọn bộ phiên bản tương thích.
Mỗi SHA phải đủ 40 ký tự hex, không nhận `main`, branch hay tag di động.
`build-manifest.json` ghi lại commit đã dùng và hash bộ SDK.
Các dependency mà script streamer tải như FFmpeg, zlib, JPEG và FDK-AAC dùng
pin của chính commit streamer đó. Cargo dùng lockfile.

Opus cho gateway T33 dùng fixed-point, CMake Release (`-O3`) và
`-march=mips32 -mtune=mips32` ở cả recipe Buildroot và legacy. Phép đo cùng
source trên T33gs xác nhận giảm CPU encode và giữ nguyên bitstream trên các
fixture đã kiểm. Không bật DSPR2 assembly hoặc fast-math, không đổi bitrate,
complexity hay frame duration. Rust gateway vẫn giữ profile tối ưu kích thước;
đây là lựa chọn build riêng cho thư viện Opus, không phải `-O3` toàn firmware.

## Thiết lập GitHub Actions

Đăng ký runner Linux x86-64 có Docker, Python >= 3.10, Git và jq, với label
`lumi-firmware`. Tài khoản runner phải chạy được Docker và đọc bộ SDK.
Nên bắt đầu với 4 CPU, 16 GiB RAM, ít nhất 60 GiB đĩa trống; điều chỉnh sau
khi đo lần build đầu. Container được build từ `Dockerfile` trong thư mục này.

Tạo **Settings → Secrets and variables → Actions → Variables**:

| Variable | Giá trị |
| --- | --- |
| `LUMI_FIRMWARE_CI` | `true` để bật workflow của Lumi |
| `LUMI_STREAMER_REPOSITORY` | `rd-lumi-software/lumi-ipc-streamer` |
| `LUMI_STREAMER_COMMIT` | SHA commit streamer đã push |
| `LUMI_LINUX_REPOSITORY` | `hieunm599/lumi-ipc-linux` hoặc fork được dùng |
| `LUMI_LINUX_COMMIT` | SHA commit linux đã push |
| `LUMI_UBOOT_REPOSITORY` | `hieunm599/lumi-u-boot-t33` hoặc fork được dùng |
| `LUMI_UBOOT_COMMIT` | SHA commit U-Boot đã push |
| `LUMI_RELAY_COMMIT` | SHA commit `rd-lumi/iot-relay-cloud` đã push |
| `LUMI_T33GS_INPUTS_DIR` | Đường dẫn tuyệt đối bộ SDK trên runner, ví dụ `/opt/lumi-ci/t33gs` |
| `LUMI_T33GS_INPUTS_SHA256` | SHA-256 của file `SHA256SUMS` trong bộ SDK |
| `LUMI_BUILD_JOBS` | Tùy chọn, mặc định `4` |

Nếu có repo private, tạo secret `LUMI_SOURCE_READ_TOKEN` có quyền đọc contents
các repo đó. Token chỉ truyền vào bước fetch, không lưu vào git config hay
đưa vào container build. Token mặc định của Actions không đọc được mọi repo private khác.

Commit/push toàn bộ thay đổi CI này trước khi chạy: script fetch cố ý từ chối
firmware checkout có thay đổi chưa commit. Repo nguồn phải đã push các commit đã pin.

Workflow **Lumi CI checks** chạy test đóng gói và parse shell khi push/PR thay đổi CI.
Workflow **Lumi T33gs firmware** chạy bằng **Actions → Run workflow** hoặc push tag
`lumi-t33gs-v*`. Tag luôn build voice; chạy thủ công có thể bỏ voice.
Chọn `draft_release=true` để xuất draft release; tag cũng xuất draft release.
Workflow cần có trên default branch để hiện nút Run workflow.
Xem [GitHub: chạy thủ công](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
và [runner labels](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow).

## Bộ đầu vào SDK

SDK/toolchain và tuning độc quyền không nằm trong Git. Chuẩn bị một lần trên
runner từ bản SDK đã được phép dùng, theo cấu trúc dưới đây. Không đưa rootfs,
runtime đã build, mật khẩu Wi-Fi, relay key hay voice credentials vào bộ này.

```text
/opt/lumi-ci/t33gs/
  sdk/kernel-4.4.94.7z
  sdk/drivers.7z
  uclibc/bin/mips-linux-uclibc-gcc
  uclibc/...                       # toàn bộ GCC5.4/uClibc toolchain
  musl/bin/mipsel-linux-muslsf-gcc
  musl/...                         # toàn bộ static soft-float musl toolchain
  riscv/bin/riscv-none-embed-gcc   # RV32IMC/ILP32 newlib toolchain (voice)
  riscv/...
  imp/include/imp/imp_isp.h
  imp/include/...                  # IMP headers tương thích libimp
  board/opt/ingenic-t33/lib/...     # libimp, alog, sysutils, uClibc và loader
  board/etc/sensor/sc4336-PRJ008-day.bin
  board/etc/sensor/sc4336-PRJ008-night.bin
  board/lib/firmware/...           # AIC8800D80 firmware, gồm các đường dẫn module yêu cầu
  aic8800.tar.gz                   # source archive revision dưới đây
  tunnel.cert                     # public relay certificate, không có private key
  PROVENANCE.md                    # phiên bản/nguồn/license của từng đầu vào
  SHA256SUMS
```

Toolchain uClibc phải báo đúng:
`mips-linux-uclibc-gcc (Ingenic r3.3.7.mxu2.cve2-gcc540 2025.07-17) 5.4.0`.
Source AIC8800 là archive của `OpenIPC/aic8800`, commit
`0e218ed686ee04a3006bb142ca70450dfa72f4d2`, có một thư mục gốc bên trong tar.
Vendor libraries phải là ELF/symlink thực, không phải file placeholder `XSym`.
Giữ symlink tương đối và nằm trong bộ SDK; link ra ngoài bị từ chối.
Các phần khác của `board/` không được phép: init scripts và executable của Lumi
đều phải đến từ source và bước build.

Tạo checksum sau khi đã chốt nội dung (đường dẫn bên dưới không chứa newline):

```sh
cd /opt/lumi-ci/t33gs
find . -xtype f ! -path ./SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
sha256sum SHA256SUMS
```

Gán hash cuối cho `LUMI_T33GS_INPUTS_SHA256`. Khi thay SDK, thay hash tương ứng.
Manifest phải liệt kê mọi regular file và symlink tới file; preflight kiểm tra từng file trước khi
chạy compiler. Bộ SDK được mount read-only vào container.

## Build từ source local đang phát triển

Dùng cấu hình riêng khi muốn build các checkout có sẵn, kể cả thay đổi chưa
commit. Từ repo firmware:

```sh
cp ci/t33gs/local.example.mk ci/t33gs/local.mk
# Sửa các biến T33GS_* trong local.mk thành đường dẫn tuyệt đối trên máy.
make t33gs-plan
make BOARD=lumi_t33gs_prj008_sc4336 -j4
```

`local.mk` được git-ignore. File cấu hình trên máy hiện tại đã được điền bằng
đường dẫn tuyệt đối thực tế; không cần copy lại file mẫu. Khi thiết lập máy khác, copy
`local.example.mk` và sửa đường dẫn. Host local cần Bash, GNU Make/coreutils,
Git, rsync, jq, Python >= 3.10 và Docker.

Lệnh build chụp các file tracked và untracked chưa bị git-ignore, gồm thay đổi
chưa commit và file đã xóa, vào workspace mới dưới `output/t33gs-local-XXXXXX/`
trong repo firmware. Loại bỏ `target/`,
`output/`, `artifacts/`, object, kernel module và image đã build. Các compiler/build script chạy trên
bản chụp, nên checkout gốc không bị `make distclean` hay các bước build sửa đổi.
Không sửa source trong lúc đang tạo bản chụp. Submodule và symlink source trỏ
ra ngoài repo bị từ chối; dùng checkout nguồn đầy đủ và symlink tương đối. Symlink trong rootfs overlay giữ nguyên đích trên camera.

Các biến `T33GS_<TÊN>_SRC` đều trỏ source local, không tự fetch repo thay thế:

| Mục | Thư mục nguồn |
| --- | --- |
| `firmware`, `streamer`, `linux`, `uboot`, `relay` | Các repo Lumi trên máy |
| `tflm`, `opus`, `buildroot` | Source dependency đã có trên máy |
| `kernel` | Source kernel 4.4.94 đã giải nén, có `Makefile` |
| `drivers` | Source vendor drivers, có `isp/tx-isp`, `sensors/sc4336`, `audio/oss3` |
| `aic` | Source driver AIC8800, có `Makefile` và `aic8800_fdrv` |

Kernel, driver và source dependency đã giải nén không bắt buộc có Git; riêng
firmware, streamer, linux và TFLM cần Git theo yêu cầu của script build hiện tại.
TFLM vẫn phải sạch và đúng commit mà script voice yêu cầu. Dependency con của
Cargo/Buildroot/FFmpeg vẫn có thể được tải khi build, nên đây không phải chế độ
offline hoàn toàn.

`T33GS_UCLIBC_TOOLCHAIN` và `T33GS_MUSL_TOOLCHAIN` trỏ trực tiếp tới toolchain đã cài.
Các biến `T33GS_IMP_HEADERS`, `T33GS_VENDOR_LIBRARIES`, `T33GS_SENSOR_TUNING`,
`T33GS_WIFI_FIRMWARE`, `T33GS_RELAY_CERTIFICATE` chỉ nhận IMP headers, thư viện
SDK, tuning sensor, firmware Wi-Fi và public relay certificate. Không nhận rootfs, kernel image, runtime package
hoặc artifact của lần build trước. `libimp`, archive ISP
`libPRJ008-firmware-4494-540.a` và dữ liệu tuning/Wi-Fi là đầu vào vendor không
có đầy đủ source trong các repo này; chúng không được mô tả là đã biên dịch lại.

Không cần chuẩn bị bộ `/opt/lumi-ci/t33gs` hoặc nhập `inputs_sha256` cho local.
Script tự chuẩn bị đầu vào từ các đường dẫn trên và ghi checksum. Trong thư mục
build mới, Buildroot quản lý các package kernel/modules, U-Boot, runtime và
userspace, rồi post-image hook đóng full firmware và OTA.
Kernel được `mrproper` trước khi cấu hình; không tái sử dụng
object/Cargo target/rootfs có sẵn.

Các tùy chọn:

```sh
# Chỉ kiểm tra cấu hình, không copy hay build.
make t33gs-plan

# Chỉ chuẩn bị source, chưa chạy Docker/build.
make t33gs-prepare T33GS_WORKSPACE=/tmp/lumi-local-001

# Build đầy đủ vào thư mục mới do mình chọn.
make t33gs-full T33GS_WORKSPACE=/tmp/lumi-local-002
```

`make t33gs-help` liệt kê các target và biến cấu hình. Dùng
`T33GS_LOCAL_CONFIG=/đường/dẫn/local.mk` để chọn cấu hình khác.
Makefile gọi `local.sh` để chụp source, chuẩn bị SDK và chạy Docker; `fetch-sources.sh`
fetch các SHA đã pin trong CI. jq/coreutils xử lý metadata và checksum. Python
vẫn được dùng cho kiểm tra SDK/ELF/manifest, sửa định dạng link SDK và đóng gói
image. `make BOARD=lumi_t33gs_prj008_sc4336 -j4` tạo cả full firmware và OTA,
không nạp lên camera. Các board khác giữ cấu hình và luồng build hiện tại.

Biến `T33GS_VOICE=0|1` bật/tắt voice worker, `T33GS_JOBS` giới hạn số job,
`T33GS_BUILDER_IMAGE` đặt tên Docker builder. Có thể truyền các biến này trên
lệnh make. Mỗi lần dùng workspace mới. Kết quả nằm trong `artifacts/`
của workspace và có cùng full image/OTA/checksum như CI. `sources.json` cùng
`build-manifest.json` ghi HEAD/trạng thái dirty cho Git checkout và SHA-256
bản chụp source; `BUILD_ID` có tiền tố `lumi-t33gs-local-` để nhận diện bản phát triển.

Firmware ở nguyên trong `output/t33gs-local-XXXXXX/artifacts/`; script không
copy kết quả sang `/home/hieunm/workspace/builds` hay thư mục export khác.
`output/` bị loại khỏi snapshot nên workspace nằm ở đây không bị chụp ngược
vào source. Có thể chọn vị trí khác bằng `T33GS_WORKSPACE`.

## Build qua cấu hình board

```sh
make BOARD=lumi_t33gs_prj008_sc4336 -j4
```

Luồng này dùng defconfig board và các package `lumi-t33-platform`,
`lumi-t33-uboot`, `lumi-t33-runtime`; Buildroot quản lý dependency/stamp và
post-image hook tạo full NOR/OTA. `-j4` được chuyển thành giới hạn job bên trong
container và `BR2_JLEVEL`; điều phối package tuần tự để tránh nhân số job giữa
các tầng. Các board cũ giữ luồng build hiện tại.

`t33gs-full` là tên gọi tương thích của luồng mới. `t33gs-legacy-full` giữ luồng
trước chuyển đổi để đối chiếu, mỗi lần vẫn dùng workspace mới. Không bỏ luồng
legacy trước khi có kết quả đối chiếu build và kiểm chứng board cần thiết.

Rebuild một package trong workspace unified đã có:

```sh
make BOARD=lumi_t33gs_prj008_sc4336 br-lumi-t33-runtime-rebuild \
  T33GS_WORKSPACE=/absolute/path/to/unified-workspace
```

Lệnh rebuild dùng source snapshot đã ghi trong workspace. Để lấy thay đổi mới
ở checkout gốc, chạy full build với workspace mới. Sau package rebuild, chạy
`br-all` trong cùng workspace để tạo lại rootfs/full/OTA. Không chỉnh source
snapshot mà giữ nguyên manifest cũ.

Khi đổi `T33GS_VOICE` trên workspace đã build, truyền cùng giá trị cho cả
`br-lumi-t33-runtime-rebuild` và `br-all`. Full build vào workspace mới chọn
voice ngay từ defconfig.

Xem [dependency và nguồn file/service](docs/build-inventory.md) và
[kế hoạch, tiêu chí kiểm chứng](docs/unified-build-plan.md). Layout chuẩn của
board là `lumi/board/t33gs-prj008/layout.json`; firmware kiểm tra chéo cấu hình
U-Boot, kernel và fw_env trước khi đóng gói. Giữ nguyên mem96/rmem32/CMA16.

## Công cụ build và kiểm tra

- `targets.mk` cung cấp các target Make; `local.mk` giữ cấu hình riêng của máy.
- `local.sh`, `fetch-sources.sh` chuẩn bị source; `build-board.sh` thiết lập
  môi trường để Make/Buildroot điều phối build. `build.sh` chỉ giữ cho đối chiếu legacy.
- `firmware.py` cung cấp kiểm tra SDK, layout/overlay, sinh cấu hình và đóng gói;
  các lệnh kiểm tra/đóng gói chính là:
  `check-inputs`, `install-updater`, `package`. Các lệnh này chỉ dùng thư viện
  chuẩn Python, không cần cài package bằng pip.
- `contrib/pack-t33gs-nor16.py` là bộ ghép NOR dùng chung với luồng post-image;
  `verify-t33gs-k4494.py` và `verify-t33-lumi-image.py` kiểm tra kernel/rootfs.
  Pipeline dùng lại các công cụ này thay vì chép thêm logic binary/layout.
- `test_pipeline.py` chỉ phục vụ kiểm thử trên máy build.

Dùng `make t33gs-test` để chạy test snapshot source, SHA nguồn, SDK, updater,
full image và OTA; không cần SDK thực, Docker hoặc camera. Công cụ Python chạy
trên host/container build; các script này không được cài vào firmware.

## Build local bằng source đã pin như CI

Từ checkout sạch của firmware, export các biến repo/commit giống bảng trên,
`LUMI_INPUTS` trỏ bộ SDK và `LUMI_T33GS_INPUTS_SHA256` trỏ hash manifest:

```sh
bash ci/t33gs/fetch-sources.sh --workspace /tmp/lumi-build-001 --plan
bash ci/t33gs/fetch-sources.sh --workspace /tmp/lumi-build-001
docker build -t lumi-t33gs-builder ci/t33gs
docker run --rm --user "$(id -u):$(id -g)" \
  --env HOME=/work/build-home --env LUMI_INPUTS=/inputs \
  --env LUMI_T33GS_INPUTS_SHA256 --env LUMI_BUILD_VOICE=1 \
  --mount type=bind,src=/tmp/lumi-build-001,dst=/work \
  --mount "type=bind,src=$LUMI_INPUTS,dst=/inputs,readonly" \
  lumi-t33gs-builder bash /work/lumi-ipc-firmware/ci/t33gs/build-board.sh
```

Mỗi lần dùng workspace mới; chỉ source đã commit được clone. Không cần các
checkout sibling hay `output/` có sẵn trên máy local.

## Artifact và OTA

| Artifact | Mục đích |
| --- | --- |
| `lumi-t33gs-full.bin` | Full flash 16 MiB, gồm bootloader và môi trường khởi tạo |
| `lumi-t33gs-ota.tgz` | Kernel + rootfs, tên SoC `t33` và MD5 theo `sysupgrade` |
| `uImage.t33`, `rootfs.squashfs.t33` | Image riêng từng phân vùng |
| `SHA256SUMS` | Kiểm tra toàn bộ artifact sau khi tải |
| `build-manifest.json` | Commit nguồn, hash SDK, kích thước và layout |
| `runtime-manifest.json`, `kernel-verification.json`, `kernel.config` | Bằng chứng kiểm tra build |
| `lumi-sysupgrade` | Updater T33gs dùng identity/layout Lumi, giữ bước flash trong RAM |

Full image dùng layout: boot 256 KiB, kernel 2560 KiB, rootfs 12288 KiB,
rootfs_data 1248 KiB, env 32 KiB. Full flashing khởi tạo lại cấu hình thiết bị.
OTA dành cho camera **đã dùng đúng layout này**; chuyển từ layout cũ cần quy trình
migration/full flash riêng. OTA không ghi U-Boot, env hay xóa rootfs_data.

Trước OTA, kiểm tra camera đã có cả `/overlay/lumi-security/firewall4.rules`
và `/overlay/lumi-security/firewall6.rules`: file thường, không phải symlink,
không rỗng, owner root và mode `0600`. Policy phải cho phép máy quản trị truy cập
SSH và các cổng API/media cần dùng. Camera chạy bản cũ có thể chưa có các file này;
phải provision policy phù hợp trước khi nâng cấp. Firmware mới mặc định chặn
kết nối vào khi thiếu policy, kể cả SSH/API, dù camera vẫn ping được. Không OTA
máy chưa provision rồi trông chờ SSH để sửa sau reboot; cần UART để khôi phục.

Sau khi đã kiểm chứng bản build trên board và xác nhận `/proc/mtd` đúng layout,
tải và kiểm tra `SHA256SUMS` trên máy triển khai, copy OTA cùng `lumi-sysupgrade`
vào `/tmp` camera rồi dùng:

```sh
chmod 755 /tmp/lumi-sysupgrade
/tmp/lumi-sysupgrade -z -k -r --archive=/tmp/lumi-t33gs-ota.tgz
```

Updater cũng được cài thành `/usr/sbin/lumi-sysupgrade` trong image mới. Nó đọc
SoC từ `BUILD_PLATFORM` thay vì hostname `lumi`, nhận phân vùng `root`, chặn
layout khác và ngừng streamer/watchdog trước khi chuyển vào RAM. Do timestamp
kernel được cố định để build lặp lại, updater ghi các phân vùng được yêu cầu
thay vì bỏ qua khi timestamp trùng. Nếu không chuyển vào RAM được thì từ chối ghi.
Nếu cập nhật bị hủy sau khi dừng streamer, reboot để khởi động lại IMP đúng vòng đời.
`-z` giữ đúng phiên bản updater đi kèm build. Không dùng `-f` bỏ qua kiểm tra, không dùng
`-n` xóa overlay. Lệnh sẽ ghi flash và reboot; pipeline chỉ tạo gói, không tự chạy lệnh này.
Kết quả CI không chứng minh camera boot/stream/record/voice được. Cần ghi nhận
boot, Wi-Fi, API, RTSP và chức năng cần dùng trên board có UART recovery trước
khi phát hành. Manifest giữ trạng thái hardware qualification pending.

Kiểm tra CI không cần SDK hoặc camera:

```sh
make t33gs-test
bash -n ci/t33gs/build.sh ci/t33gs/post-build.sh
python3 .github/scripts/lint-workflow-shell.py
```

## Wake-word RISC-V mặc định trên T33gs

Khi build voice (mặc định), firmware build worker Linux không kèm suy luận CPU,
đóng gói `/lumi/firmware/wake.rvpack` từ cùng snapshot source và dùng launcher
`/lumi/bin/lumi-voice-riscv`. Launcher nạp module `lumi_riscv_mem.ko` cùng kernel;
worker sử dụng kernel lease, không truy cập MMIO trực tiếp. Không cần payload
trên thẻ nhớ. Cloud, PCM/AEC và xử lý hội thoại vẫn nằm trong worker Linux.

Build local cần `T33GS_RISCV_TOOLCHAIN` trong `ci/t33gs/local.mk`, trỏ tới bộ
RV32IMC/ILP32 newlib có `bin/riscv-none-embed-gcc` và `g++`.
`T33GS_VOICE=0` không yêu cầu toolchain này và không đóng gói worker/payload.
Voice vẫn cần cấu hình cloud/model và marker đã provision trong overlay;
firmware không nhúng credentials và không tự bật voice trên máy chưa provision.
Mặc định RISC-V này chỉ áp dụng profile T33gs PRJ008 hiện tại, không suy rộng
sang board/SoC chưa hỗ trợ. Lỗi MCU được báo ở voice, không chuyển ngầm về CPU.

Profile này chọn ngữ cảnh literal XZ `lc=0/lp=2` cho rootfs chủ yếu là mã MIPS,
giúp chứa payload trong phân vùng 12 MiB. Preset, kích thước khối/dictionary,
filter và bộ giải nén kernel giữ nguyên; kernel hiện tại hỗ trợ các giá trị này.
