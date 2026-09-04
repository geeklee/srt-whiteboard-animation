"""SRT 解析与分镜建议（scripts/parse_srt.py）的单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from parse_srt import group_scenes, parse_srt  # noqa: E402

SAMPLE = """﻿1
00:00:00,000 --> 00:00:04,500
小猴子坐在山顶

2
00:00:04.500 --> 00:00:09,000
大猴子冲过来抢香蕉


3
00:00:09,000 --> 00:00:12,000
小朋友们都笑了
"""


def test_parse_cues_handles_bom_dot_and_blank_lines():
    cues = parse_srt(SAMPLE)
    assert [c["index"] for c in cues] == [1, 2, 3]
    assert cues[0]["startMs"] == 0 and cues[0]["endMs"] == 4500
    assert cues[1]["startMs"] == 4500          # 点号毫秒分隔也要认
    assert cues[2]["text"] == "小朋友们都笑了"
    assert all(c["durMs"] > 0 for c in cues)


def test_parse_cues_ignores_blocks_without_timecode():
    cues = parse_srt("这是一段说明文字\n\n1\n00:00:01,000 --> 00:00:02,000\n正文\n")
    assert len(cues) == 1
    assert cues[0]["text"] == "正文"


def test_multiline_text_is_joined():
    cues = parse_srt("1\n00:00:00,000 --> 00:00:02,000\n第一行\n第二行\n")
    assert cues[0]["text"] == "第一行 第二行"


def test_group_scenes_breaks_near_target():
    cues = [
        {"index": i + 1, "startMs": i * 8000, "endMs": (i + 1) * 8000,
         "durMs": 8000, "text": f"第{i + 1}句"}
        for i in range(10)
    ]
    scenes = group_scenes(cues, target_sec=30, min_sec=25, max_sec=35)
    assert [s["sceneIndex"] for s in scenes] == list(range(1, len(scenes) + 1))
    # 每条字幕都必须落进恰好一幕，不能丢也不能重复
    covered = [i for s in scenes for i in range(s["cueRange"][0], s["cueRange"][1] + 1)]
    assert covered == list(range(1, 11))
    assert all(s["sceneDurationMs"] == s["endMs"] - s["startMs"] for s in scenes)
    # 除末幕外都应落在 target 附近（不超过 max）
    for scene in scenes[:-1]:
        assert 25_000 <= scene["sceneDurationMs"] <= 35_000


def test_group_scenes_last_scene_may_be_shorter_than_min():
    """已知行为：末幕不受 --min-sec 保护，文档里要如实说明。"""
    cues = [
        {"index": i + 1, "startMs": i * 8000, "endMs": (i + 1) * 8000,
         "durMs": 8000, "text": "x"}
        for i in range(10)
    ]
    scenes = group_scenes(cues, target_sec=30, min_sec=25, max_sec=35)
    assert scenes[-1]["sceneDurationMs"] < 25_000


def test_single_overlong_cue_becomes_its_own_scene():
    """已知行为：单条字幕本身超过 max 时不会被切开。"""
    cues = [
        {"index": 1, "startMs": 0, "endMs": 40_000, "durMs": 40_000, "text": "很长"},
        {"index": 2, "startMs": 40_000, "endMs": 45_000, "durMs": 5_000, "text": "短"},
    ]
    scenes = group_scenes(cues, target_sec=30, min_sec=25, max_sec=35)
    assert len(scenes) == 2
    assert scenes[0]["sceneDurationMs"] == 40_000


def test_group_scenes_on_empty_input():
    assert group_scenes([], 30, 25, 35) == []
