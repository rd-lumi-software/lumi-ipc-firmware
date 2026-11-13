# Kế hoạch thống nhất build T33gs với luồng BOARD

Trạng thái: đã tích hợp defconfig/package/hook vào luồng BOARD, layout chuẩn
và kiểm tra overlay. Full NOR/OTA với voice bật/tắt đã build và vượt qua verifier;
đã kiểm tra rebuild platform/runtime và repack. Kiểm chứng board và đo RAM còn pending;
giữ luồng legacy để đối chiếu. Xem `build-inventory.md`.

## Mục tiêu và phạm vi

Dùng cùng giao diện Make/Buildroot cho T33gs PRJ008 và các board khác:

```sh
make BOARD=lumi_t33gs_prj008_sc4336 -j4
```

Tên defconfig dự kiến: `lumi/configs/lumi_t33gs_prj008_sc4336_defconfig`.
Mỗi board có cấu hình riêng; cùng SoC T33 không mặc định có cùng DDR, kernel,
SDK, sensor, GPIO, Wi-Fi, U-Boot hoặc layout flash.

Đợt đầu chỉ chuyển board T33gs PRJ008/SC4336 hiện có. Không tạo defconfig cho
board chưa biết phần cứng, không nâng phiên bản kernel/toolchain và không tự
flash camera. Giữ luồng hiện tại trong thời gian đối chiếu.

## Hiện trạng cần giải quyết

- `make t33gs-full` gọi shell để build kernel/module, U-Boot và runtime ngoài
  Buildroot; Buildroot chỉ tạo userspace (`BR2_LINUX_KERNEL` đang tắt).
- `lumi/package/lumi-osdrv-t33` là template cũ: dùng `CONFIG_KERNEL_3_10`,
  đường dẫn module `3.10.14`, SDK staging và đường dẫn repo sibling cố định.
  Không bật package này cho kernel 4.4.94 khi chưa sửa/tách implementation.
- Có ba nhóm toolchain C cần giữ phân biệt: GCC 5.4/uClibc cho kernel/vendor;
  musl soft-float cho native runtime; OpenIPC musl cho userspace Buildroot.
  Rust target/config cũng phải giữ như luồng hiện tại. Không thay toolchain
  chỉ để làm cấu trúc thư mục giống nhau.
- Init/service đến từ ba lớp `general/overlay`, `lumi/overlay` và overlay board;
  post-build còn copy, sửa và xóa file. Cần xác định nguồn cuối cùng và thành phần
  chịu trách nhiệm cài mỗi file để tránh ghi đè hoặc cài trùng.
- Layout RAM/flash đang lặp ở packer, `firmware.py`, U-Boot, kernel config và
  updater. Cần một cấu hình board làm nguồn chuẩn và kiểm tra các consumer.
- Root Makefile còn gọi `repack` sau Buildroot. Board mới cần đi qua packer
  NOR/OTA đúng layout; không chạy thêm repack với layout mặc định khác.
- `br-ext-chip-ingenic` hiện chứa cấu hình vendor; external tree hoạt động là
  `general` và, cho sản phẩm Lumi, `lumi`. Không cần tạo external tree mới.

## Cấu trúc đích

| Phạm vi | Nội dung | Vị trí dự kiến |
| --- | --- | --- |
| SoC/SDK | Khả năng T33, phiên bản kernel/SDK/toolchain, package driver tái sử dụng | Các package trong `lumi/package/`; nguồn kernel/driver ở repo nguồn tương ứng |
| Board | Defconfig, DTS/fragment được chọn, DDR/U-Boot, GPIO, sensor/tuning, Wi-Fi, layout flash | `lumi/configs/` và `lumi/board/t33gs-prj008/` |
| Sản phẩm | Streamer, relay, voice, dịch vụ, overlay | Package/overlay Lumi; tính năng chọn qua Kconfig |
| Nguồn local | Đường dẫn checkout, SDK/toolchain cài trên máy | File cấu hình riêng được git-ignore và cơ chế source override |
| CI | Fetch SHA đã pin, chuẩn bị SDK, gọi cùng target BOARD | `.github/workflows/lumi-t33gs.yml`, `ci/t33gs/` |

