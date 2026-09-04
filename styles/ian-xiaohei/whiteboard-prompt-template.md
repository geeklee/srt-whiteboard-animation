# 出图提示词模板（小黑 × 白板动画融合版）

每幕单独生成一张 16:9 图，不要把多幕拼进一张。
变量按当前幕的字幕内容替换；方括号里的说明不要写进提示词。

与上游模板的差别只有三处：**纸底不是纯白**、**画面内不写任何文字**、**主体之间要留可分区的空白走廊**。
其余（小黑承担核心动作、原创隐喻、克制留白、禁忌清单）完全沿用上游。

## 主模板

```text
Generate one standalone 16:9 horizontal hand-drawn illustration for a whiteboard animation.

Visual DNA:
Warm beige aged-paper background, exact color #F5EBD7 — a calm off-white paper tone, NOT pure white.
Minimalist black hand-drawn line art with slightly wobbly pen lines. Lots of empty space.
Clean, absurd, low-tech product-sketch feeling.
No gradients, no drop shadows, no paper grain or noise texture, no vignette, no complex background,
no commercial vector style, no PPT infographic look, no cute mascot poster, no children's illustration,
no realistic UI, no photographic detail, no 3D rendering.

ABSOLUTELY NO TEXT anywhere in the image:
no Chinese characters, no letters, no numbers, no labels, no captions, no titles, no signage,
no handwriting, no watermarks. The narration is carried by subtitles outside the image.
Express every idea through drawn objects, postures and arrows only.

Recurring IP character required:
小黑 (Xiaohei), a small solid-black absurd creature: filled black body, two white dot eyes,
thin spindly legs (occasionally thin arms), blank deadpan serious expression, slightly uneven
hand-drawn silhouette. Body may read as a cylinder, black bean, black box, funnel, shadow or hole.
小黑 must PERFORM the core conceptual action, not stand beside the scene as decoration.
Serious, deadpan, slightly bizarre — never cute, never a mascot, no costumes, no shiny eyes.

Theme:
{这一幕的主题}

Structure type:
{结构类型：Workflow / 系统局部 / 前后对比 / 角色状态 / 概念隐喻 / 方法分层 / 地图路线 / 小漫画分镜}

Core idea:
{这一幕字幕要表达的核心意思，一句话}

Composition:
{具体画面：小黑在哪里、正在做什么、主要物件是什么、信息如何流动}

Suggested elements:
{元素1} / {元素2} / {元素3}   [1-2 个低科技物件为主，不要堆满]

Color use:
Black for all line art and 小黑. Sparse orange only for the main flow/path/arrows.
Sparse red only for a key problem or result. Sparse blue only for a secondary/system state.
Color appears as strokes, arrows or small filled shapes — never as text. Restrained: less is better.

Whiteboard animation constraints (important):
Draw {N} clearly separated subjects, laid out left to right in narrative order, one per subtitle beat.
Each subject must fit inside its own axis-aligned rectangle that does NOT overlap the other subjects'
rectangles — leave a visible empty corridor of paper between neighbours. Subjects must not interlock,
overlap or share outlines.
Keep all four corners of the canvas as clean empty paper.
Use confident mid-weight black strokes, not faint hairlines or light grey.
Main subjects should occupy roughly 40%-60% of the canvas; keep at least 35% empty paper.

Constraints:
One image explains only one core structure. Do not write a title. Do not draw a frame or border around
the canvas. Do not copy known example compositions — invent a fresh, strange but valid metaphor for
this specific content. Clear but not instructional, interesting but not childish, strange but clean.
```

## 变量填写要点

- **`{N}`**：该幕的绘制区域数，通常 2–4，与该幕的字幕事件数一致。
- **结构类型**：从 [references/composition-patterns.md](references/composition-patterns.md) 里挑**一种**，不要混。
- **Composition**：必须明确写出「小黑在做什么」这个动作。判据见 [references/xiaohei-ip.md](references/xiaohei-ip.md)：
  去掉小黑后隐喻还完全成立，就说明小黑是装饰，要重写。
- **原创隐喻**：用三步法（抽象概念 → 物理动作 → 低科技物件 → 小黑承担动作），
  不要复用「传送带断点 / 素材鱼 / 盖章工具箱」等上游已有构图。

## 改图提示词

主体粘在一起、没法分区时：

```text
Edit the provided image. Keep the same metaphor, characters and line style, but push the {某个主体}
further {left/right} so that each subject sits inside its own non-overlapping rectangle with a clear
empty paper corridor between them. Do not add any text, and keep the background exactly #F5EBD7.
```

不小心画了文字时：

```text
Edit the provided image. Remove every text element (all Chinese characters, letters, numbers and labels),
filling those areas with the same clean #F5EBD7 paper background. Preserve everything else exactly:
小黑, objects, arrows, line style, composition and aspect ratio. Do not add any new text or objects.
```

小黑变装饰时：

```text
Regenerate this illustration with the same core meaning and simple layout, but make 小黑 central to the
conceptual action — 小黑 should be doing the strange work that explains the idea, not standing beside it.
Keep it clean, sparse, hand-drawn, deadpan, not cute, warm beige #F5EBD7 paper, and no text at all.
```

底色出成纯白时：

```text
Edit the provided image. Replace the pure white background with a warm beige aged-paper tone,
exact color #F5EBD7, keeping it perfectly flat and clean — no texture, no grain, no gradient, no vignette.
Preserve all line art, 小黑 and composition exactly. Do not add any text.
```
