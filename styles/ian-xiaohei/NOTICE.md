# Notice — 小黑风格包（vendored）

本目录是 **[ian-xiaohei-illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations)** 的
局部 vendored 副本，作者 **Ian**，以 MIT 许可分发（见本目录 `LICENSE`）。
`srt-whiteboard-animation` 用它作为线稿生成阶段的默认视觉语言。

## 取自上游的文件

- `references/style-dna.md`
- `references/xiaohei-ip.md`
- `references/composition-patterns.md`
- `references/prompt-template.md`
- `references/qa-checklist.md`

以上文件均为原文内容，**唯一的改动**是在每个文件开头加了一段「本仓库适配说明」横幅，
指向本目录 `README.md` 里的覆盖规则——否则单独阅读某个参考文件的 agent 会按上游的
「纯白背景 / 图内中文批注」出图，而那两条在白板动画管线里会导致渲染失败或违反本仓库规范。

## 未取的文件

上游的营销 README、示例配图 PNG（`assets/examples/`、`examples/images/`）、
微信二维码图片、上游 `SKILL.md` 与 `agents/openai.yaml` 均未收录：
体积大、或与本仓库的工作流（确认关卡、SRT 分幕）冲突。
需要做风格校准时请直接访问上游仓库查看示例图。

## 本仓库新增（非上游内容）

- `README.md`：风格包说明与覆盖规则。
- `whiteboard-prompt-template.md`：融合后的出图提示词模板（暖黄纸底、无图内文字、可分区）。

## 署名

角色「小黑」是 Ian 视觉语言的一部分。再分发或二次改编时请保留
`Ian Xiaohei Illustrations` 名称或在文档中标注 Ian 的署名。

- GitHub: <https://github.com/helloianneo>
- Website: <https://www.ianneo.xyz/opc>
- X/Twitter: <https://x.com/ianneo_ai>

上游 commit 抓取时间：2026-08-23（上游 `pushed_at` 2026-06-03）。
