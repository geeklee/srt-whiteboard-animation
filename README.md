# SRT 白板动画 Skill

将 SRT 字幕转为按叙事顺序绘制的白板手绘视频Skill。它结合了**分区遮罩编排**与**流式笔迹绘制**：每个元素跟随字幕依次出场，笔尖在区域内连续落墨，再逐步添彩，最终导出 MP4。

线稿的默认视觉语言是**小黑 IP**（暖黄纸底、黑色手绘线、小黑承担核心动作、画面内无文字），
来自 [ian-xiaohei-illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations)（作者 Ian，MIT），
已作为风格包收录在 [`styles/ian-xiaohei/`](styles/ian-xiaohei/README.md)。

适合把知识讲解、故事口播、课程字幕或短视频文案制作成暖米黄色纸张底的手绘动画。

## 效果示例

**场景：猴子山抢香蕉** —— 随着字幕的叙事顺序，依次绘制假山与小猴、抢香蕉的大猴，以及围观小朋友。

![猴子山抢香蕉：SRT 白板动画演示](examples/scene-01-monkey-mountain-stream.gif)

原始线稿：[查看 PNG](examples/scene-01-monkey-mountain.png)。

## 核心能力

- 解析 SRT 字幕，并按建议的 25–35 秒时长拆分场景
- 先输出分镜与配图策略，确保每一幕只表达一个核心意思
- 线稿统一用小黑 IP：小黑必须承担核心动作，一幕只讲一个结构，画面内不写字
- 提供小黑风格包（风格 DNA、IP 设定、构图模式、提示词模板、QA 清单）
- 按字幕事件而非画面坐标，为元素建立语义化的绘制顺序
- 用 `annotation.json` 管理区域、时序、字幕关联和重叠保护区
- 每个区域采用连续流式笔迹：先 `ink` 铺线稿，再 `color` 添彩
- 支持浏览器预览台调整区域、顺序、时间和字幕关联
- 支持逐幕渲染与多幕合并，输出完整 MP4
- 默认带开场封面：Codex 出封面分镜，中文主标/副标由渲染器手写，片头 4–6 秒后擦入第一幕
- 每幕自动手写「标题 + 2–4 条要点」（渲染器排版书写，不把中文烤进出图）
- 幕间自带过渡：上一幕完整画面停留后擦除，擦到下一幕已有墨的画面（并抹掉那一帧里下一幕的手），不闪回空白画布
- 用 edge-tts（云希，免费无需 key）按字幕逐条合成中文旁白并混进成片，不烧录字幕
- 旁白卡点跟画面走：语音超窗默认扩窗顺延，不用变速把人声催快

## 工作方式

该 Skill 的关键在于“字幕驱动、逐步确认”。每一步完成后都等待确认，避免在分镜、线稿或标注尚未定稿时浪费渲染成本：

1. 解析 SRT，输出分镜与配图策略（含封面主标/副标）。
2. 确认后生成统一风格的线稿。
3. 确认线稿后，结合字幕和原图创建标注，并载入预览台。
4. 确认标注后，生成分区与方向检查图。
5. 在预览台调整区域、叙事顺序、时序和字幕关联并保存。
6. 确认最终标注后，逐幕渲染 MP4。
7. 多幕项目在确认各幕成片后合并。
8. 确认最终视频后，先把字幕对齐到成片真实时间线，再配旁白并混音。

## 视觉规范（小黑风格包）

完整规范见 [`styles/ian-xiaohei/README.md`](styles/ian-xiaohei/README.md)，出图请直接套用
[`whiteboard-prompt-template.md`](styles/ian-xiaohei/whiteboard-prompt-template.md)：

