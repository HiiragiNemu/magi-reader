#!/usr/bin/env python3
"""Reclassify preservation portal membership using strong structural signals.

The initial crawler used broad full-text keywords, which caused generic phrases
such as “魔法少女” to place songs and events inside the character portal.  This
postprocessor uses MediaWiki categories, namespaces and narrowly scoped title
signals. It rewrites only portal labels/counts; article content is untouched.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

PORTAL_TITLES = {
    "characters": "魔法少女与人物",
    "story": "剧情与活动",
    "memoria": "记忆结晶与道具",
    "doppel": "Doppel、魔女与传言",
    "system": "游戏与战斗系统",
    "world": "世界观与术语",
    "media": "动画、音乐与出版物",
    "technical": "模板与技术档案",
}

PORTAL_KEYWORDS = {
    "characters": ["登场角色", "魔法少女", "人物", "组织"],
    "story": ["剧情", "活动", "主线", "支线"],
    "memoria": ["记忆结晶", "素材", "道具", "商店"],
    "doppel": ["Doppel", "魔女", "使魔", "传言", "谣"],
    "system": ["战斗系统", "游戏系统", "攻略"],
    "world": ["世界观", "地点", "术语", "时间线"],
    "media": ["歌曲", "动画", "漫画", "广播", "出版物"],
    "technical": ["模板", "模块", "帮助", "维护", "规范"],
}

TECHNICAL_NAMESPACES = {4, 8, 10, 12, 14, 828}


def has_any(value: str, words: tuple[str, ...]) -> bool:
    folded = value.casefold()
    return any(word.casefold() in folded for word in words)


def classify(item: dict[str, Any]) -> list[str]:
    title = str(item.get("title") or "")
    namespace = int(item.get("namespace") or 0)
    categories = {str(value) for value in item.get("categories") or []}
    category_text = " ".join(sorted(categories))
    headings = " ".join(str(value.get("text") or "") for value in item.get("headings") or [])
    portals: set[str] = set()

    # Technical namespaces are structural by definition and should not leak
    # into user-facing subject portals merely because their examples mention
    # game terms.
    if namespace in TECHNICAL_NAMESPACES:
        portals.add("technical")
        return sorted(portals)

    if (
        "魔法纪录登场角色" in categories
        or "魔法少女" in categories
        or "魔法少女组织" in categories
        or any(category.endswith("属性魔法少女") for category in categories)
        or any(category.endswith("星魔法少女") for category in categories)
        or has_any(title, ("人物列表", "角色列表", "组织列表"))
    ):
        portals.add("characters")

    if (
        "魔法纪录活动" in categories
        or any(category.endswith("活动") for category in categories)
        or any("剧情" in category for category in categories)
        or has_any(title, ("主线剧情", "支线剧情", "活动剧情", "魔法少女剧情", "镜界剧情", "特别剧情"))
    ):
        portals.add("story")

    if (
        "记忆结晶" in categories
        or has_any(title, ("记忆结晶", "素材", "道具", "商店", "觉醒材料", "精神强化素材"))
        or has_any(category_text, ("素材", "道具"))
    ):
        portals.add("memoria")

    if (
        categories.intersection({"魔女", "谣", "传言"})
        or has_any(title, ("Doppel", "ドッペル", "魔女", "使魔", "传言", "谣", "魔女文字", "符文"))
        or has_any(category_text, ("Doppel", "魔女", "使魔", "传言", "谣"))
    ):
        portals.add("doppel")

    if (
        categories.intersection({"魔法纪录战斗系统", "魔法纪录游戏系统", "攻略文章"})
        or has_any(title, ("战斗系统", "游戏系统", "属性克制", "伤害计算", "MP计算", "Connect", "Magia", "行动盘", "镜层", "关卡机制"))
    ):
        portals.add("system")

    if (
        categories.intersection({"魔法纪录歌曲", "魔法纪录动画", "魔法少女小圆歌曲"})
        or has_any(title, ("动画", "漫画", "歌曲", "音乐", "广播", "画集", "设定集", "Magia Report", "マギアレコード公式"))
    ):
        portals.add("media")

    if (
        categories.intersection({"神滨市", "二木市"})
        or has_any(category_text, ("世界观", "地点", "术语", "时间线"))
        or has_any(title, ("世界观", "术语", "时间线", "神滨市", "二木市", "魔法少女系统", "灵魂宝石", "丘比"))
    ):
        portals.add("world")

    if (
        has_any(category_text, ("模板", "维护", "社区规范", "帮助", "翻译"))
        or has_any(title, ("编辑指南", "翻译规范", "模板总览", "帮助总览", "条目总览"))
    ):
        portals.add("technical")

    # Pages with no strong subject signal remain available in “全部保存内容”.
    return sorted(portals)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Static snapshot root containing data/")
    args = parser.parse_args()
    root = args.root.resolve()
    data = root / "data"
    archive_path = data / "archive-index.json"
    portal_path = data / "portal-index.json"

    archive = json.loads(archive_path.read_text(encoding="utf-8-sig"))
    counts: Counter[str] = Counter()
    for item in archive:
        item["portals"] = classify(item)
        counts.update(item["portals"])

    portals = [
        {
            "id": portal_id,
            "title": title,
            "count": counts[portal_id],
            "keywords": PORTAL_KEYWORDS[portal_id],
        }
        for portal_id, title in PORTAL_TITLES.items()
    ]

    archive_path.write_text(json.dumps(archive, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    portal_path.write_text(json.dumps(portals, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(json.dumps({"pages": len(archive), "portalCounts": dict(counts)}, ensure_ascii=False, indent=2))
    if counts["characters"] < 100:
        raise RuntimeError(f"character portal unexpectedly small: {counts['characters']}")
    if counts["characters"] > len(archive) * 0.75:
        raise RuntimeError(f"character portal still too broad: {counts['characters']}/{len(archive)}")
    if counts["story"] < 50:
        raise RuntimeError(f"story portal unexpectedly small: {counts['story']}")


if __name__ == "__main__":
    main()