Tên package cụ thể được chốt sau khi lập dependency graph. Package chỉ chứa
phần dùng chung đã có bằng chứng tương thích; PRJ008 không làm mặc định cho T33.
Các patch kernel tiếp tục nằm trong repo Linux, không chuyển vào shared patches
của firmware. Thay đổi dưới `general/` phải tuân thủ quy định riêng của repo.

## Các bước triển khai

### 1. Chốt baseline và hợp đồng đầu ra

- Ghi lại commit nguồn, hash SDK, phiên bản compiler, kernel config và các
  cờ ABI/runtime của luồng đang dùng.
- Lập danh sách các bước build, input/output và dependency từ `build.sh`,
  `build-t33gs-k4494.sh` và các script runtime của streamer.
- Chạy baseline từ workspace sạch; lưu log, manifest và kết quả verification.
  Nếu baseline thất bại thì sửa/chốt nguyên nhân trước khi dùng để đối chiếu.
- Lập bảng nguồn/cài đặt cuối cùng cho init script, service, binary và config:
  file đến từ overlay/package/hook nào, bị ghi đè hoặc xóa ở bước nào.
- Ghi lại thứ tự init thực tế, dependency driver/network/runtime và thành phần
  đang giám sát/restart từng tiến trình; giữ hành vi này làm baseline.
- Giữ chính sách RAM hiện tại: `mem=96M@0x0 rmem=32M@0x6000000 cma=16M`.
  CMA thuộc vùng RAM Linux quản lý, không cộng thành vùng RAM vật lý thứ ba.
- Giữ layout PRJ008 hiện tại: boot 256 KiB, kernel 2560 KiB, rootfs 12288 KiB,
  rootfs_data 1248 KiB, env 32 KiB; full image 16 MiB.

Điều kiện qua bước: có baseline build thành công, bộ đầu ra có thể đối chiếu
và bảng nguồn file/service cùng chính sách RAM/flash hiện tại.

### 2. Tách cấu hình board và nguồn đầu vào

- Tạo defconfig PRJ008/SC4336 mới, không tái sử dụng template GC4653/kernel 3.10.
- Đưa lựa chọn sensor, GPIO, tuning, Wi-Fi, U-Boot/DDR và flash layout vào board.
- Định nghĩa cấu hình layout chuẩn của board: kích thước flash, offset/kích
  thước từng phân vùng, bootargs RAM/rmem/CMA và địa chỉ env. Sinh cấu hình cho
  các consumer khi khả thi; nếu repo nguồn cần giữ cấu hình riêng thì kiểm tra
  chéo và dừng build khi U-Boot, packer, kernel config hoặc updater lệch nhau.
- Kiểm tra phân vùng không chồng lấn/vượt flash, địa chỉ env khớp
  `fw_env.config`, kích thước image trong giới hạn và CMA phù hợp RAM Linux.
  Ghi các giá trị layout resolve được vào manifest build.
- Phân loại lại overlay: phần dùng chung OpenIPC, sản phẩm Lumi và riêng board.
  Giữ GPIO, sensor, tuning và layout PRJ008 trong phạm vi board. Lập danh sách
  ghi đè có chủ đích; bổ sung kiểm tra va chạm ngoài danh sách và file bị hook
  xóa/sửa để người review thấy rootfs cuối cùng được tạo ra thế nào.
- Chuyển đường dẫn nguồn sang biến/override; bỏ phụ thuộc vị trí sibling repo.
- Giữ cơ chế snapshot local: nhận thay đổi chưa commit, loại artifact cũ,
  build ở workspace riêng. CI dùng nguồn đã pin SHA.
- Giữ vendor library/tuning/Wi-Fi firmware là input SDK được kiểm tra checksum;
  không mô tả các binary này là đã build lại từ source.

Điều kiện qua bước: cấu hình resolve được từ workspace bất kỳ; thiếu input
hoặc cấu hình ABI không tương thích phải báo lỗi trước khi compile. Layout
phải nhất quán giữa các consumer; không rò giá trị PRJ008 sang cấu hình khác.

