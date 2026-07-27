#!/usr/bin/env python3
"""Retire the obsolete 618401 partial-translation pairing rule safely.

The original catalogue paired a one-section CN TXT (618401_1) with a seven-section
JP TXT (618401_1-7). The complete translation corpus now provides the full CN
618401_1-7 TXT, so normal exact pairing must take over. This migration uses exact
source assertions and refuses to modify an unexpected generator revision.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_TARGET = ROOT / "generate_story_index.py"

PARTIAL_CONSTANT = '''MAGIRECO_AUDITED_PARTIAL_PAIR = (
    "login_story/6184 - 2021新年 各自的福袋梦/618401_1",
    "login_story/6184 - 2021新年 各自的福袋梦/618401_1-7",
)
'''

PARTIAL_MERGE_BLOCK = '''    partial_id = "618401"
    if _merge_audited_magireco_pair(
        logical_sources,
        cn_identity=MAGIRECO_AUDITED_PARTIAL_PAIR[0],
        jp_identity=MAGIRECO_AUDITED_PARTIAL_PAIR[1],
        stats=stats,
        partial_cn_prefix=True,
    ):
        satisfied.add(partial_id)

'''

OLD_DOCSTRING = '    """Apply only the reviewed cross-folder and partial-story pairings."""'
NEW_DOCSTRING = '    """Apply only the reviewed cross-folder pairings."""'
OLD_EXPECTED = '        expected = set(MAGIRECO_AUDITED_CROSS_FOLDER_PAIRS) | {partial_id}'
NEW_EXPECTED = '        expected = set(MAGIRECO_AUDITED_CROSS_FOLDER_PAIRS)'


class MigrationError(RuntimeError):
    pass


def require_once(source: str, needle: str, label: str) -> None:
    count = source.count(needle)
    if count != 1:
        raise MigrationError(
            f"{label} 应恰好出现 1 次，实际为 {count} 次；拒绝修改"
        )


def migrate(source: str) -> str:
    require_once(source, PARTIAL_CONSTANT, "旧 partial 常量")
    require_once(source, PARTIAL_MERGE_BLOCK, "旧 partial 合并块")
    require_once(source, OLD_DOCSTRING, "旧配对函数说明")
    require_once(source, OLD_EXPECTED, "旧完整语料预期集合")

    migrated = source.replace(
        PARTIAL_CONSTANT,
        "# 618401 曾使用 CN 第 1 节对 JP 第 1–7 节的临时配对。\n"
        "# 完整中文语料现已提供 618401_1-7，交由正常精确配对处理。\n",
    )
    migrated = migrated.replace(PARTIAL_MERGE_BLOCK, "")
    migrated = migrated.replace(OLD_DOCSTRING, NEW_DOCSTRING)
    migrated = migrated.replace(OLD_EXPECTED, NEW_EXPECTED)

    if "MAGIRECO_AUDITED_PARTIAL_PAIR" in migrated or "partial_id = \"618401\"" in migrated:
        raise MigrationError("旧 partial 配对引用仍有残留；拒绝写入")
    return migrated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    target = args.target.resolve()
    source = target.read_text(encoding="utf-8")
    migrated = migrate(source)

    if args.write:
        target.write_text(migrated, encoding="utf-8")
        print(f"已移除过时的 618401 partial 配对规则: {target}")
    else:
        print("迁移预检通过；未修改文件。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"错误: {exc}")
        raise SystemExit(2) from exc
