"""
小黑风格包融合的守护测试。

覆盖三件事：
  1. SKILL.md / README.md 确实把线稿阶段的默认视觉语言定成小黑；
  2. 文档里的相对链接都能落到真实文件（融合引入了大量交叉链接）；
  3. vendored 风格包保留了署名，且冲突项有覆盖说明。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STYLE = REPO / "styles" / "ian-xiaohei"
SKILL = (REPO / "SKILL.md").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")

# 文档里出现的相对链接（跳过 http(s) 与纯锚点）
LINK = re.compile(r"\[[^\]]+\]\((?!https?://|#)([^)\s]+)\)")


def _step_two() -> str:
    """截出 SKILL.md 工作流的第 2 步文本。"""
    match = re.search(r"\n2\. \*\*生成线稿.*?(?=\n3\. \*\*)", SKILL, re.S)
    assert match, "SKILL.md 里找不到工作流第 2 步"
    return match.group(0)


# ──────────────────────────────────────────────────────────────
# 1) 第 2 步必须要求小黑
# ──────────────────────────────────────────────────────────────
def test_skill_step_two_requires_xiaohei():
    step = _step_two()
    assert "小黑" in step
    assert "styles/ian-xiaohei/whiteboard-prompt-template.md" in step
    assert "承担核心动作" in step


def test_skill_step_two_forbids_text_and_pure_white():
    step = _step_two()
    assert "不得生成任何文字" in step
    assert "纯白" in step          # 明确禁止纯白底


def test_skill_visual_spec_is_xiaohei_not_notion_doodle():
    spec = re.search(r"## 统一出图视觉规范（强制）(.*?)\n## ", SKILL, re.S)
    assert spec, "找不到视觉规范章节"
    body = spec.group(1)
    assert "小黑" in body
    assert "#F5EBD7" in body
    assert "Notion" not in body, "旧的 Notion 涂鸦规范应已被小黑规范取代"


def test_skill_frontmatter_and_params_mention_xiaohei():
    frontmatter = SKILL.split("---")[1]
    assert "小黑" in frontmatter, "description 要让 agent 一眼看到默认风格"
    params = re.search(r"## 默认实现参数(.*?)\n## ", SKILL, re.S).group(1)
    assert "视觉 IP" in params and "小黑" in params


def test_readme_documents_style_pack():
    assert "小黑" in README
    assert "styles/ian-xiaohei" in README
    assert "helloianneo/ian-xiaohei-illustrations" in README
    assert "致谢" in README


def test_confirmation_gates_are_intact():
    """融合不能顺手拿掉确认关卡（上游恰好要求"不要停下来等确认"）。"""
    assert "## 确认关卡（强制）" in SKILL
    assert "每一步完成后都必须停止并等待用户明确确认" in SKILL
    assert SKILL.count("等待用户确认") >= 5


# ──────────────────────────────────────────────────────────────
# 2) 链接可达
# ──────────────────────────────────────────────────────────────
def _doc_files() -> list[Path]:
    docs = [REPO / "README.md", REPO / "SKILL.md"]
    docs += sorted(STYLE.rglob("*.md"))
    return docs


def test_all_relative_links_resolve():
    broken: list[str] = []
    for doc in _doc_files():
        text = doc.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            path = (doc.parent / target.split("#")[0]).resolve()
            if not path.exists():
                broken.append(f"{doc.relative_to(REPO)} -> {target}")
    assert not broken, "存在断链:\n" + "\n".join(broken)


def test_style_pack_files_exist():
    for name in (
        "README.md", "NOTICE.md", "LICENSE", "whiteboard-prompt-template.md",
        "references/style-dna.md", "references/xiaohei-ip.md",
        "references/composition-patterns.md", "references/prompt-template.md",
        "references/qa-checklist.md",
    ):
        assert (STYLE / name).exists(), f"风格包缺 {name}"


# ──────────────────────────────────────────────────────────────
# 3) 署名与覆盖说明
# ──────────────────────────────────────────────────────────────
def test_attribution_is_present():
    notice = (STYLE / "NOTICE.md").read_text(encoding="utf-8")
    license_text = (STYLE / "LICENSE").read_text(encoding="utf-8")
    assert "MIT" in license_text and "Ian" in license_text
    assert "helloianneo/ian-xiaohei-illustrations" in notice
    assert "小黑" in notice


def test_vendored_references_carry_adaptation_banner():
    """单独读某个参考文件的 agent 必须能看到覆盖说明，否则会照上游出纯白+文字。"""
    for reference in sorted((STYLE / "references").glob("*.md")):
        head = reference.read_text(encoding="utf-8")[:600]
        assert "本仓库适配说明" in head, f"{reference.name} 缺适配横幅"
        assert "暖米黄" in head or "不是纯白" in head
        assert "不写任何文字" in head or "无图内文字" in head


def test_override_table_covers_the_three_conflicts():
    pack = (STYLE / "README.md").read_text(encoding="utf-8")
    assert "覆盖规则" in pack
    assert "#F5EBD7" in pack and "纯白" in pack        # 背景
    assert "不得出现任何文字" in pack                   # 图内文字
    assert "确认关卡" in pack                          # 流程
    assert "SRT 分幕" in pack                          # 张数依据


def test_prompt_template_is_whiteboard_ready():
    template = (STYLE / "whiteboard-prompt-template.md").read_text(encoding="utf-8")
    assert "#F5EBD7" in template
    assert "ABSOLUTELY NO TEXT" in template
    assert "小黑" in template
    assert "non-overlapping rectangle" in template     # 可分区约束
    assert "NOT pure white" in template


# ──────────────────────────────────────────────────────────────
# 4) 渲染器：实心墨块开关默认关闭（不改变既有画面）
# ──────────────────────────────────────────────────────────────
def test_solid_ink_default_is_off_and_flag_exists():
    import pytest

    pytest.importorskip("cv2", reason="需要 opencv-python")
    sys.path.insert(0, str(REPO / "scripts"))
    import stream_render as sr

    assert sr.Config().solid_ink_gray == 0, "默认必须关闭，否则既有成片会变"
    for script in ("render_stream_whiteboard.py", "stream_render.py"):
        text = (REPO / "scripts" / script).read_text(encoding="utf-8")
        assert "--solid-ink-gray" in text, f"{script} 缺 CLI 开关"


def test_solid_ink_fills_solid_black_areas():
    import numpy as np
    import pytest

    cv2 = pytest.importorskip("cv2", reason="需要 opencv-python")
    sys.path.insert(0, str(REPO / "scripts"))
    import stream_render as sr

    # 暖黄纸底 + 一块实心黑（模拟小黑的身体）
    image = np.full((240, 320, 3), (215, 235, 245), np.uint8)
    cv2.circle(image, (160, 120), 60, (20, 20, 20), -1)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10
    )
    solid = gray < 60

    off_map, off_cut = sr.build_ink_maps(thresh, gray, sr.Config())
    on_map, on_cut = sr.build_ink_maps(thresh, gray, sr.Config(solid_ink_gray=90))

    off_cover = ((off_map < off_cut) & solid).sum() / solid.sum()
    on_cover = ((on_map < on_cut) & solid).sum() / solid.sum()
    assert off_cover < 0.5, "默认行为应保持原样（实心内部被判成背景）"
    assert on_cover > 0.95, "开启后实心黑应整块算作墨迹"
    # 线条处仍然是纯黑，实心处取自身墨色（不能画成白色）
    assert on_map[solid].max() <= 90


# ──────────────────────────────────────────────────────────────
# 用户点名的三条规则：文字例外 / 幕间过渡 / 卡点不靠加速
# ──────────────────────────────────────────────────────────────
def test_title_and_bullets_are_the_only_text_exception():
    spec = re.search(r"## 统一出图视觉规范（强制）(.*?)\n## ", SKILL, re.S).group(1)
    assert "唯一例外" in spec, "标题+要点必须写成点名的例外"
    assert "标题" in spec and "要点" in spec
    assert "水印" in spec, "仍要禁止水印/随意标签/英文 UI"
    # 手写文字区自己的章节
    assert "## 手写文字区（标题 + 要点）" in SKILL
    section = SKILL.split("## 手写文字区（标题 + 要点）")[1].split("\n## ")[0]
    assert '"type": "text"' in section
    assert "不要烤进出图" in section or "不要烤进" in section
    assert "不重叠" in section, "文字区必须与绘制区分开"
    assert "SRT_WB_TEXT_FONT" in section or "--text-font" in section


def test_scene_transition_rule_is_documented():
    step = re.search(r"\n7\. \*\*多幕合并.*?(?=\n8\. )", SKILL, re.S)
    assert step, "找不到第 7 步"
    body = step.group(0)
    assert "禁止硬切回空白画布" in body
    assert "停留" in body and "擦除" in body
    assert "--timeline-out" in body
    params = re.search(r"## 默认实现参数(.*?)\n## ", SKILL, re.S).group(1)
    assert "幕间过渡" in params


def test_cadence_rule_prefers_longer_picture_over_atempo():
    params = re.search(r"## 默认实现参数(.*?)\n## ", SKILL, re.S).group(1)
    assert "旁白卡点" in params and "extend" in params
    quality = SKILL.split("## 质量检查")[1]
    assert "旁白已开口、画布还空" in quality
    assert "没有被 atempo 加速" in quality


def test_readme_documents_the_three_changes():
    assert "标题 + 2–4 条要点" in README
    assert "不闪回空白画布" in README or "不硬切回空白画布" in README
    assert "不用变速把人声催快" in README or "而不是把人声催快" in README
    assert "drawing-hand-v2.png" in README, "重画版手部素材的接管方式要写进文档"


# ──────────────────────────────────────────────────────────────
# 开场封面：必须是 Skill 的默认步骤，而不是事后拼片头
# ──────────────────────────────────────────────────────────────
def test_cover_is_a_documented_default_step():
    assert "## 开场封面（默认必做）" in SKILL
    section = SKILL.split("## 开场封面（默认必做）")[1].split("\n## ")[0]
    assert "make_cover.py" in section
    assert "--no-cover" in section, "要写清怎么跳过"
    assert "不许有任何文字" in section or "图内同样不许" in section
    assert "手写" in section and "不" in section  # 标题手写、不烤进出图
    assert "4–6 秒" in section
    params = re.search(r"## 默认实现参数(.*?)\n## ", SKILL, re.S).group(1)
    assert "开场封面" in params


def test_cover_wired_into_workflow_steps():
    """第 2 步出封面分镜、第 6 步渲封面、第 7 步 --cover 接到最前。"""
    step_two = re.search(r"\n2\. \*\*生成线稿.*?(?=\n3\. \*\*)", SKILL, re.S).group(0)
    assert "封面" in step_two
    step_six = re.search(r"\n6\. \*\*命令行渲染成片.*?(?=\n7\. )", SKILL, re.S).group(0)
    assert "封面" in step_six
    step_seven = re.search(r"\n7\. \*\*多幕合并.*?(?=\n8\. )", SKILL, re.S).group(0)
    assert "--cover" in step_seven and "--no-cover" in step_seven


def test_seam_rule_requires_inked_target():
    step_seven = re.search(r"\n7\. \*\*多幕合并.*?(?=\n8\. )", SKILL, re.S).group(0)
    assert "已经有墨" in step_seven
    assert "seam-ink-ratio" in step_seven
    quality = SKILL.split("## 质量检查")[1]
    assert "已经有墨" in quality and "闪回空白" in quality
    assert "封面" in quality


def test_readme_documents_cover():
    assert "make_cover.py" in README
    assert "开场封面" in README and "--no-cover" in README
