# Skill hoạt hình bảng trắng từ SRT

**Tiếng Việt** · [English](README.en.md) · [中文](README.zh.md)

> Bản dịch tiếng Việt và tiếng Anh của [geeklee/srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation) (giấy phép MIT). Bản gốc tiếng Trung được giữ ở các tệp `*.zh.*`.

Skill biến phụ đề SRT thành video bảng trắng vẽ tay, các thành phần được vẽ theo đúng thứ tự kể chuyện. Skill kết hợp **dàn dựng bằng mặt nạ theo vùng** với **nét bút chảy liên tục**: mỗi thành phần xuất hiện lần lượt theo phụ đề, đầu bút đổ mực liên tục trong vùng rồi tô màu dần, cuối cùng xuất ra MP4.

Phù hợp để làm hoạt hình vẽ tay trên nền giấy vàng be ấm từ bài giảng, truyện kể, phụ đề khóa học hoặc kịch bản video ngắn.

## Ví dụ

**Cảnh: khỉ giành chuối trên núi giả** — theo thứ tự kể chuyện trong phụ đề, lần lượt vẽ núi giả và chú khỉ con, con khỉ lớn giành chuối, và các em nhỏ đứng xem.

![Khỉ giành chuối trên núi giả: demo hoạt hình bảng trắng từ SRT](examples/scene-01-monkey-mountain-stream.gif)

Line art gốc: [xem PNG](examples/scene-01-monkey-mountain.png).

## Khả năng chính

- Phân tích phụ đề SRT và chia cảnh theo thời lượng đề xuất 25–35 giây
- Đưa ra storyboard và chiến lược hình minh họa trước, bảo đảm mỗi cảnh chỉ diễn đạt một ý cốt lõi
- Sắp thứ tự vẽ theo ngữ nghĩa của sự kiện trong phụ đề, không theo tọa độ trên ảnh
- Dùng `annotation.json` để quản lý vùng, thời gian, liên kết với phụ đề và vùng bảo vệ khi chồng nhau
- Mỗi vùng vẽ bằng nét bút liên tục: `ink` phủ line art trước, `color` tô màu sau
- Có bảng xem trước trên trình duyệt để chỉnh vùng, thứ tự, thời gian và liên kết phụ đề
- Render từng cảnh và ghép nhiều cảnh thành MP4 hoàn chỉnh

## Cách làm việc

Điểm mấu chốt của skill là "phụ đề dẫn dắt, xác nhận từng bước". Sau mỗi bước đều dừng chờ xác nhận, tránh tốn công render khi storyboard, line art hay annotation chưa chốt:

1. Phân tích SRT, đưa ra storyboard và chiến lược hình minh họa.
2. Sau khi được xác nhận, tạo line art cùng một phong cách.
3. Sau khi xác nhận line art, kết hợp phụ đề và ảnh gốc để tạo annotation, rồi nạp vào bảng xem trước.
4. Sau khi xác nhận annotation, xuất ảnh kiểm tra vùng và hướng.
5. Trong bảng xem trước, chỉnh vùng, thứ tự kể chuyện, thời gian và liên kết phụ đề rồi lưu.
6. Sau khi xác nhận annotation cuối cùng, render MP4 từng cảnh.
7. Với dự án nhiều cảnh, ghép lại sau khi xác nhận thành phẩm từng cảnh.

## Quy chuẩn hình ảnh

- Nền giấy vàng be ấm: đề xuất `#F5EBD7`
- Nét phác xám đậm; đỏ, cam, xanh dương chỉ dùng làm điểm nhấn khái niệm với số lượng ít
- Vẽ tay tối giản, nền sạch, nhiều khoảng trống
- Không dùng chữ trong cảnh, nhãn, cảm giác ảnh chụp, hiệu ứng 3D hay chất liệu phức tạp

## Cài đặt và môi trường

Skill có sẵn script chuẩn bị môi trường ảo Python riêng. Lần chạy đầu tiên, thực hiện:

```bash
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

Khi thành công, lệnh đầu tiên in ra `ENV_PY=<đường dẫn>`; các bước render sau đó hãy dùng trình thông dịch này để cô lập phụ thuộc.

## Cấu trúc tài nguyên dự án

```text
assets/whiteboard/<tên dự án>/
├── scene-01-<tên>.png
├── scene-01-<tên>.annotation.json
├── scene-01-<tên>-whiteboard.mp4
└── scene-01-<tên>-preview.mp4
```

Ảnh và annotation phải cùng tên, ví dụ `scene-01-demo.png` ứng với `scene-01-demo.annotation.json`.

## Định dạng annotation

Mỗi thành phần dùng tọa độ pixel nguyên của ảnh gốc, và liên kết với sự kiện trong phụ đề qua `sequence`, `subtitle` và `narrativeRole`. Các vùng nên sắp theo trình tự "bối cảnh → nhân vật/vật chính → hành động hoặc biến đổi → phản ứng/kết quả".

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Chú khỉ con cầm quả chuối trên núi giả, con khỉ lớn giành mất, các em nhỏ đứng xem.",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Cảnh núi giả",
      "sequence": 1,
      "narrativeRole": "Bối cảnh mở đầu câu chuyện",
      "subtitle": "Chú khỉ con ngồi trên đỉnh núi giả, tay cầm quả chuối.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": {
        "direction": "top_to_bottom",
        "startMs": 300,
        "durationMs": 2600,
        "maskPaddingPx": 22,
        "protectedRegions": []
      },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

`direction` và `handPath` chỉ dùng cho hình chữ nhật đại diện trong bảng xem trước; nét bút thật của thành phẩm do bộ vẽ stream tự sinh. Với các đối tượng che nhau, hãy đánh dấu trong `protectedRegions` của thành phần xuất hiện sớm hơn những vùng cần hiện muộn, để nội dung phía sau không lộ ra sớm.

## Các lệnh thường dùng

Phân tích phụ đề và tạo đề xuất chia cảnh:

```bash
python scripts/parse_srt.py <phụ đề.srt> --target-sec 30 --min-sec 25 --max-sec 35
```

Tạo ảnh kiểm tra vùng:

```bash
python scripts/render_annotation_preview.py <đường dẫn ảnh> <đường dẫn annotation> <đường dẫn ảnh xem trước đầu ra>
```

Mở `assets/preview.html`, bấm "Mở thư mục…" để nạp thư mục cảnh, rồi chỉnh vùng, thứ tự, thời gian và liên kết phụ đề.

Render một cảnh:

```bash
<ENV_PY> scripts/render_stream_whiteboard.py <đường dẫn ảnh> <đường dẫn annotation> <đầu ra.mp4> assets/drawing-hand.png \
  --ink-path grid --color-fill contour-wipe
```

Ghép nhiều cảnh:

```bash
<ENV_PY> scripts/merge_scenes.py --inputs canh1.mp4 canh2.mp4 canh3.mp4 --output final.mp4
```

## Kiểm tra chất lượng

- Khung hình đầu là nền giấy vàng be sạch, không lộ nét nào sớm
- `canvas` khớp kích thước ảnh gốc, mọi vùng là tọa độ pixel nguyên nằm trong canvas
- `sequence`, `startMs` khớp thứ tự kể chuyện trong phụ đề
- Ở khung hình giữa, vùng chưa bắt đầu và vùng bảo vệ không hiện ra sớm
- Đầu bút bám sát nét đang chạy; khi line art rõ có thể chọn `--ink-path skeleton`
- Cuối mỗi cảnh dừng ít nhất 0,5 giây ở ảnh đầy đủ; thứ tự ghép nhiều cảnh khớp với storyboard theo phụ đề

## Nội dung kho mã

```text
srt-whiteboard-animation/
├── SKILL.md                         # Quy trình đầy đủ và ràng buộc (tiếng Việt)
├── SKILL.en.md / SKILL.zh.md        # Bản tiếng Anh / bản gốc tiếng Trung
├── README.md / README.en.md / README.zh.md
├── assets/
│   ├── drawing-hand.png              # Ảnh bàn tay
│   ├── preview.html                  # Bảng xem trước/chỉnh sửa cục bộ (tiếng Việt)
│   └── preview.en.html / preview.zh.html
├── examples/                         # Tài nguyên ví dụ cho README
├── scripts/
│   ├── parse_srt.py                  # Phân tích phụ đề và đề xuất chia cảnh
│   ├── render_annotation_preview.py  # Ảnh kiểm tra annotation
│   ├── render_stream_whiteboard.py   # Bộ render MP4 nét bút chảy liên tục
│   ├── merge_scenes.py               # Ghép nhiều cảnh
│   └── prepare_env.py                # Chuẩn bị môi trường phụ thuộc
└── agents/openai.yaml                # Metadata cho Codex
```

## Đóng góp

Hoan nghênh gửi Issue hoặc Pull Request. Mọi thay đổi liên quan đến logic vẽ nên được kiểm tra bằng phụ đề, annotation và thành phẩm thật để xác nhận mặt nạ bảo vệ, thời gian và hình ảnh cuối.

## Giấy phép

Dự án mã nguồn mở theo MIT License, xem [LICENSE](LICENSE).

## Về tác giả gốc

Tác giả gốc: 一个爱养鱼的老登 / AI Builder / dùng đội AI xây dựng công ty một người (Douyin, Bilibili, tài khoản công khai: 江哥是老登啊).