- **小黑必须出现且承担核心动作**：黑色实心身体、白圆点眼、细腿、空表情、手绘不规则轮廓；只当装饰就要重画
- 暖米黄色纸张背景：出图用 `#F5EBD7`（**不是纯白**）；渲染时画布底色为 `#F6F1E3`（`stream_render.py` 的 `Config.canvas_hex`），渲染器会把原图中接近背景的像素统一涂成该底色，使起笔阶段与上色阶段的背景一致
- 黑色手绘线条；红、橙、蓝仅作**非文字**的少量点缀（橙=主路径箭头，红=关键问题或结果，蓝=补充或系统状态）
- 极简手绘、一图一结构、干净背景与充足留白（主体约占 40%–60%，至少留 35% 空白）
- 主体之间留出可分区的空白走廊，四角保持干净纸底，主体数量对齐该幕字幕事件数
- **画面文字只允许「标题 + 2–4 条要点」这一种**，且由渲染器手写、不烤进出图；其它文字（随意标签、英文 UI、水印、类型标题、密集手写批注）一律禁止
- 出图时给标题要点留一块空白（画面上方或左上），那里不要画东西
- 不使用摄影感、3D 效果、复杂纹理、PPT 信息图、正式流程图或可爱卡通

手部素材：若存在 `assets/drawing-hand-v2.png` 或 `/workspace/e2e-paper/assets/drawing-hand-v2.png`，
渲染器会自动改用这张重画版（原 `drawing-hand.png` 不会被覆盖）；也可用 `SRT_WB_HAND` 指定任意素材，
用 `--hand-height` 调大小（多格分镜建议 260 左右，避免手挡住画面）。

小黑的实心黑身体在起笔阶段可能只勾出轮廓、到添彩阶段才填实；想让起笔阶段就填实，渲染时加 `--solid-ink-gray 90`。
含大面积实心黑的画面不要用 `--ink-path skeleton`（骨架追踪只沿中轴线揭示，实心区域会留空）。

## 安装与环境

Skill 自带独立的 Python 虚拟环境准备脚本。首次运行时执行：

```bash
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

依赖及其版本范围记在 `requirements.txt`（`prepare_env.py` 会按它安装）。依赖齐全时 `--check` 末行输出 `ENV_PY=<路径>`；缺依赖时它以非零码退出，直接运行不带 `--check` 的命令补齐即可。

除 `parse_srt.py`（纯标准库）外，其余脚本都请用 `<ENV_PY>` 运行——`render_annotation_preview.py` 需要 Pillow，渲染需要 opencv/numpy，它们只装在 `.venv` 里。

## 项目素材结构

```text
assets/whiteboard/<项目名>/
├── scene-01-<名称>.png
├── scene-01-<名称>.annotation.json
├── scene-01-<名称>-whiteboard.mp4
└── scene-01-<名称>-preview.mp4
```

图片与标注必须同名，例如 `scene-01-demo.png` 对应 `scene-01-demo.annotation.json`。

## 标注格式

每个元素使用原图的整数像素坐标，并通过 `sequence`、`subtitle` 与 `narrativeRole` 关联字幕中的事件。区域应按“场景铺垫 → 关键人物/物体 → 动作或变化 → 反应/结果”排序。

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "小猴在猴子山上拿着香蕉，大猴抢走香蕉，孩子们在旁观看。",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "猴子山场景",
      "sequence": 1,
      "narrativeRole": "故事的场景铺垫",
      "subtitle": "小猴子坐在猴子山顶，手里拿着香蕉。",
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

`direction` 和 `handPath` 用于预览台的矩形代理；最终成片的真实笔迹由流式绘制器自动生成。对于相互遮挡的对象，在较早元素的 `protectedRegions` 中标出需要延后显示的区域，避免后续内容提前露出。

字段说明与已知取舍：

- **绘制顺序只看 `reveal.startMs`。** 渲染器按 `startMs` 排序，`sequence` 只是给人和预览台看的编号，不影响成片。因此在预览台拖动列表调整顺序后，**必须一并调整开始/结束时间**，否则成片顺序不变。两者不一致时校验器会给出提醒。
- **`maskPaddingPx` 目前是保留字段**，渲染器与预览台都不读取它，可以照抄默认值。
- 渲染前建议先跑一遍校验（缺字段、区域越界、时间窗重叠都会指出来）：

```bash
python scripts/annotation_schema.py <标注路径> [图片路径]
```

## 常用命令

解析字幕并生成建议分镜：

```bash
python scripts/parse_srt.py <字幕.srt> --target-sec 30 --min-sec 25 --max-sec 35
```

生成区域检查图（字体自动探测 Windows / macOS / Linux 常见中文字体，也可用 `--font` 或环境变量 `SRT_WB_FONT` 指定）：

```bash
<ENV_PY> scripts/render_annotation_preview.py <图片路径> <标注路径> <预览图输出路径> [--font 字体文件]
```

打开 `assets/preview.html`，使用“打开文件夹”载入场景目录，即可编辑区域、顺序、时间与字幕关联。

渲染单幕：

```bash
<ENV_PY> scripts/render_stream_whiteboard.py <图片路径> <标注路径> <输出.mp4> assets/drawing-hand.png \
  --ink-path grid --color-fill contour-wipe
