#!/usr/bin/env python3
"""Reflow only trusted-memory delta leaves to the Japanese JSON's @ count.

The trusted human corpus predates the current reader's exact visual line wrapping.
This tool preserves its Chinese wording and all control codes, and changes only @.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterator

ALLOWED = {
    "textLeft", "textRight", "textCenter", "narration",
    "progressNarration", "textSelect", "nameLeft", "nameRight",
    "nameCenter", "nameNarration",
}
TEXT_TAGS = {
    "textBlack", "textRed", "textBlue", "textGreen", "textYellow",
    "textWhite", "textGray", "textPurple", "textOrange",
}
TAG_RE = re.compile(r"\[([^\[\]]+)\]")
PLACEHOLDER_RE = re.compile(
    r"(?:\{[^{}]+\}|%(?:\d+\$)?[-+#0 ]*\d*(?:\.\d+)?[a-zA-Z]|\\[nrt])"
)
CLOSE = set("，。！？；：、…—～~,.!?;:）】》」』”’〉〕］｝")
OPEN = set("（【《「『“‘〈〔［｛")
NO_SPLIT = {
    "学生会长", "学生会长候选人", "候选人", "魔法少女", "见泷原", "神滨市",
    "悲叹之种", "灵魂宝石", "调整屋", "协调屋", "小圆", "小焰", "麻美学姐",
    "巴学姐", "沙耶香", "菲莉希亚", "彩羽", "伊吕波", "御魂", "丘比",
    "玛吉斯", "魔女化", "多媒体教室", "视听教室", "改变视角", "镜之魔女",
    "民间传说", "大家", "我们", "自己", "因为", "所以", "但是", "虽然",
    "如果", "而且", "然后", "已经", "还是", "能够", "不能", "不会", "没有",
    "什么", "怎么", "为什么", "真正", "一定", "终于", "果然", "突然", "现在",
    "这里", "那里", "这个", "那个", "时候", "事情", "对不起", "谢谢你",
    "没关系", "没办法", "请不要", "必须", "可能", "应该", "知道", "明白",
    "相信", "拯救", "保护", "战斗", "约定", "朋友", "前辈", "学姐", "妹妹",
    "姐姐", "哥哥", "妈妈", "爸爸", "老师", "学校", "教室", "视频", "画面",
    "镜头", "新的", "一边", "一段", "播放", "表情", "抽搐", "了不得", "自由",
    "发生", "恐惧", "痛苦", "混乱", "失踪", "踪迹", "赝品街", "搜索中心",
    "寻人启事", "走失儿童中心", "选举活动", "有效候选人", "任何人", "变强",
    "实现梦想",
}


def walk(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ALLOWED and isinstance(child, str):
                yield path + (key,), child
            yield from walk(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + (index,))


def set_path(root: Any, path: tuple[Any, ...], value: str) -> None:
    target = root
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def visible(text: str) -> str:
    return TAG_RE.sub("", text.replace("@", ""))


def signature(text: str) -> list[tuple[str, str]]:
    result = []
    for raw in TAG_RE.findall(text):
        name = raw.split(":", 1)[0]
        result.append((name, "<visible>") if name in TEXT_TAGS else (name, raw))
    return result


def raw_boundaries(base: str) -> tuple[dict[int, int], int]:
    positions = {0: 0}
    count = 0
    index = 0
    while index < len(base):
        if base[index] == "[":
            match = TAG_RE.match(base, index)
            if match:
                index = match.end()
                positions[count] = index
                continue
        index += 1
        count += 1
        positions[count] = index
    return positions, count


def existing_boundaries(text: str) -> set[int]:
    result: set[int] = set()
    count = 0
    index = 0
    while index < len(text):
        if text[index] == "[":
            match = TAG_RE.match(text, index)
            if match:
                index = match.end()
                continue
        if text[index] == "@":
            result.add(count)
            index += 1
            continue
        count += 1
        index += 1
    return result


def targets(japanese: str, chinese_length: int) -> list[float]:
    lengths = [len(TAG_RE.sub("", part)) for part in japanese.split("@")]
    total = sum(lengths)
    if not total:
        return [chinese_length * i / len(lengths) for i in range(1, len(lengths))]
    result = []
    cumulative = 0
    for length in lengths[:-1]:
        cumulative += length
        result.append(chinese_length * cumulative / total)
    return result


def splits_word(text: str, position: int) -> bool:
    low = max(0, position - 12)
    high = min(len(text), position + 12)
    for word in NO_SPLIT:
        start = text.find(word, low, high)
        while start != -1 and start < high:
            if start < position < start + len(word):
                return True
            start = text.find(word, start + 1, high)
    return False


def boundary_cost(text: str, position: int, target: float, old: set[int], previous: int) -> float:
    before = text[position - 1]
    after = text[position]
    cost = abs(position - target) * 5.0
    if position in old:
        cost -= 4.0
    if before in CLOSE:
        cost -= 18.0
    if before in "的了呢吧啊呀嘛哦啦哟者时后中上下来去着过完好":
        cost -= 2.5
    if after in "但而可所因如只再又也并于与或却才就都还那这你我他她它请让把被从向对为":
        cost -= 1.5
    if after in CLOSE or before in OPEN:
        cost += 24.0
    if before.isspace() or after.isspace():
        cost -= 5.0
    if before.isascii() and after.isascii() and before.isalnum() and after.isalnum():
        cost += 35.0
    if before.isdigit() and after.isdigit():
        cost += 35.0
    if splits_word(text, position):
        cost += 30.0
    if position - previous < 2:
        cost += 18.0
    if len(text) - position < 2:
        cost += 18.0
    return cost


def reflow(chinese: str, japanese: str) -> str:
    needed = japanese.count("@")
    if chinese.count("@") == needed:
        return chinese
    base = chinese.replace("@", "")
    if needed == 0:
        return base
    positions, length = raw_boundaries(base)
    text = visible(chinese)
    if length <= needed:
        chosen = list(range(1, length))
        while len(chosen) < needed:
            chosen.append(length)
    else:
        old = existing_boundaries(chinese)
        average = length / (needed + 1)
        states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, ())}
        for number, target in enumerate(targets(japanese, length), start=1):
            next_states: dict[int, tuple[float, tuple[int, ...]]] = {}
            remaining = needed - number
            for previous, (base_cost, selected) in states.items():
                for position in range(previous + 1, (length - 1) - remaining + 1):
                    cost = base_cost + boundary_cost(text, position, target, old, previous)
                    segment = position - previous
                    cost += max(0.0, abs(segment - average) - average * 0.75) * 1.5
                    candidate = (cost, selected + (position,))
                    current = next_states.get(position)
                    if current is None or candidate[0] < current[0]:
                        next_states[position] = candidate
            states = next_states
        best = min(
            (
                cost + max(0.0, abs((length - last) - average) - average * 0.75) * 1.5,
                selected,
            )
            for last, (cost, selected) in states.items()
        )
        chosen = list(best[1])
    result = base
    for position in sorted(chosen, reverse=True):
        raw = positions.get(position, len(result))
        result = result[:raw] + "@" + result[raw:]
    return result


def git_json(repo: Path, ref: str, path: str) -> Any:
    data = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    return json.loads(data.decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--patch-root", type=Path, required=True)
    parser.add_argument("--base-ref", required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    patch_root = args.patch_root.resolve()
    jp_root = repo / "magireco-source-master" / "Scenarios_full"
    changed_files = 0
    reflowed_fields = 0

    for patch_file in sorted(patch_root.rglob("*.json")):
        relative = patch_file.relative_to(patch_root).as_posix()
        repo_path = f"magireco-translate-data-master/Scenarios_full/{relative}"
        baseline = git_json(repo, args.base_ref, repo_path)
        patch = json.loads(patch_file.read_text(encoding="utf-8"))
        japanese = json.loads((jp_root / relative).read_text(encoding="utf-8"))
        baseline_leaves = dict(walk(baseline))
        patch_leaves = dict(walk(patch))
        jp_leaves = dict(walk(japanese))
        if baseline_leaves.keys() != patch_leaves.keys() or baseline_leaves.keys() != jp_leaves.keys():
            raise RuntimeError(f"Allowed-field structure differs: {relative}")
        file_changed = False
        for path, old_value in baseline_leaves.items():
            value = patch_leaves[path]
            if value == old_value:
                continue
            jp_value = jp_leaves[path]
            adjusted = reflow(value, jp_value)
            if adjusted.count("@") != jp_value.count("@"):
                raise RuntimeError(f"@ count still differs: {relative} {path!r}")
            if signature(adjusted) != signature(jp_value):
                raise RuntimeError(f"Control signature differs: {relative} {path!r}")
            if PLACEHOLDER_RE.findall(adjusted) != PLACEHOLDER_RE.findall(jp_value):
                raise RuntimeError(f"Placeholder sequence differs: {relative} {path!r}")
            if adjusted != value:
                set_path(patch, path, adjusted)
                reflowed_fields += 1
                file_changed = True
        if file_changed:
            patch_file.write_text(json.dumps(patch, ensure_ascii=False, indent=1), encoding="utf-8")
            changed_files += 1

    print(json.dumps({
        "status": "ok",
        "reflowed_fields": reflowed_fields,
        "changed_patch_files": changed_files,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
