from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import generate_story_index as story_index
from tools import generate_exedra_voice_catalog as voice_catalog


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "artifacts" / "exedra_voice_catalog.json"
EXEDRA_MANIFEST_PATH = (
    ROOT
    / "magiraexedra-source-master"
    / "Scenarios_full"
    / "exedra_manifest.json"
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class VoiceCatalogFixture:
    def __init__(self, root: Path) -> None:
        self.master_root = root / "master"
        self.audio_root = root / "audio"
        self.exedra_root = root / "exedra"
        self.cn_root = root / "cn"
        self.dictionary_path = root / "dictionary.ts"
        for directory in (
            self.master_root,
            self.audio_root,
            self.exedra_root,
            self.cn_root,
        ):
            directory.mkdir(parents=True)

        self.source_names = ["cv_100101_voice_01.json"]
        self._write_master_data()
        self.dictionary_path.write_text(
            "\n".join(
                [
                    "export const NAME_TRANSLATE_MAP = {",
                    '  "鹿目まどか": "鹿目圆",',
                    "};",
                    "",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )
        self.write_sources()
        self.write_manifest()

    def _write_master_data(self) -> None:
        write_json(
            self.master_root / "getCharacterMstList.json",
            {
                "payload": {
                    "mstList": [
                        {
                            "characterMstId": 1001,
                            "name": "鹿目まどか",
                        }
                    ]
                }
            },
        )
        write_json(
            self.master_root / "getStyleFigureMstList.json",
            {
                "payload": {
                    "mstList": [
                        {
                            "styleFigureMstId": 100101,
                            "characterMstId": 1001,
                            "voiceCueSheetName": "cv_100101_{0}",
                        }
                    ]
                }
            },
        )
        write_json(
            self.master_root / "getStyleMstList.json",
            {
                "payload": {
                    "mstList": [
                        {
                            "styleFigureMstId": 100101,
                            "name": "ルクス☆マギカ",
                            "isCollectionDisp": True,
                        }
                    ]
                }
            },
        )

    def write_manifest(self, *, source_paths: list[str] | None = None) -> None:
        source_paths = source_paths or [
            f"6_Reaction/cv_100101/{name}"
            for name in self.source_names
        ]
        write_json(
            self.exedra_root / "exedra_manifest.json",
            {
                "schemaVersion": 1,
                "groups": [
                    {
                        "id": "exedra:6_Reaction:cv_100101",
                        "category": "6_Reaction",
                        "groupKey": "cv_100101",
                        "sourceCount": len(source_paths),
                        "sources": source_paths,
                    }
                ],
            },
        )

    def write_sources(self, *, duplicate_audio: bool = False) -> None:
        for index, source_name in enumerate(self.source_names, start=1):
            sound_name = (
                "cv_100101_voice_01"
                if duplicate_audio
                else Path(source_name).stem
            )
            write_json(
                self.exedra_root
                / "6_Reaction"
                / "cv_100101"
                / source_name,
                {
                    "bookTitle": "鹿目まどか_魔法少女_ボイス_1",
                    "sheetList": [
                        {
                            "headerRow": {
                                "cellList": ["SoundFile", "SoundName"]
                            },
                            "contentRowList": [
                                {
                                    "cellList": [
                                        "cv_100101_outgame",
                                        sound_name,
                                    ]
                                }
                            ],
                        }
                    ],
                },
            )
            audio_path = (
                self.audio_root
                / "cv_100101_outgame"
                / f"{sound_name}.ogg"
            )
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(f"OggS fixture {index}".encode("ascii"))

    def build(self) -> dict[str, object]:
        return voice_catalog.build_catalog(
            master_root=self.master_root,
            audio_root=self.audio_root,
            exedra_root=self.exedra_root,
            cn_root=self.cn_root,
            dictionary_path=self.dictionary_path,
            expected_group_count=1,
        )


class CommittedVoiceCatalogTests(unittest.TestCase):
    def test_catalog_exactly_covers_all_reaction_groups(self) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(
            EXEDRA_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        expected_group_keys = {
            group["groupKey"]
            for group in manifest["groups"]
            if group["category"] == "6_Reaction"
        }
        groups = catalog["groups"]
        actual_group_keys = {group["groupKey"] for group in groups}
        self.assertEqual(len(groups), 86)
        self.assertEqual(actual_group_keys, expected_group_keys)
        self.assertEqual(catalog["summary"]["groups"], 86)

        sources = [
            source
            for group in groups
            for source in group["sources"]
        ]
        audio_keys = [source["audioKey"] for source in sources]
        self.assertEqual(len(sources), 1167)
        self.assertEqual(len(audio_keys), len(set(audio_keys)))
        self.assertEqual(catalog["summary"]["sources"], len(sources))
        self.assertEqual(
            catalog["summary"]["uniqueAudioKeys"],
            len(audio_keys),
        )
        for source in sources:
            self.assertTrue(source["localExists"])
            for field in ("sourceJson", "audioRelativePath"):
                value = source[field]
                self.assertNotIn("\\", value)
                self.assertNotIn(":", value)
                self.assertFalse(value.startswith("/"))
                self.assertNotIn("..", Path(value).parts)
            self.assertTrue(
                source["wikiAudioUrl"].startswith(
                    "https://exedra.wiki/wiki/Special:Redirect/file/"
                )
            )

    def test_story_index_loader_reads_all_titles(self) -> None:
        titles = story_index.load_exedra_voice_titles(CATALOG_PATH)
        self.assertEqual(len(titles), 86)
        self.assertEqual(
            titles["cv_100101"],
            "鹿目圆（鹿目まどか） · 魔法少女",
        )


class VoiceCatalogGenerationTests(unittest.TestCase):
    def test_fixture_generation_is_byte_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = VoiceCatalogFixture(Path(temporary))
            first = voice_catalog.catalog_bytes(fixture.build())
            second = voice_catalog.catalog_bytes(fixture.build())
            self.assertEqual(first, second)

    def test_cn_txt_first_speaker_precedes_dictionary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = VoiceCatalogFixture(Path(temporary))
            cn_path = (
                fixture.cn_root
                / "6_Reaction"
                / "cv_100101"
                / "cv_100101_cn.txt"
            )
            cn_path.parent.mkdir(parents=True, exist_ok=True)
            cn_path.write_text(
                "--- [Section 1] (Source: voice.json) ---\n"
                "圆神：中文台词\n",
                encoding="utf-8",
                newline="\n",
            )
            catalog = fixture.build()
            group = catalog["groups"][0]
            self.assertEqual(group["characterNameCn"], "圆神")
            self.assertEqual(
                group["characterNameCnSource"],
                "cn_txt_speaker",
            )

    def test_cn_txt_is_found_under_arbitrary_nested_language_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = VoiceCatalogFixture(Path(temporary))
            cn_path = (
                fixture.cn_root
                / "任意语言目录"
                / "zh-Hans"
                / "角色语音"
                / "更深一层"
                / "CV－100101 ZH－CN.TXT"
            )
            cn_path.parent.mkdir(parents=True, exist_ok=True)
            cn_path.write_text(
                "--- [Section 1] (Source: voice.json) ---\n"
                "圆神：任意嵌套目录中的中文台词\n",
                encoding="utf-8",
                newline="\n",
            )

            group = fixture.build()["groups"][0]
            self.assertEqual(group["characterNameCn"], "圆神")
            self.assertEqual(
                group["characterNameCnSource"],
                "cn_txt_speaker",
            )

    def test_multiple_cn_txt_candidates_for_one_reaction_group_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = VoiceCatalogFixture(Path(temporary))
            candidates = [
                fixture.cn_root / "简体中文" / "cv_100101_cn.txt",
                fixture.cn_root / "另一语言目录" / "CV-100101-ZH-CN.txt",
            ]
            for index, cn_path in enumerate(candidates, start=1):
                cn_path.parent.mkdir(parents=True, exist_ok=True)
                cn_path.write_text(
                    "--- [Section 1] (Source: voice.json) ---\n"
                    f"圆神：候选 {index}\n",
                    encoding="utf-8",
                    newline="\n",
                )

            with self.assertRaisesRegex(
                voice_catalog.CatalogError,
                r"中文 Reaction TXT 匹配歧义: cv_100101",
            ):
                fixture.build()

    def test_manifest_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = VoiceCatalogFixture(Path(temporary))
            fixture.write_manifest(
                source_paths=[
                    "6_Reaction/cv_100101/../cv_100101_voice_01.json"
                ]
            )
            with self.assertRaisesRegex(
                voice_catalog.CatalogError,
                "安全相对路径",
            ):
                fixture.build()

    def test_duplicate_audio_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = VoiceCatalogFixture(Path(temporary))
            fixture.source_names.append("cv_100101_voice_02.json")
            fixture.write_sources(duplicate_audio=True)
            fixture.write_manifest()
            with self.assertRaisesRegex(
                voice_catalog.CatalogError,
                "复用了同一音频键",
            ):
                fixture.build()


if __name__ == "__main__":
    unittest.main()