```

成片长度由各区域的 `startMs + durationMs` 累加决定：`--total-ms`（缺省取 `sceneDurationMs`）只用于在画完之后补足凝视时长，**只能延长、不能缩短**。要缩短成片，请改区域时序。`--pause` 在逐区域画法下不生效（保留参数，仅整图模式 `stream_render.py` 使用）。

生成开场封面标注（主标/副标由渲染器手写，不烤进出图；`--no-cover` 跳过）：

```bash
python scripts/make_cover.py --board 封面.png --title "动态组合" \
  --subtitle "把可撤销效应和响应式协效应做成运行时" --output 封面.annotation.json
```

合并（封面接在最前；幕间停留 600ms + 擦除 700ms，擦到下一幕已有墨的一帧）：

```bash
<ENV_PY> scripts/merge_scenes.py --inputs 幕1.mp4 幕2.mp4 幕3.mp4 --cover 封面.mp4 \
  --output final.mp4 --timeline-out timeline.json [--hold-ms 600] [--erase-ms 700]
```

按成片时间线重定时字幕（插过渡后必须做，否则旁白比画面早开口；每幕第一条会随标题书写开口，
避免幕首静音，`--no-text-lead` 可关）：

```bash
python scripts/retime_srt.py --srt 原始.srt --scenes scenes.json --timeline timeline.json \
  --annotations 幕1.annotation.json ... --output 重定时.srt
```

配旁白并混音（edge-tts，免费、无需 key，需联网）：

```bash
<ENV_PY> scripts/mux_srt_narration.py --srt <字幕.srt> --video final.mp4 \
  --output final-narrated.mp4 [--voice zh-CN-YunxiNeural] [--rate +0%] [--keep-wav]