### 3. Đưa kernel, module và U-Boot vào dependency graph Buildroot

- Chốt cách tích hợp kernel bằng thử nghiệm trên Buildroot 2024.02.10:
  ưu tiên Linux infrastructure; kiểm chứng compiler riêng cho kernel/module
  không bị thay bằng compiler userspace trong các build/config/install hook.
- Nếu hạ tầng Linux chuẩn không đáp ứng compiler SDK, dùng package kernel
  vendor có dependency/output rõ ràng. Đây vẫn là build do Buildroot quản lý;
  không giữ một script điều phối toàn bộ pipeline phía sau target BOARD.
- Tách driver SDK 4.4.94 khỏi implementation 3.10 cũ. ISP, sensor, audio,
  motor, TNPU, AES/DMA và Wi-Fi phụ thuộc đúng kernel build directory/config.
- Build U-Boot từ source với cấu hình board và compiler đã chốt.
- Cài module theo kernelrelease thực, tạo dependency index; giữ các kiểm tra
  ELF/vermagic và allocator/DMA hiện tại. Input thiếu phải thất bại, không bỏ qua.

Điều kiện qua bước: Buildroot tạo được kernel, module và U-Boot từ source sạch;
rebuild driver không dùng kernel/object từ luồng cũ.

### 4. Đưa runtime Lumi vào package và hook chuẩn

- Đóng gói native dependency, relay, streamer/gateway, recorder, snapshot và
  voice tùy chọn; khai báo dependency và thứ tự cài rõ ràng.
- Giữ nguyên các compiler/ABI, Cargo lockfile, TFLM pin và các lựa chọn hiện tại.
- Điều chỉnh script nguồn để nhận đường dẫn/build directory từ package;
  compile trong vùng build, không sửa checkout người dùng.
- Package chịu trách nhiệm cài binary, thư viện và init script của tính năng
  được chọn. Overlay giữ cấu hình tĩnh/script board hoặc sản phẩm; post-build
  hoàn thiện cấu hình sinh tự động, manifest/updater và kiểm tra tính nhất quán.
  Loại các bước copy/xóa chữa lại kết quả cài của package khi đã thay thế được.
- Sinh hardware.env từ cấu hình board; không lặp GPIO/sensor trong nhiều hook.
- Rà thứ tự driver → network → runtime theo dependency thực tế. Phân định vai
  trò init, supervisor và watchdog: mỗi tiến trình có cơ chế quản lý restart rõ
  ràng, không để nhiều thành phần cùng restart một service. Giữ cơ chế phục hồi
  cần thiết và thứ tự stop ngược dependency, đặc biệt khi OTA chuyển vào RAM.
- Khi tắt tính năng tùy chọn, không cài binary/init script tương ứng; phần
  còn lại không được gọi một service đã bị loại. Kiểm tra quyền executable,
  shell syntax và đường dẫn mà init script sử dụng.

Điều kiện qua bước: rootfs vượt qua verifier hiện tại ở cả voice bật và tắt;
không chứa secret hoặc artifact lấy từ lần build trước. Mỗi service/file có
thành phần chịu trách nhiệm cài rõ ràng; cấu hình tắt tính năng không để lại
init script lỗi, và luồng stop/OTA vẫn vượt qua các kiểm tra hiện có.

### 5. Nối giao diện Make, đóng gói và CI

- Cho `make BOARD=lumi_t33gs_prj008_sc4336` đi xuyên suốt dependency graph.
  Có target rõ ràng cho full build và rebuild package khi phát triển.
- Dùng post-image hook để gọi packer NOR/OTA hiện có. Chọn đường đóng gói theo
  board, tránh root Makefile chạy repack mặc định lần nữa.
- Giữ `firmware.py` và các verifier/packer binary dùng chung; không viết lại
  CRC/ELF/layout bằng shell. Giữ tên artifact, checksum và manifest hiện tại.
