---
name: srt-whiteboard-animation
description: Biến phụ đề SRT thành video hoạt hình bảng trắng vẽ tay trên nền giấy vàng be ấm: đọc phụ đề → đưa ra chiến lược hình minh họa → sau khi được xác nhận thì tạo line art đồng nhất phong cách → đánh dấu vùng theo ngữ nghĩa kể chuyện → chỉnh trong bảng xem trước → render MP4. Phần dàn dựng giữ cơ chế hé lộ theo vùng bằng mặt nạ (annotation.json / sequence / startMs / protectedRegions), nhưng trong mỗi vùng nét mực được vẽ bằng nét bút liên tục kiểu stream (khung xương/lưới ink→color). Kích hoạt khi người dùng đưa phụ đề SRT và yêu cầu "làm video bảng trắng vẽ tay từ phụ đề", "nét bút chảy liên tục từ SRT", "SRT thành hoạt hình bảng trắng", "chia cảnh và vẽ tay theo phụ đề".
---

# Hoạt hình bảng trắng từ SRT (dàn dựng bằng mặt nạ + vẽ kiểu stream)

Chuyển phụ đề SRT thành hoạt hình bảng trắng vẽ tay. **Dàn dựng** giữ cơ chế hé lộ theo vùng bằng mặt nạ (các vùng xuất hiện lần lượt theo thứ tự kể chuyện, vùng chưa tới lượt hoàn toàn ẩn, vùng chồng nhau được bảo vệ bằng `protectedRegions`). **Cách vẽ** dùng nét bút chảy liên tục: trong mỗi vùng, đầu bút trượt liên tục dọc theo khung xương/lưới để đổ mực (bước đầu `ink`, rồi thêm màu `color`), mọi vùng dùng chung một canvas lưu giữ, vùng đã vẽ xong được giữ nguyên trên canvas. Mọi giải thích, storyboard, cấu hình và chữ trên giao diện hướng tới người dùng phải viết bằng tiếng Việt.

Khác với kiểu nhảy từng ô hay lau hình chữ nhật, nét bút của skill này **chảy liền mạch**. Khác với stream cho cả ảnh, skill này vẽ **lần lượt theo từng vùng kể chuyện của phụ đề**, nên điều khiển được thứ tự và thời điểm xuất hiện của từng thành phần.

## Tham số triển khai mặc định

| Mục | Yêu cầu mặc định |
|---|---|
| Nền giấy | Ảnh tạo ra dùng màu giấy cũ vàng be ấm (đề xuất `#F5EBD7`); khi render, lấy mẫu màu nền từ bốn góc ảnh (thụt vào trong) để nhuộm nền; cấm dùng trắng tinh. |
| Cách vẽ | Mỗi vùng vẽ bằng nét bút stream liên tục: bước đầu `ink` (phủ nét line art) → thêm màu `color` (khôi phục màu gốc); tỉ lệ thời gian `ink:color = 2:1`. |
| Đường đi của nét bút | `--ink-path grid` (lưới, mặc định, ổn định) hoặc `skeleton` (bám khung xương, hợp với tranh minh họa có line art rõ). |
| Kiểu tô màu | `--color-fill contour-wipe` (quét theo đường viền, mặc định) hoặc `brush` (quét cọ dọc theo quỹ đạo). |
| Vùng chưa vẽ | Mặt nạ cho phép của một vùng = hình chữ nhật `region` trừ đi "các vùng phía sau + protectedRegions"; vùng chưa bắt đầu hoàn toàn ẩn. |
| Nguồn thời lượng | `sceneDurationMs` của mỗi ảnh lấy từ khoảng thời gian phụ đề của cảnh đó (đề xuất 25–35 giây/cảnh). |
| Khung chỉnh sửa | Bảng xem trước mặc định hiện tất cả khung chỉnh sửa có đánh số; khung chỉnh sửa không thuộc nội dung hình ảnh của hoạt hình. |

## Quy chuẩn hình ảnh đồng nhất khi tạo ảnh (bắt buộc)

Ảnh nguồn của mọi cảnh phải theo cùng một ngôn ngữ hình ảnh; trước khi tạo, phải đưa đầy đủ các yêu cầu dưới đây vào prompt tạo ảnh, và sau khi tạo phải kiểm tra từng điều:

- **Phong cách và bố cục:** minh họa vẽ tay tối giản, thuần phác thảo bằng bút chì, thẩm mỹ nguệch ngoạc tiết chế kiểu Notion. Ưu tiên diễn đạt khái niệm, không theo đuổi chân thực; bố cục gọn, nền sạch, nhiều khoảng trống, cảm xúc chung bình lặng, rõ ràng, nét vẽ/nhân vật/màu sắc nhất quán trong cả loạt.
- **Màu sắc và chất liệu:** nền giấy be `#F5EBD7`, nét phác xám đậm; chỉ được dùng đỏ, cam, xanh dương làm điểm nhấn khái niệm với số lượng ít. Không dùng màu nhấn khác, màu bão hòa cao hay chất liệu phức tạp.
- **Nhân vật và đối tượng:** đối tượng thể hiện bằng đường viền đơn giản, ít nét và khoảng trống, nhấn vào quan hệ/biến đổi/khái niệm cốt lõi chứ không phải tỉ lệ, chất liệu và chi tiết thật.
- **Tuyệt đối cấm:** mọi chữ, từ, chữ cái, con số, phông chữ hoặc nhãn trong ảnh nguồn của cảnh; cảm giác chân thực, chi tiết kiểu ảnh chụp, hiệu ứng 3D, chất liệu tranh vẽ; cảnh phức tạp, nền dày đặc, trang trí rườm rà và hình có độ bão hòa cao.
- **Ngoại lệ về bàn tay vẽ:** nếu người dùng nói rõ chữ trên thân bút là logo của họ và yêu cầu giữ lại, có thể giữ logo trên thân bút trong `drawing-hand.png`; đó không tính là chữ trong ảnh nguồn của cảnh, không cần xóa hay vẽ lại. Khi chưa được người dùng nói rõ, vẫn xử lý theo nguyên tắc hình không có chữ.

## Cổng xác nhận (bắt buộc)

Trong quy trình mặc định, **sau khi hoàn thành mỗi bước đều phải dừng lại và chờ người dùng xác nhận rõ ràng** rồi mới bắt đầu bước tiếp theo. Trước khi được xác nhận, không được tạo ảnh, annotation, bản xem trước, video hay tệp ghép của bước kế tiếp; không được coi "chưa trả lời", "ủy quyền chung chung trước đó" hay "người dùng không phản đối" là xác nhận. Khi người dùng yêu cầu sửa bước trước, chỉ làm lại bước đó và chờ xác nhận lần nữa sau khi xong.

Hành động đi kèm duy nhất: **sau khi tạo xong JSON annotation, phải tự động mở bảng xem trước ngay và nạp thư mục chứa JSON đó**; việc này thuộc kết quả bàn giao của bước 3, không cần chờ xác nhận riêng cho việc "mở bảng xem trước". Nếu File System Access API của trình duyệt yêu cầu thao tác của người dùng, hãy dùng giao diện trình duyệt để chọn đúng thư mục đã xác định này; không được vì thế mà xin thêm xác nhận hoặc bắt người dùng tự mở bảng xem trước.

## Quy trình làm việc

