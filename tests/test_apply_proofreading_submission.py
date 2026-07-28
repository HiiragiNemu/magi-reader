from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "apply_proofreading_submission.py"
spec = importlib.util.spec_from_file_location("apply_proofreading_submission", MODULE_PATH)
assert spec and spec.loader
apply = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = apply
spec.loader.exec_module(apply)


def digest_text(value: str) -> str:
    return hashlib.sha256(apply.normalize_text(value).encode("utf-8")).hexdigest()


class ApplyProofreadingSubmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "website/public").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_fixture(self, *, story: dict, source: Path, current: str, submitted: str) -> Path:
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(current, encoding="utf-8")
        source_match = apply.HEADER_RE.search(current.splitlines()[0].strip())
        assert source_match
        json_name = source_match.group(0).split("Source:", 1)[1].split(")", 1)[0].strip()
        current_body = next(
            line for line in current.splitlines()[1:] if line.strip()
        )
        current_text = current_body.split(":", 1)[1].strip()
        if story.get("game") == "exedra":
            category, group = story["source_identity"].split(":")[1:]
            document = {
                "sheetList": [
                    {
                        "headerRow": {
                            "cellList": ["ActionType", "Name", "Comment"]
                        },
                        "contentRowList": [
                            {
                                "rowNumber": 2,
                                "cellList": ["Talk", "角色", current_text],
                            }
                        ],
                    }
                ]
            }
            source.with_name(json_name).write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )
            jp_folder = (
                self.root
                / "magiraexedra-source-master/Scenarios_full"
                / category
                / group
            )
            jp_folder.mkdir(parents=True, exist_ok=True)
            (jp_folder / json_name).write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )
            (jp_folder / f"{group}_jp.txt").write_text(
                f"--- [Section 1] (Source: {json_name}) ---\n角色：日文\n",
                encoding="utf-8",
            )
            manifest = {
                "schemaVersion": 1,
                "groups": [
                    {
                        "id": f"exedra:{category}:{group}",
                        "category": category,
                        "groupKey": group,
                        "outputDir": f"{category}/{group}",
                        "textFile": f"{category}/{group}/{group}_jp.txt",
                        "sources": [f"{category}/{group}/{json_name}"],
                    }
                ],
            }
            manifest_path = (
                self.root
                / "magiraexedra-source-master/Scenarios_full/exedra_manifest.json"
            )
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            source.with_name(json_name).write_text(
                json.dumps(
                    {
                        "story": {
                            "group_1": [
                                {
                                    "nameLeft": "角色",
                                    "textLeft": current_text,
                                }
                            ]
                        },
                        "version": 3,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        story_index = self.root / "website/public/story_index.json"
        raw_index = (json.dumps([story], ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        story_index.write_bytes(raw_index)
        record = {
            "id": "ps_test_1234567890",
            "story_id": story["id"],
            "nickname": "校对者",
            "note": "修正措辞",
            "content": submitted,
            "content_sha256": digest_text(submitted),
            "base_sha256": digest_text(current),
            "base_content_sha256": digest_text("---[Section 1] (Source: 123-1.json) ---\n角色: 原文"),
            "catalog_sha256": hashlib.sha256(raw_index).hexdigest(),
            "source_path_cn": story["path_cn"],
            "source_path_jp": story["path_jp"],
            "source_identity": story["source_identity"],
            "target_branch": "EXEDRA-TEST",
        }
        submission = self.root / "submission.json"
        submission.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return submission

    def test_applies_magireco_txt(self) -> None:
        current = "---[Section 1] (Source: 123-1.json) ---\n角色: 原文\n"
        submitted = "---[Section 1] (Source: 123-1.json) ---\n角色: 修正文"
        story = {
            "id": "123",
            "game": "magireco",
            "source_identity": "event_story/123 - 测试/123_1",
            "path_cn": "/data/event_story/123 - 测试/123_1_cn.txt",
            "path_jp": "/data/event_story/123 - 测试/123_1_jp.txt",
        }
        source = self.root / "magireco-translate-data-master/Scenarios_full/event_story/123 - 测试/123_1.txt"
        submission = self.write_fixture(story=story, source=source, current=current, submitted=submitted)
        result = apply.apply_submission(
            repo_root=self.root,
            submission_path=submission,
            story_index_path=self.root / "website/public/story_index.json",
            write=True,
        )
        self.assertEqual(result.source_relative, source.relative_to(self.root).as_posix())
        self.assertEqual(
            source.read_text(encoding="utf-8"),
            "--- [Section 1] (Source: 123-1.json) ---\n角色：修正文\n",
        )
        generated = json.loads(source.with_name("123-1.json").read_text(encoding="utf-8"))
        self.assertEqual(generated["story"]["group_1"][0]["textLeft"], "修正文")
        self.assertIn(
            source.with_suffix(".proofreading-report.json").relative_to(self.root).as_posix(),
            result.materialized_paths,
        )

    def test_applies_exedra_txt(self) -> None:
        current = "---[Section 1] (Source: group_1.json) ---\n角色: 原文\n"
        submitted = "---[Section 1] (Source: group_1.json) ---\n角色: 修正文"
        story = {
            "id": "exedra_main_group_0123456789",
            "game": "exedra",
            "source_identity": "exedra:1_Main:group",
            "filename_cn": "group_cn.txt",
            "path_cn": "/data/exedra_main/group/group_cn.txt",
            "path_jp": "/data/exedra_main/group/group_jp.txt",
        }
        source = self.root / "magiraexedra-translate-data-master/Scenarios_full/1_Main/group/group_cn.txt"
        submission = self.write_fixture(story=story, source=source, current=current, submitted=submitted)
        result = apply.apply_submission(
            repo_root=self.root,
            submission_path=submission,
            story_index_path=self.root / "website/public/story_index.json",
            write=True,
        )
        self.assertEqual(result.story_id, story["id"])
        self.assertEqual(
            source.read_text(encoding="utf-8"),
            "--- [Section 1] (Source: group_1.json) ---\n角色：修正文\n",
        )
        generated = json.loads(source.with_name("group_1.json").read_text(encoding="utf-8"))
        self.assertEqual(
            generated["sheetList"][0]["contentRowList"][0]["cellList"][2],
            "修正文",
        )

    def test_rejects_stale_source(self) -> None:
        current = "---[Section 1] (Source: 123-1.json) ---\n角色: 新文本\n"
        submitted = "---[Section 1] (Source: 123-1.json) ---\n角色: 修正文"
        story = {
            "id": "123",
            "game": "magireco",
            "source_identity": "event_story/123 - 测试/123_1",
            "path_cn": "/data/event_story/123 - 测试/123_1_cn.txt",
            "path_jp": "/data/event_story/123 - 测试/123_1_jp.txt",
        }
        source = self.root / "magireco-translate-data-master/Scenarios_full/event_story/123 - 测试/123_1.txt"
        submission = self.write_fixture(story=story, source=source, current=current, submitted=submitted)
        record = json.loads(submission.read_text(encoding="utf-8"))
        record["base_sha256"] = "0" * 64
        submission.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(apply.ApplyError) as caught:
            apply.apply_submission(
                repo_root=self.root,
                submission_path=submission,
                story_index_path=self.root / "website/public/story_index.json",
                write=True,
            )
        self.assertEqual(caught.exception.code, "stale_source")

    def test_rejects_changed_section_structure(self) -> None:
        current = "---[Section 1] (Source: 123-1.json) ---\n角色: 原文\n"
        submitted = "---[Section 2] (Source: 123-2.json) ---\n角色: 修正文"
        story = {
            "id": "123",
            "game": "magireco",
            "source_identity": "event_story/123 - 测试/123_1",
            "path_cn": "/data/event_story/123 - 测试/123_1_cn.txt",
            "path_jp": "/data/event_story/123 - 测试/123_1_jp.txt",
        }
        source = self.root / "magireco-translate-data-master/Scenarios_full/event_story/123 - 测试/123_1.txt"
        submission = self.write_fixture(story=story, source=source, current=current, submitted=submitted)
        with self.assertRaises(apply.ApplyError) as caught:
            apply.apply_submission(
                repo_root=self.root,
                submission_path=submission,
                story_index_path=self.root / "website/public/story_index.json",
                write=False,
            )
        self.assertEqual(caught.exception.code, "structure_changed")


if __name__ == "__main__":
    unittest.main()