- Dùng `-jN` làm giao diện mức song song; kiểm tra GNU Make jobserver và các
  giới hạn Cargo/CMake. Nếu chạy qua Docker, truyền N rõ ràng vì jobserver
  không tự đi qua biên container. Tránh nhân N ở nhiều tầng gây quá tải.
- CI fetch/stage input rồi gọi cùng lệnh BOARD. Local vẫn nhận source override.
- Đăng ký defconfig vào CI matrix hoặc danh sách loại trừ kèm lý do theo quy
  định repo; chạy self-test selector trước khi merge.
- Giữ `t33gs-full` làm alias tương thích trong giai đoạn chuyển đổi, có tài liệu
  lệnh mới; không duy trì hai implementation build độc lập.

Điều kiện qua bước: local/CI cùng sử dụng cấu hình board và build graph;
`-j4` được kiểm tra thực tế trên các compiler/build tool bên trong.

### 6. Đối chiếu, kiểm chứng board và dọn luồng cũ

- Build sạch, build với thay đổi source local, rebuild package và chạy lại khi
  không đổi nguồn; kiểm tra dependency không bỏ sót hoặc tái sử dụng binary cũ.
- So sánh baseline với luồng mới: kernel config/release, toolchain/ABI, module,
  file rootfs, manifest, phân vùng, uImage CRC và nội dung gói OTA.
  Phân biệt khác biệt timestamp/build metadata với khác biệt chức năng.
- Kiểm thử host việc từ chối board/layout không tương thích. Dùng fixture để
  kiểm tra cấu hình không rò PRJ008 sang board khác; không giả lập bằng chứng
  chạy được trên một board T33 chưa có.
- Sau khi được phép triển khai lên thiết bị có UART recovery, kiểm chứng boot,
  sensor, Wi-Fi, API, RTSP, recording, voice nếu bật, reboot và OTA đúng layout.
  Chỉ ghi nhận bằng chứng quan sát được; không tự flash trong quá trình đổi build.
- Đo bộ nhớ trên board với các tổ hợp streaming, snapshot, recording và voice
  (khi bật), gồm chạy đồng thời và chạy kéo dài. Thu `/proc/meminfo` (đặc biệt
  MemAvailable, CmaTotal/CmaFree), log kernel/OOM, lỗi cấp phát ISP/DMA/CMA,
  restart và trạng thái stream/record/voice. Lưu cấu hình tải và thời gian đo.
- Giữ mem96/rmem32/CMA16 trong đợt chuyển đổi. Chỉ đề xuất đổi tỷ lệ sau khi
  có số đo baseline, xác định đủ headroom cho tải mục tiêu và kiểm thử hồi quy
  trên cùng board. Thay đổi tỷ lệ RAM là hạng mục riêng, không gộp vào chuyển
  build. Khi chưa có thiết bị, ghi phần đo còn pending, không suy ra từ build.
- Sau khi đạt các tiêu chí tương ứng, xóa orchestration cũ, helper không còn
  người gọi và tài liệu cũ; giữ công cụ binary dùng chung.

Điều kiện hoàn tất: build local/CI đạt, full/OTA đúng hợp đồng và có bằng chứng
board trước khi coi firmware đủ điều kiện phát hành. Nếu chưa có board, ghi rõ
build đã kiểm tra nhưng hardware qualification còn pending.

## Chia thay đổi để review

1. Baseline, dependency inventory, bảng overlay/service và cấu hình board/nguồn;
   layout chuẩn cùng kiểm tra chéo RAM/flash.
2. Kernel, driver và U-Boot qua Buildroot.
3. Runtime package, trách nhiệm cài rootfs, thứ tự init và cơ chế giám sát service.
4. Post-image, Make CLI, giới hạn job và CI.
5. Kết quả đối chiếu, bằng chứng board/số đo bộ nhớ và dọn đường cũ.

Chưa bỏ đường build cũ trước khi luồng thay thế đạt các kiểm tra cần thiết.
Không thay phiên bản dependency hoặc tối ưu cache trong cùng đợt nếu chưa có
số đo/chứng cứ yêu cầu; tránh trộn thay đổi kiến trúc build với thay đổi runtime.