```

每条字幕单独合成、按自己的起点对齐。默认 `--fit extend`：**不改语速**，语音超窗就自然说完、后面顺延；
整体放不进画面时报错并告诉你还差多少秒——正确做法是把对应区域的 `durationMs` / 该幕凝视加长后重渲，
或精简文案，而不是把人声催快。只有确实要强行塞进现有时长时才用 `--fit atempo`（逐条告警）。
视频流是 `-c:v copy`，画面零改动、**不烧录字幕**，字幕仍作为外部 `.srt` 交付。`--output` 不能与 `--video` 相同。

## 质量检查

- 首帧是干净的暖米黄纸张底色，没有提前露出的线条
- 每幕都有小黑且承担核心动作；画面内没有任何文字（含手写批注）
- `canvas` 与原图尺寸一致，所有区域都是画布内的整数像素坐标
- `sequence`、`startMs` 与字幕的叙事顺序一致
- 中段帧中，未开始区域和保护区不会提前出现
- 笔尖贴近当前流式笔迹；线稿清晰、且没有大面积实心黑时才可选择 `--ink-path skeleton`
- 每幕结束后至少停留 0.5 秒完整画面；多幕合并顺序与字幕分镜一致
- 片头封面：手写主标/副标通栏够大，第一句在写主标时就开口，停留约 1 秒后擦入第一幕
- 每幕有手写标题 + 2–4 条要点，未写出区域、与隐喻不重叠
- 幕间接缝：上一幕完整画面停留 ≥0.5s 后擦除过渡，没有硬切回空白
- 带旁白的成片有 aac 音轨、旁白开口时对应那一笔已在画、未被加速、画面未烧录字幕

## 仓库内容

```text
srt-whiteboard-animation/
├── SKILL.md                         # 完整工作流与约束
├── requirements.txt                  # 渲染链依赖及版本范围
├── assets/
│   ├── drawing-hand.png              # 手部素材
│   ├── preview.html                  # 本地编辑预览台
├── examples/                         # README 案例素材
├── scripts/
│   ├── parse_srt.py                  # 字幕解析与分镜建议
│   ├── annotation_schema.py          # 标注校验（渲染前自动执行，也可单独跑）
│   ├── render_annotation_preview.py  # 标注检查图
│   ├── render_stream_whiteboard.py   # 编排层：分区遮罩 + 时序，输出单幕 MP4
│   ├── stream_render.py              # 画法层引擎：骨架/网格笔迹、上色、转码
│   ├── merge_scenes.py               # 多幕合并 + 幕间停留/擦除过渡
│   ├── make_cover.py                 # 开场封面标注（手写主标/副标）
│   ├── retime_srt.py                 # 按成片时间线/作画时序重定时字幕
│   ├── text_render.py                # 标题+要点的手写排版与笔序
│   ├── fonts.py                      # 中文/楷体字体定位
│   ├── mux_srt_narration.py          # edge-tts 旁白合成与混音
│   └── prepare_env.py                # 依赖环境准备
├── styles/ian-xiaohei/               # 小黑风格包（vendored，MIT，作者 Ian）
│   ├── README.md                     # 风格包说明与覆盖规则
│   ├── whiteboard-prompt-template.md # 融合后的出图提示词模板
│   ├── references/                   # 风格 DNA / IP 设定 / 构图模式 / QA 清单
│   ├── LICENSE, NOTICE.md            # 上游许可与署名
├── tests/                            # pytest + node 的回归测试
└── agents/openai.yaml                # Codex 元数据
```

`render_stream_whiteboard.py` 负责「按字幕分区、按时序揭示」，真正的笔迹生成、上色与 H.264 转码都在 `stream_render.py` 里（它也可作为独立 CLI 把单张图渲染成整图流式动画）。

跑测试：

```bash
<ENV_PY> -m pytest tests/ -q     # 需要 pytest；无 opencv 的环境会自动跳过渲染用例
node tests/preview_html.test.mjs # 预览台逻辑（可选，需 node）
```

## 贡献

欢迎提交 Issue 或 Pull Request。任何涉及绘制逻辑的改动，都应使用真实的字幕、标注和成片检查遮罩保护、时序与最终画面。

## 致谢与第三方内容

线稿阶段的视觉语言来自 [ian-xiaohei-illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations)（作者
[Ian](https://github.com/helloianneo)，MIT）。本仓库以风格包形式收录了其 `references/` 参考文档，
并针对白板动画管线做了三处覆盖（纸底改暖黄、画面禁止文字、保留确认关卡）。
署名、vendoring 范围与改动说明见 [`styles/ian-xiaohei/NOTICE.md`](styles/ian-xiaohei/NOTICE.md)，
上游许可见 [`styles/ian-xiaohei/LICENSE`](styles/ian-xiaohei/LICENSE)。角色「小黑」是 Ian 视觉语言的一部分。

## 许可证

本项目基于 MIT License 开源，详见 [LICENSE](LICENSE)。

## 关于作者

一个爱养鱼的老登 / AI Builder / 用 AI 团队打造一人公司。

抖音、B站、公众号：江哥是老登啊
