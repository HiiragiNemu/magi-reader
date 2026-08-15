#!/usr/bin/env python3
"""Add exact Simplified-Chinese aliases for every residual Exedra Name label.

These aliases are grounded in the existing Chinese corpus and established
MagiReader dictionary spellings.  The workflow still performs a full fail-closed
scan afterwards; any unlisted Japanese label stops publication.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DICTIONARY = ROOT / "website/app/config/dictionary.ts"

ALIASES: dict[str, str] = {
    "キリカ之魔女": "纪里香之魔女",
    "リナ的母亲": "里奈的母亲",
    "使役する魔女": "使役魔女",
    "マチビト马": "待人马",
    "彩羽的ドッペル": "彩羽的Doppel",
    "アイ": "小爱",
    "传闻さん": "传闻小姐",
    "お菓子之魔女": "点心魔女",
    "落书き的魔女的手下_车": "涂鸦魔女的手下_车",
    "佐仓モモ": "佐仓桃",
    "お菓子的魔女的纹章": "点心魔女的纹章",
    "みさと": "未沙都",
    "すず": "小铃",
    "真尾ひみか": "真尾日美香",
    "マメジ": "豆次",
    "ひみか的弟": "日美香的弟弟",
    "ひみか的妹": "日美香的妹妹",
    "ひみか的父亲": "日美香的父亲",
    "キリカ的母亲": "纪里香的母亲",
    "加贺见まさら": "加贺见真良",
    "矢宵か的こ": "矢宵鹿乃子",
    "アネカ": "安涅卡",
    "アネカ的妹": "安涅卡的妹妹",
    "ワルプルギス的夜": "魔女之夜",
    "不审な男": "可疑男子",
    "おじいさん": "老爷爷",
    "チアリーディング部长": "啦啦队部长",
    "五十铃れん": "五十铃怜",
    "れん的父亲": "怜的父亲",
    "れん的母亲": "怜的母亲",
    "立ち耳之魔女": "立耳魔女",
    "ハコ之魔女": "箱之魔女",
    "ヨダカ": "夜鹰",
}

PAIR_RE = re.compile(
    r'"((?:\\.|[^"\\])*)"\s*:\s*"((?:\\.|[^"\\])*)"'
)


def decode(value: str) -> str:
    return json.loads(f'"{value}"')


def encode(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    source = DICTIONARY.read_text(encoding="utf-8")
    marker = "export const NAME_TRANSLATE_MAP"
    start = source.find(marker)
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise RuntimeError("NAME_TRANSLATE_MAP block is missing")

    prefix = source[:start]
    block = source[start:end]
    suffix = source[end:]
    matches = list(PAIR_RE.finditer(block))
    by_key: dict[str, list[re.Match[str]]] = {}
    for match in matches:
        by_key.setdefault(decode(match.group(1)), []).append(match)

    replacements: list[tuple[int, int, str]] = []
    missing: list[tuple[str, str]] = []
    for key, value in ALIASES.items():
        found = by_key.get(key, [])
        if len(found) > 1:
            raise RuntimeError(f"Duplicate dictionary key before repair: {key!r}")
        if not found:
            missing.append((key, value))
            continue
        match = found[0]
        current = decode(match.group(2))
        if current == value:
            continue
        replacements.append(
            (
                match.start(),
                match.end(),
                f"{encode(key)}: {encode(value)}",
            )
        )

    for left, right, replacement in sorted(replacements, reverse=True):
        block = block[:left] + replacement + block[right:]

    if missing:
        lines = [
            "",
            "  // Residual Exedra JSON Name labels: exact canonical Chinese aliases.",
        ]
        for key, value in missing:
            lines.append(f"  {encode(key)}: {encode(value)},")
        block += "\n".join(lines)

    DICTIONARY.write_text(
        prefix + block + suffix,
        encoding="utf-8",
        newline="\n",
    )

    repaired = DICTIONARY.read_text(encoding="utf-8")
    repaired_block = repaired[
        repaired.find(marker):repaired.find("\n};", repaired.find(marker))
    ]
    parsed = {
        decode(match.group(1)): decode(match.group(2))
        for match in PAIR_RE.finditer(repaired_block)
    }
    mismatches = {
        key: parsed.get(key)
        for key, value in ALIASES.items()
        if parsed.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"Residual alias verification failed: {mismatches}")

    print(
        "EXEDRA_RESIDUAL_NAME_ALIASES_APPLIED "
        f"aliases={len(ALIASES)} updated={len(replacements)} added={len(missing)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
