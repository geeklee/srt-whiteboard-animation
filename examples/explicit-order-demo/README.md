# 显式顺序绘制样片

这是一份自绘几何线稿，不含品牌、商标或私有素材：右侧是太阳，左侧是小山。它用来说明两件不同的事：

1. **区域按序**（`elementOrder: ["sun", "hill"]`）——先揭示太阳，再揭示小山。如果只按画面从左到右或只按 JSON 文件里的元素排列，小山会先出现；本样片故意把 `hill` 写在文件前面，且设 `hill.startMs=0`、`sun.startMs=200`；默认按时间也会先画山，只有 `elementOrder` 才会纠正成「先太阳后山」。`startMs` 是最早开始约束：太阳从 200ms 开始，画 1800ms 后，山实际从 2000ms 开始（不是 0ms 并发）。
2. **逐笔路径按序**（`strokePaths`）——太阳从右侧落笔、顺时针画圆，再按东→南→西→北射出光线；小山从右下角起笔，经山顶到左下角后闭合底边。这与预览代理的 `handPath`（只是一条从上到下的直线）以及自动 `grid`/`skeleton` 路径都不是一回事。

落墨和笔尖共用同一条采样时间线。成片渲染时加 `--tip-log`，日志里的 `(x, y)` 就是该帧笔尖位置，应落在当前已揭开的笔迹上。

## 源文件

| 文件 | 说明 |
|---|---|
| `scene-explicit-order.png` | 暖米黄底线稿（960×540，`#F5EBD7`） |
| `scene-explicit-order.annotation.json` | 含 `elementOrder` 与 `strokePaths` 的标注 |
| `scene-explicit-order-whiteboard.mp4` | 成片 |
| `scene-explicit-order-preview.png` | 区域编号 + 真实笔顺箭头检查图 |
| `tip-log.json` | 每帧笔尖坐标 |
| `frames/` | 从成片抽取的核对帧 |
| `proof.json` | 含成片/标注/日志 SHA-256 的可复现像素核验结果 |
| `verify_sample.py` | 用相同 CLI 临时重渲染无手版，排除把笔尖本身误判为墨迹 |

复原源图与标注：

```bash
<ENV_PY> examples/explicit-order-demo/build_source.py
```

渲染（输出尺寸与画布 1:1，便于对照坐标）：

```bash
<ENV_PY> scripts/render_stream_whiteboard.py \
  examples/explicit-order-demo/scene-explicit-order.png \
  examples/explicit-order-demo/scene-explicit-order.annotation.json \
  examples/explicit-order-demo/scene-explicit-order-whiteboard.mp4 \
  assets/drawing-hand.png \
  --cap-long-edge 960 --fps 30 --tip-log examples/explicit-order-demo/tip-log.json
```

旧标注只要不写这两个新字段，行为与原来完全相同：区域仍按 `startMs` 排序，区内仍走 `--ink-path grid` 或 `skeleton`。

## 核对结果（2026-11-14 / Asia/Shanghai，独立复核后重渲染）

成片 960×540、30 fps、126 帧。`proof.json` 中 15 项检查全部通过（其中逐帧检查 66 个起笔帧的笔尖与墨迹相交）。像素检查来自无手遮挡版本，而非手持笔的黑色像素；两版的 tip-log 完全一致。复验并重抽下面的成片帧：

```bash
<ENV_PY> examples/explicit-order-demo/verify_sample.py
```



| 帧 | 时间 | 看到的内容 |
|---|---|---|
| `frames/00-blank.png` | 0 ms | 只有纸张，尚未露线 |
| `frames/01-sun-start.png` | 200 ms | 笔尖落在太阳右侧（772, 160），小山完全没有出现 |
| `frames/02-sun-mid-circle.png` | 433 ms | 圆弧已顺时针画过南侧，笔尖贴在已揭墨迹上；小山仍隐藏 |
| `frames/03-sun-rays.png` | 1000 ms | 开始画由中心射出的光芒 |
| `frames/04-hill-start.png` | 2000 ms | 太阳已画完；笔尖落到小山右下角（380, 420），三角形尚未展开 |
| `frames/05-hill-mid.png` | 2333 ms | 已从右下角翻到山顶附近，笔尖贴着当前墨迹 |
| `frames/06-final.png` | 4167 ms | 完整画面 |

`scene-explicit-order-preview.png` 按 `elementOrder` 编号：太阳为 1、小山为 2（尽管小山在画面左侧、且写在 JSON 数组前面），并画出真实笔顺箭头，而不是 `handPath` 的上下直线。

注：显式路径模式的添彩仅着色已经沿路径揭开的墨迹，凝视阶段不会突然补全路径未覆盖的源图内容。网页预览依然是矩形布局代理，不能作为真实逐笔揭墨或末帧证据；应以本目录视频、tip-log 与无手像素核验为准。

## 视觉复核补充：顶部形状与十字线

源图的太阳顶部是**平头北向直线与圆环的交点**，没有专门设计的箭头或独立弯钩。逐帧对照无手版与源图，顶部区域（x=705..735、y=50..124）没有超出源墨迹 2 像素边缘容差的新增暗像素；局部像小钩/箭头的观感来自交点及栅格边缘，而不是新增绘制路径。此结果不保证编码后每个边缘像素与 PNG 完全相同。

内部十字由四条有方向的路径依次从中心向东、南、西、北揭示。验证器逐帧检查各方向距中心 15、30、70、90 像素的墨迹首次出现帧（从 0 开始）：

| 方向 | 首次出现帧（近→远） |
|---|---|
| 东 | 25、26、27、28 |
| 南 | 29、30、31、32 |
| 西 | 33、34、36、37 |
| 北 | 38、38、40、41 |

各线分多个帧向外增长，没有整条线瞬间出现。30fps 的帧采样和揭墨半径可能让相邻采样点同帧出现；圆环与射线的交叉墨迹也可能在先画圆环时露出一个小交点。这是**源图墨迹按路径半径揭示**的边界，不是分层矢量笔画隔离，也不等于真实彩铅引擎。

`tip-log.json`、`frames/` 为本地生成的核验产物，不纳入提交；先按上面的渲染命令生成日志，再运行验证器即可复原。