1. **Đọc phụ đề, đưa ra chiến lược (chưa tạo ảnh).** Dùng `scripts/parse_srt.py` để phân tích SRT thành các dòng phụ đề và đề xuất chia cảnh theo 25–35 giây/cảnh. Dựa vào đó, đưa ra chiến lược hình minh họa: với mỗi cảnh nêu số thứ tự cảnh, ý diễn đạt cốt lõi, chủ thể của hình, khoảng phụ đề tương ứng và `sceneDurationMs`. Mỗi cảnh chỉ diễn đạt một ý cốt lõi. **Xong thì dừng, chờ người dùng xác nhận chiến lược.**
2. **Tạo line art.** Chỉ sau khi người dùng xác nhận chiến lược, theo "Quy chuẩn hình ảnh đồng nhất" tạo từng cảnh một ảnh line art 16:9 nền giấy cũ vàng be `#F5EBD7`, giữa các chủ thể chừa đủ khoảng trống để dễ tự động tách vùng; không được tạo chữ, ảnh chụp phức tạp, đối tượng chồng nhau hoặc yếu tố trái quy chuẩn. **Xong thì dừng, trình bày line art và chờ người dùng xác nhận.**
3. **Đọc phụ đề trước rồi xem ảnh, sau đó đánh dấu và mở bảng xem trước.** Chỉ sau khi người dùng xác nhận line art, trước hết đọc phụ đề tương ứng với ảnh, sau đó thực sự xem ảnh và lấy chiều rộng/cao theo pixel của ảnh gốc; không được chỉ dựa vào phụ đề để đoán hình, cũng không được chỉ sắp xếp máy móc theo vị trí trên ảnh. Trước hết rút ra các sự kiện kể chuyện trong phụ đề, rồi ghép các chủ thể nhìn thấy trong ảnh với từng sự kiện, sắp thứ tự vẽ theo ngữ nghĩa "bối cảnh → nhân vật/vật chính → hành động xung đột hoặc biến đổi → phản ứng/kết quả". Sau đó tạo `<tên ảnh>.annotation.json`. Tạo xong thì mở ngay `assets/preview.html` bằng trình duyệt mặc định và dùng nút "Mở thư mục" của bảng xem trước để nạp **thư mục chứa tệp annotation đó**, gồm tất cả cặp `<tên>.png` + `<tên>.annotation.json`; không được chỉ đưa đường dẫn tệp hay bắt người dùng tự thao tác. **Khi bảng xem trước đã nạp thư mục thì dừng, chờ người dùng xác nhận annotation và nội dung xem trước.**
4. **Tạo ảnh xem trước vùng.** Chỉ sau khi người dùng xác nhận annotation và nội dung xem trước, dùng `render_annotation_preview.py` xuất ảnh kiểm tra có đánh số/hướng, đối chiếu việc chia vùng khớp thứ tự kể chuyện, mọi vùng nằm trong canvas, các chủ thể chồng nhau đã được bảo vệ bằng `protectedRegions`. **Xong thì dừng, chờ người dùng xác nhận ảnh xem trước.**
5. **Chỉnh trong bảng xem trước và lưu.** Chỉ sau khi người dùng xác nhận ảnh xem trước, chỉnh trong bảng xem trước đã mở và đã nạp đúng thư mục: mặc định (chưa phát) hiển thị ảnh đầy đủ và các khung vùng; canvas là **đại diện hình chữ nhật**: kéo bốn cạnh bốn góc của vùng để sửa `region`, bên phải sửa tên/hướng/**bắt đầu (ms)/kết thúc (ms)** (thời lượng = kết thúc − bắt đầu, chỉ đọc) và **phụ đề**, kéo danh sách module để **đổi thứ tự** (tự sắp lại `sequence`), chọn module thì phụ đề tương ứng được tô sáng; kéo thanh thời gian hoặc bấm phát để xem hé lộ (vùng chưa bắt đầu không hiện); `direction` chỉ ảnh hưởng tới đại diện này. Sửa xong bấm "Lưu cảnh này/Lưu tất cả" để ghi lại vào `.annotation.json` gốc (kèm `subtitle` của mỗi vùng, và căn `sceneDurationMs` bằng thời điểm kết thúc của vùng cuối + 0,5 giây). **Sau khi lưu thì dừng, chờ người dùng xác nhận annotation và thời gian cuối cùng.**
6. **Render thành phẩm bằng dòng lệnh.** Chỉ sau khi người dùng xác nhận annotation và thời gian cuối cùng, dùng `render_stream_whiteboard.py` xuất từng cảnh thành MP4 hoàn chỉnh, kiểm tra ngẫu nhiên ba thời điểm: đầu, giữa của module chồng nhau bất kỳ, và cuối. **Xong thì dừng, chờ người dùng xác nhận thành phẩm.**
7. **Ghép nhiều cảnh (chỉ khi có nhiều cảnh).** Chỉ sau khi người dùng xác nhận mọi thành phẩm từng cảnh, dùng `merge_scenes.py` ghép theo thứ tự thành một video. **Xong thì dừng, chờ người dùng xác nhận video ghép cuối cùng.**

## Quy ước thư mục

Tạo trong dự án của người dùng:

```text
assets/whiteboard/<tên dự án>/
  scene-01-<tên>.png
  scene-01-<tên>.annotation.json     # cùng tên với png
  scene-01-<tên>-whiteboard.mp4      # thành phẩm
  scene-01-<tên>-preview.mp4         # đoạn thật (do bảng xem trước tạo, độ phân giải thấp)
```

Ảnh và cấu hình phải cùng tên: `foo.png` ứng với `foo.annotation.json`. Bảng xem trước dựa vào đó để tự nạp cấu hình.

## Sắp xếp theo ngữ nghĩa và đánh dấu mức pixel (bắt buộc thực hiện)

1. **Căn cứ đọc:** trước khi đánh dấu phải có đồng thời phụ đề và ảnh gốc đã được xem. Thiếu một trong hai thì phải yêu cầu bổ sung trước, không được tạo annotation.
2. **Căn cứ thứ tự:** `sequence`, `startMs` và `label` phải phản ánh thứ tự trước sau của các sự kiện trong phụ đề, không chỉ theo trái sang phải, trên xuống dưới hay mức độ nổi bật thị giác.
3. **Căn cứ tọa độ:** mỗi module xuất `x`, `y`, `width`, `height` là số nguyên pixel trong hệ tọa độ ảnh gốc; gốc ở góc trên trái, cấm dùng phần trăm/tỉ lệ/tọa độ ước chừng hay bỏ kích thước. `canvas.width`/`canvas.height` phải bằng kích thước pixel của ảnh gốc.
4. **Trường của module:** mỗi phần tử gồm `sequence`, `narrativeRole`, `subtitle`, `region`, `reveal`, `handPath`. `narrativeRole` dùng tiếng Việt mô tả vai trò kể chuyện của nó trong phụ đề; `subtitle` lưu nội dung phụ đề tương ứng với vùng đó (lấy từ SRT, để bảng xem trước liên kết và dùng cho các mục đích sau); `sequence` đánh số liên tục từ 1.
5. **Kiểm tra:** trước khi tạo ảnh xem trước, kiểm tra từng vùng có nằm trong canvas không, có bao trọn chủ thể nhìn thấy tương ứng không, có khớp sự kiện trong phụ đề không; các chủ thể chồng nhau dùng `protectedRegions` để bảo vệ rồi mới vẽ module.

## Mô hình thời gian (dành riêng cho cách vẽ stream)

- **Tổng thời lượng mỗi cảnh** `sceneDurationMs` lấy từ khoảng thời gian phụ đề của cảnh đó (`scenes[].sceneDurationMs` của `parse_srt.py`).
- **Các vùng vẽ nối tiếp:** cách vẽ stream chỉ có một cây bút chuyển động, nên trong cùng một cảnh các vùng nên **lần lượt theo thời gian** (`startMs` không chồng nhau): vùng sau bắt đầu từ `startMs + durationMs` của vùng trước (cộng thêm 100–300 ms nghỉ tùy chọn). Nếu `startMs` chồng nhau, bộ render vẫn xử lý lần lượt, nhưng về thị giác không còn là chạy song song.
- **ink→color trong vùng:** `durationMs` của mỗi vùng được chia theo `ink:color = 2:1` thành đoạn khởi bút và đoạn thêm màu. `durationMs` do **thời điểm bắt đầu/kết thúc** trong bảng xem trước quyết định (kết thúc − bắt đầu), có thể căn theo thời lượng phụ đề tương ứng của vùng; cũng có thể ước tính ban đầu bằng 150 pixel/giây × quãng đường vẽ.
- **Dừng hình kết thúc:** sau khi mọi vùng vẽ xong, tự động kéo dài tới `sceneDurationMs`, và đảm bảo cuối cảnh dừng ít nhất 0,5 giây ở ảnh gốc đầy đủ.
- `reveal.direction` trong cách vẽ stream **không quyết định nét bút thật** (nét bút do khung xương/lưới tự sinh), chỉ phục vụ phần đại diện hình chữ nhật trong bảng xem trước; giữ lại để bảng xem trước dùng được.

## Bất biến của mặt nạ (tầng dàn dựng, bắt buộc thực hiện)

- Tại thời điểm `t`, một module chỉ được hiển thị các pixel sau `reveal.startMs ≤ t` và không vượt quá tiến độ vẽ hiện tại; module chưa bắt đầu thì không được lộ bất kỳ nét, vùng tô hay hình nào.
- **Mặt nạ cho phép** của mỗi vùng = hình chữ nhật `region` trừ đi `region` của toàn bộ **các module phía sau**, rồi trừ đi `reveal.protectedRegions` của chính module đó. Nét mực stream bị giới hạn trong mặt nạ cho phép, nên các vùng phía sau sẽ không bị lộ nét sớm.
- `protectedRegions` dùng cùng tọa độ pixel nguyên của ảnh gốc như `region`, dùng khi hình chữ nhật quá lớn, chủ thể đan xen hoặc nét nền có thể rò rỉ.
- Bộ render đã hiện thực thứ tự "giới hạn đổ mực trong mặt nạ cho phép → các vùng phía sau và vùng bảo vệ tự nhiên không bị chạm tới"; đại diện hình chữ nhật của bảng xem trước dùng phép trừ `destination-out` tương đương để minh họa cùng cách dàn dựng.

## Ví dụ cấu hình

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Tóm tắt các sự kiện trong phụ đề của cảnh này",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Cảnh núi giả",
      "sequence": 1,
      "narrativeRole": "Bối cảnh mở đầu câu chuyện",
      "subtitle": "Trên núi khỉ, một chú khỉ con ngồi trên đỉnh núi giả, tay cầm quả chuối.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": { "direction": "top_to_bottom", "startMs": 300, "durationMs": 2600, "maskPaddingPx": 22, "protectedRegions": [] },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

> `direction` / `handPath` chỉ dùng cho đại diện hình chữ nhật của bảng xem trước; nét bút trong thành phẩm do stream tự sinh, không cần tinh chỉnh.

## Dùng các script

Mọi script render chạy bằng trình thông dịch trong `.venv` của skill (cô lập phụ thuộc).

1. **Chuẩn bị môi trường** (lần đầu hoặc khi thiếu phụ thuộc):
   ```bash
   python scripts/prepare_env.py --check   # dò; thành công thì dòng cuối in ENV_PY=<đường dẫn>, ghi lại để dùng
   python scripts/prepare_env.py           # thiếu thì tạo .venv và cài opencv-python/numpy/av
   ```
2. **Phân tích phụ đề + đề xuất chia cảnh**:
   ```bash
   python scripts/parse_srt.py <phụ đề.srt> --target-sec 30 --min-sec 25 --max-sec 35
   ```
3. **Ảnh xem trước vùng có đánh số**:
   ```bash
   python scripts/render_annotation_preview.py <ảnh> <annotation> <ảnh xem trước đầu ra>
   ```
4. **Bảng xem trước (không cần máy chủ)**: mở thẳng `assets/preview.html` bằng Chrome / Edge, bấm "Mở thư mục" chọn thư mục → nạp toàn bộ ảnh + annotation cùng tên → kéo thả để chỉnh → "Lưu" để ghi lại vào tệp gốc. Ghi lại cần File System Access API (Chrome/Edge); trình duyệt khác thì tải về rồi ghi đè thủ công. Việc render vẫn chạy bằng dòng lệnh (bước 5 dưới đây).
5. **Render thành phẩm một cảnh**:
   ```bash
   <ENV_PY> scripts/render_stream_whiteboard.py <ảnh> <annotation> <đầu ra mp4> assets/drawing-hand.png \
       [--ink-path grid|skeleton] [--color-fill contour-wipe|brush] [--total-ms <mili giây>]
   ```
   Nếu không đặt `--total-ms` thì dùng `sceneDurationMs` trong annotation. Dòng cuối in `OUTPUT=<đường dẫn>`.
6. **Ghép nhiều cảnh**:
   ```bash
   <ENV_PY> scripts/merge_scenes.py --inputs canh1.mp4 canh2.mp4 canh3.mp4 --output final.mp4
   ```

## Kiểm tra chất lượng

Trước/sau khi render, xác nhận:

- Khung hình đầu là nền giấy cũ vàng be sạch, không lộ nét nào sớm.
- Đã đọc phụ đề tương ứng và thực sự xem ảnh gốc; `canvas` khớp kích thước pixel ảnh gốc, mọi `region` là tọa độ pixel nguyên và nằm trong canvas.
- `sequence`, `startMs` khớp thứ tự sự kiện trong phụ đề; số thứ tự/nhãn/vùng của ảnh xem trước đều đến từ cùng một JSON annotation.
- Tại ba thời điểm: lúc mở đầu, giữa của module chồng nhau bất kỳ, và khi mọi module đã xong, kiểm tra: module chưa vẽ đều không nhìn thấy, vùng bảo vệ chồng nhau không rò, khung cuối hiện ảnh gốc đầy đủ.
- Đầu bút bám sát nét đang tiến; với tranh minh họa có line art rõ có thể dùng `--ink-path skeleton` để nét bám hơn.
- Sau khi mọi module kết thúc, dừng ít nhất 0,5 giây ở ảnh gốc đầy đủ.
- Sau khi ghép nhiều cảnh, thứ tự và thời lượng khớp với việc chia cảnh theo phụ đề.

Nếu muốn đổi hiệu quả, hãy chỉnh annotation (vùng/thứ tự/thời gian) trong bảng xem trước (`assets/preview.html`) và lưu, rồi mới render bằng dòng lệnh; đừng render đi render lại một cách vô căn cứ.
