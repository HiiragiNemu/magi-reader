#!/usr/bin/env python3
"""Update the 618401 pipeline test from partial to complete CN pairing.

The replacement preserves the original test's important guarantees: the legacy
route remains attached to the canonical story and a distinct translation variant
remains a separate CN-only catalogue entry.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_TARGET = ROOT / "tests" / "test_data_pipeline.py"

OLD_TEST = '''    def test_audited_partial_pair_keeps_distinct_translation_variant(
        self,
    ) -> None:
        cn_identity, jp_identity = generate.MAGIRECO_AUDITED_PARTIAL_PAIR
        cn_parent = cn_identity.rsplit("/", 1)[0]
        write_text(
            self.cn / f"{cn_identity}.txt",
            "---[Section 1] (Source: 618401-1-cn.json) ---\\n"
            "彩羽: 中文第一节\\n"
            "八千代: 中文回应\\n",
        )
        write_text(
            self.jp / f"{jp_identity}.txt",
            "---[Section 1] (Source: 618401-1-jp.json) ---\\n"
            "いろは: 日文第一节\\n"
            "やちよ: 日文回应\\n"
            "---[Section 2] (Source: 618401-2-jp.json) ---\\n"
            "旁白: 日文第二节\\n"
            "---[Section 3] (Source: 618401-3-jp.json) ---\\n"
            "旁白: 日文第三节\\n"
            "---[Section 4] (Source: 618401-4-jp.json) ---\\n"
            "旁白: 日文第四节\\n"
            "---[Section 5] (Source: 618401-5-jp.json) ---\\n"
            "旁白: 日文第五节\\n"
            "---[Section 6] (Source: 618401-6-jp.json) ---\\n"
            "旁白: 日文第六节\\n"
            "---[Section 7] (Source: 618401-7-jp.json) ---\\n"
            "旁白: 日文第七节\\n",
        )
        write_text(
            self.cn / cn_parent / "618401_1-1.txt",
            "---[Section 1] (Source: alternate.json) ---\\n"
            "彩羽: 不同译本\\n",
        )

        stories, stats = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=None,
            exedra_cn_dir=None,
            titles_path=self.titles,
        )

        self.assertEqual(len(stories), 2)
        paired = next(
            story for story in stories if story.get("legacy_ids") == ["618401"]
        )
        alternate = next(story for story in stories if story is not paired)
        self.assertTrue(paired["has_cn"] and paired["has_jp"])
        self.assertEqual(paired["source_identity"], cn_identity)
        self.assertTrue(alternate["has_cn"])
        self.assertFalse(alternate["has_jp"])
        self.assertEqual(stats["magireco_audited_partial_pairs"], 1)
        self.assertEqual(stats["magireco_legacy_route_aliases"], 1)

'''

NEW_TEST = '''    def test_completed_full_pair_keeps_distinct_translation_variant(
        self,
    ) -> None:
        full_identity = (
            "login_story/6184 - 2021新年 各自的福袋梦/618401_1-7"
        )
        parent = full_identity.rsplit("/", 1)[0]
        write_text(
            self.cn / f"{full_identity}.txt",
            "---[Section 1] (Source: 618401-1-cn.json) ---\\n"
            "彩羽: 中文第一节\\n"
            "八千代: 中文回应\\n"
            "---[Section 2] (Source: 618401-2-cn.json) ---\\n"
            "旁白: 中文第二节\\n"
            "---[Section 3] (Source: 618401-3-cn.json) ---\\n"
            "旁白: 中文第三节\\n"
            "---[Section 4] (Source: 618401-4-cn.json) ---\\n"
            "旁白: 中文第四节\\n"
            "---[Section 5] (Source: 618401-5-cn.json) ---\\n"
            "旁白: 中文第五节\\n"
            "---[Section 6] (Source: 618401-6-cn.json) ---\\n"
            "旁白: 中文第六节\\n"
            "---[Section 7] (Source: 618401-7-cn.json) ---\\n"
            "旁白: 中文第七节\\n",
        )
        write_text(
            self.jp / f"{full_identity}.txt",
            "---[Section 1] (Source: 618401-1-jp.json) ---\\n"
            "いろは: 日文第一节\\n"
            "やちよ: 日文回应\\n"
            "---[Section 2] (Source: 618401-2-jp.json) ---\\n"
            "旁白: 日文第二节\\n"
            "---[Section 3] (Source: 618401-3-jp.json) ---\\n"
            "旁白: 日文第三节\\n"
            "---[Section 4] (Source: 618401-4-jp.json) ---\\n"
            "旁白: 日文第四节\\n"
            "---[Section 5] (Source: 618401-5-jp.json) ---\\n"
            "旁白: 日文第五节\\n"
            "---[Section 6] (Source: 618401-6-jp.json) ---\\n"
            "旁白: 日文第六节\\n"
            "---[Section 7] (Source: 618401-7-jp.json) ---\\n"
            "旁白: 日文第七节\\n",
        )
        write_text(
            self.cn / parent / "618401_1-1.txt",
            "---[Section 1] (Source: alternate.json) ---\\n"
            "彩羽: 不同译本\\n",
        )

        stories, stats = generate.build_story_catalog(
            staging_public_dir=self.stage,
            jp_dir=self.jp,
            cn_dir=self.cn,
            exedra_jp_dir=None,
            exedra_cn_dir=None,
            titles_path=self.titles,
        )

        self.assertEqual(len(stories), 2)
        paired = next(
            story for story in stories if story.get("legacy_ids") == ["618401"]
        )
        alternate = next(story for story in stories if story is not paired)
        self.assertTrue(paired["has_cn"] and paired["has_jp"])
        self.assertEqual(paired["source_identity"], full_identity)
        self.assertTrue(alternate["has_cn"])
        self.assertFalse(alternate["has_jp"])
        self.assertEqual(stats["magireco_audited_partial_pairs"], 0)
        self.assertEqual(stats["magireco_legacy_route_aliases"], 1)

'''


class MigrationError(RuntimeError):
    pass


def migrate(source: str) -> str:
    count = source.count(OLD_TEST)
    if count != 1:
        raise MigrationError(
            f"旧 618401 测试应恰好出现 1 次，实际为 {count} 次；拒绝修改"
        )
    migrated = source.replace(OLD_TEST, NEW_TEST)
    if "test_audited_partial_pair_keeps_distinct_translation_variant" in migrated:
        raise MigrationError("旧 partial 测试仍有残留；拒绝写入")
    if "test_completed_full_pair_keeps_distinct_translation_variant" not in migrated:
        raise MigrationError("完整配对测试未写入；拒绝写入")
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
        print(f"已更新 618401 完整配对测试: {target}")
    else:
        print("测试迁移预检通过；未修改文件。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"错误: {exc}")
        raise SystemExit(2) from exc
