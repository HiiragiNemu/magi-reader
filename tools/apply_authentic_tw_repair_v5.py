#!/usr/bin/env python3
"""Expand the canonical Exedra speaker dictionary and mixed-label resolver."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DICTIONARY = ROOT / "website/app/config/dictionary.ts"
MODULE = ROOT / "tools/tw_authentic_scenario.py"

ALIASES: dict[str, str] = {
    # Canonical characters and mixed Traditional/Simplified + kana variants.
    "いろはちゃん": "小彩羽",
    "美树さやか": "美树沙耶香",
    "美樹さやか": "美树沙耶香",
    "环いろは": "环彩羽",
    "環いろは": "环彩羽",
    "环うい": "环忧",
    "環うい": "环忧",
    "爱生まばゆ": "爱生眩",
    "愛生まばゆ": "爱生眩",
    "御园かりん": "御园花凛",
    "御園かりん": "御园花凛",
    "アシュリー": "阿什莉",
    "アルティメットまどか": "终极圆",
    "リズ・ホークウッド": "莉兹·霍克伍德",
    "リズ･ホークウッド": "莉兹·霍克伍德",
    "鹿目タツヤ": "鹿目达也",
    "人见リナ": "人见莉奈",
    "人見リナ": "人见莉奈",
    "キュぅべえ": "丘比",
    "キュゥべえたち": "丘比们",
    "キューブ": "丘布",
    # Family/relationship labels.
    "すみれの母": "堇的母亲",
    "すみれの父": "堇的父亲",
    "すみれの祖母": "堇的祖母",
    "なぎさの母": "渚的母亲",
    "まばゆの母": "眩的母亲",
    "みふゆの母": "美冬的母亲",
    "やちよの祖母": "八千代的祖母",
    "キリカの友人A": "纪里香的朋友A",
    "キリカの友人B": "纪里香的朋友B",
    "キリカの友人Ａ": "纪里香的朋友A",
    "キリカの友人Ｂ": "纪里香的朋友B",
    "呉キリカの友人A": "吴纪里香的朋友A",
    "呉キリカの友人B": "吴纪里香的朋友B",
    "呉キリカの友人Ａ": "吴纪里香的朋友A",
    "呉キリカの友人Ｂ": "吴纪里香的朋友B",
    "小乃花の元彼氏": "小乃花的前男友",
    "小乃花の友人": "小乃花的朋友",
    "幼いメリッサ": "幼年梅丽莎",
    "幼いメリッサ？": "幼年梅丽莎？",
    "過去のメリッサ？": "过去的梅丽莎？",
    "タルトの父": "塔鲁特的父亲",
    "タルトの母": "塔鲁特的母亲",
    "幼い織莉子": "幼年织莉子",
    "幼い织莉子": "幼年织莉子",
    "織莉子の母": "织莉子的母亲",
    "织莉子の母": "织莉子的母亲",
    "織莉子の伯父": "织莉子的伯父",
    "织莉子の伯父": "织莉子的伯父",
    "織莉子の父の手帳": "织莉子父亲的手账",
    "织莉子の父の手帐": "织莉子父亲的手账",
    # Generic roles, mobs and supernatural entities.
    "ウワサ小": "小型传闻",
    "チビ魔女": "小魔女",
    "チンピラＡ": "混混A",
    "チンピラＢ": "混混B",
    "チンピラA": "混混A",
    "チンピラB": "混混B",
    "ホストA": "男公关A",
    "ホストB": "男公关B",
    "ホストＡ": "男公关A",
    "ホストＢ": "男公关B",
    "女の子": "女孩",
    "男の子": "男孩",
    "子ども": "孩子",
    "不審な男": "可疑男子",
    "工場長の男": "工厂长",
    "工场长の男": "工厂长",
    "伪街の子供たち": "伪街的孩子们",
    "偽街の子供たち": "伪街的孩子们",
    "羊の魔女": "羊之魔女",
    "羊の魔女の使い魔": "羊之魔女的使魔",
    "振り子の魔女": "钟摆魔女",
    "蔷薇の魔女": "蔷薇魔女",
    "薔薇の魔女": "蔷薇魔女",
    "ハコの魔女の手下": "箱之魔女的手下",
    "うさぎのキーホルダー": "兔子钥匙扣",
    "キリカの使い魔たち": "纪里香的使魔们",
    "ひび割れたキリカのソウルジェム": "出现裂痕的纪里香灵魂宝石",
    "蒼海幇メンバーA": "苍海帮成员A",
    "蒼海幇メンバーB": "苍海帮成员B",
    "蒼海幇メンバーＡ": "苍海帮成员A",
    "蒼海幇メンバーＢ": "苍海帮成员B",
    "蒼海幇メンバーＣ": "苍海帮成员C",
    "蒼海幇メンバーＤ": "苍海帮成员D",
    "蒼海幇メンバーＥ": "苍海帮成员E",
    "蒼海幇メンバーＦ": "苍海帮成员F",
    "蒼海幇メンバーＧ": "苍海帮成员G",
    "蒼海幇メンバーＨ": "苍海帮成员H",
    # Historical/proper names retained in the source labels.
    "エイミー": "艾米",
    "オスヴァルト": "奥斯瓦尔德",
    "カトリーヌ": "卡特琳",
    "サントライユ": "桑特莱伊",
    "ザッバイ": "扎拜",
    "ナマエ": "名字",
    "フィリッポ·マリーア·ヴィスコンティ": "菲利波·马里亚·维斯康蒂",
    "フィリッポ・マリーア・ヴィスコンティ": "菲利波·马里亚·维斯康蒂",
    "ベベ": "贝贝",
    "マチビト馬": "待人马",
    "ラ·イル": "拉·海尔",
    "ラ・イル": "拉·海尔",
}

OLD_TRANSLATOR = '''def translate_speaker(value: str, mapping: dict[str, str]) -> str:
    normalized = normalize_display_punctuation(value)
    if not normalized or normalized in NARRATION_SPEAKERS:
        return "旁白"
    parts = tuple(part for part in MULTI_SPEAKER_RE.split(normalized) if part)
    if len(parts) > 1:
        return "＆".join(translate_speaker(part, mapping) for part in parts)
    return mapping.get(speaker_lookup_key(normalized), normalized)
'''

NEW_TRANSLATOR = '''EXEDRA_ADDITIONAL_SPEAKER_ALIASES = {
''' + "".join(
    f"    {json.dumps(key, ensure_ascii=False)}: "
    f"{json.dumps(value, ensure_ascii=False)},\n"
    for key, value in ALIASES.items()
) + '''}
EXEDRA_ADDITIONAL_SPEAKER_LOOKUP = {
    speaker_lookup_key(key): value
    for key, value in EXEDRA_ADDITIONAL_SPEAKER_ALIASES.items()
}
EXEDRA_RELATION_SUFFIXES = (
    ("の父の手帳", "父亲的手账"),
    ("の父の手帐", "父亲的手账"),
    ("の使い魔たち", "的使魔们"),
    ("の子供たち", "的孩子们"),
    ("の元彼氏", "的前男友"),
    ("のキーホルダー", "的钥匙扣"),
    ("のソウルジェム", "的灵魂宝石"),
    ("のメッセージ", "的信息"),
    ("の友人Ａ", "的朋友A"),
    ("の友人Ｂ", "的朋友B"),
    ("の友人A", "的朋友A"),
    ("の友人B", "的朋友B"),
    ("の使い魔", "的使魔"),
    ("の祖母", "的祖母"),
    ("の伯父", "的伯父"),
    ("の手下", "的手下"),
    ("の母", "的母亲"),
    ("の父", "的父亲"),
    ("の友人", "的朋友"),
    ("の魔女", "之魔女"),
    ("の声", "的声音"),
    ("の歌", "的歌"),
)


def _translate_speaker_component(
    value: str,
    mapping: dict[str, str],
) -> str:
    normalized = normalize_display_punctuation(value)
    key = speaker_lookup_key(normalized)
    direct = mapping.get(key) or EXEDRA_ADDITIONAL_SPEAKER_LOOKUP.get(key)
    if direct is not None:
        return direct

    punctuation = ""
    while normalized and normalized[-1] in "?？!！":
        punctuation = normalized[-1] + punctuation
        normalized = normalized[:-1]
    if punctuation:
        translated = _translate_speaker_component(normalized, mapping)
        if translated != normalized:
            return translated + punctuation

    for prefix, replacement in (
        ("ひび割れた", "出现裂痕的"),
        ("過去の", "过去的"),
        ("幼い", "幼年"),
    ):
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            return replacement + _translate_speaker_component(
                normalized[len(prefix):],
                mapping,
            )

    for suffix, replacement in EXEDRA_RELATION_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            return (
                _translate_speaker_component(
                    normalized[:-len(suffix)],
                    mapping,
                )
                + replacement
            )

    if normalized.endswith("たち") and len(normalized) > 2:
        return _translate_speaker_component(normalized[:-2], mapping) + "们"

    compact = speaker_lookup_key(normalized)
    # Replace only dictionary aliases that contain Japanese kana. This repairs
    # mixed official labels such as 美树さやか without touching ordinary Chinese.
    for alias in sorted(mapping, key=len, reverse=True):
        if alias == compact or len(alias) < 2 or JAPANESE_SCRIPT_RE.search(alias) is None:
            continue
        replacement = mapping[alias]
        if JAPANESE_SCRIPT_RE.search(replacement) is not None:
            continue
        if alias in compact:
            compact = compact.replace(alias, replacement)
    compact = (
        compact
        .replace("メンバー", "成员")
        .replace("キーホルダー", "钥匙扣")
        .replace("ソウルジェム", "灵魂宝石")
        .replace("使い魔", "使魔")
        .replace("子供", "孩子")
        .replace("子ども", "孩子")
        .replace("友人", "朋友")
        .replace("手帳", "手账")
        .replace("の", "的")
    )
    final_key = speaker_lookup_key(compact)
    return (
        mapping.get(final_key)
        or EXEDRA_ADDITIONAL_SPEAKER_LOOKUP.get(final_key)
        or compact
    )


def translate_speaker(value: str, mapping: dict[str, str]) -> str:
    normalized = normalize_display_punctuation(value)
    if not normalized or normalized in NARRATION_SPEAKERS:
        return "旁白"
    parts = tuple(part for part in MULTI_SPEAKER_RE.split(normalized) if part)
    if len(parts) > 1:
        return "＆".join(translate_speaker(part, mapping) for part in parts)
    return _translate_speaker_component(normalized, mapping)
'''


def patch_dictionary() -> None:
    source = DICTIONARY.read_text(encoding="utf-8")
    marker = "export const NAME_TRANSLATE_MAP"
    start = source.find(marker)
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise RuntimeError("dictionary.ts NAME_TRANSLATE_MAP is missing")
    block = source[start:end]
    additions: list[str] = []
    for key, value in ALIASES.items():
        encoded_key = json.dumps(key, ensure_ascii=False)
        if f"{encoded_key}:" in block:
            continue
        additions.append(
            f"  {encoded_key}: {json.dumps(value, ensure_ascii=False)},"
        )
    if additions:
        insertion = "\n\n  // Exedra authentic TW and retained-human speaker aliases.\n"
        insertion += "\n".join(additions)
        source = source[:end] + insertion + source[end:]
        DICTIONARY.write_text(source, encoding="utf-8", newline="\n")


def patch_module() -> None:
    source = MODULE.read_text(encoding="utf-8")
    count = source.count(OLD_TRANSLATOR)
    if count != 1:
        raise RuntimeError(
            f"tw_authentic_scenario.py translator count={count}; expected 1"
        )
    MODULE.write_text(
        source.replace(OLD_TRANSLATOR, NEW_TRANSLATOR, 1),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    patch_dictionary()
    patch_module()
    print(f"EXEDRA_SPEAKER_ALIAS_EXPANSION_APPLIED aliases={len(ALIASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
