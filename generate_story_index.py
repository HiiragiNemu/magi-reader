#!/usr/bin/env python3
"""Build MagiReader's public story catalogue safely.

The module is intentionally import-safe: importing it never deletes or writes
website data.  Generation happens only through ``main``/``run_generation``.

Supported source families:

* Magia Record consolidated TXT trees with exact logical JP/CN pairing.
* Magia Exedra organized chapter/character groups with exact JP/CN pairing.
* Exedra JSON provenance validation through ``exedra_manifest.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

try:
    import natsort
except ImportError:  # pragma: no cover - the repository already uses natsort
    natsort = None


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DIR_JP = SCRIPT_DIR / "magireco-source-master" / "Scenarios_full"
DEFAULT_DIR_CN = SCRIPT_DIR / "magireco-translate-data-master" / "Scenarios_full"
DEFAULT_EXEDRA_JP_DIR = (
    SCRIPT_DIR / "magiraexedra-source-master" / "Scenarios_full"
)
DEFAULT_EXEDRA_CN_DIR = (
    SCRIPT_DIR / "magiraexedra-translate-data-master" / "Scenarios_full"
)
DEFAULT_PUBLIC_DIR = SCRIPT_DIR / "website" / "public"
DEFAULT_TITLES_PATH = SCRIPT_DIR / "titles.json"
EXEDRA_MANIFEST_NAME = "exedra_manifest.json"

# Kept for callers that used the old module-level name.  It is deliberately
# empty until main() loads titles, so import remains read-only.
TITLES: dict[str, str] = {}

EXEDRA_CATEGORY_MAP = {
    "1_Main": "exedra_main",
    "2_Sub": "exedra_sub",
    "3_Character": "exedra_character",
    "4_Portrait": "exedra_portrait",
    "6_Reaction": "exedra_reaction",
    "7_Namae": "exedra_namae",
    "8_Dungeon": "exedra_dungeon",
    "10_Battle": "exedra_battle",
}
EXEDRA_CATEGORY_MAP_REVERSE = {
    category: raw_category
    for raw_category, category in EXEDRA_CATEGORY_MAP.items()
}
STORY_IDS_FILENAME = "story_ids.generated.json"
EXEDRA_ROUTE_GROUP_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
STORY_ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
MAX_LEGACY_IDS_PER_STORY = 16
MAX_LEGACY_ROUTE_ALIASES = 10_000
EXEDRA_CHARACTER_DISPLAY_NAMES = {
    "character_arina": "阿莉娜·格雷（アリナ・グレイ）",
    "character_ashley": "阿什莉·泰勒（アシュリー・テイラー）",
    "character_asuka": "龙城明日香（竜城 明日香）",
    "character_ayame": "三栗菖蒲（三栗 あやめ）",
    "character_corbeau": "可鲁波（コルボー）",
    "character_darc": "塔鲁特（タルト）",
    "character_felicia": "深月菲莉希亚（深月 フェリシア）",
    "character_fuka": "日暮风花（日暮 ふうか）",
    "character_hanna": "更纱帆奈（更紗 帆奈）",
    "character_hazuki": "游佐叶月（遊佐 葉月）",
    "character_himika": "真尾日美香（眞尾 ひみか）",
    "character_homura": "晓美焰（暁美 ほむら）",
    "character_iroha": "环彩羽（環 いろは）",
    "character_kaede": "秋野枫（秋野 かえで）",
    "character_kako": "夏目佳子（夏目 かこ）",
    "character_kanae": "雪野加奈惠（雪野 かなえ）",
    "character_karin": "御园花凛（御園 かりん）",
    "character_kirika": "吴纪里香（呉 キリカ）",
    "character_koito": "浅古小糸（浅古 小糸）",
    "character_kokoro": "粟根心（粟根 こころ）",
    "character_konoha": "静海木叶（静海 このは）",
    "character_kush": "入名库什（入名 クシュ）",
    "character_kyoko": "佐仓杏子（佐倉 杏子）",
    "character_liz": "莉兹（リズ）",
    "character_mabayu": "爱生眩（愛生 まばゆ）",
    "character_madoka": "鹿目圆（鹿目 まどか）",
    "character_mami": "巴麻美（巴 マミ）",
    "character_mannenzakura": "万年樱之谣（万年桜のウワサ）",
    "character_masara": "加贺见真良（加賀見 まさら）",
    "character_mayoi": "八九寺真宵（八九寺 真宵）",
    "character_meiyui": "纯美雨（純 美雨）",
    "character_melissa": "梅丽莎（メリッサ）",
    "character_meru": "安名梅露（安名 メル）",
    "character_mifuyu": "梓美冬（梓 みふゆ）",
    "character_mitama": "八云御魂（八雲 みたま）",
    "character_mito": "相野未都（相野 みと）",
    "character_momoko": "十咎桃子（十咎 ももこ）",
    "character_nagisa": "百江渚（百江 なぎさ）",
    "character_nanaka": "常盘七香（常盤 ななか）",
    "character_natsuki": "空穗夏希（空穂 夏希）",
    "character_nemu": "柊音梦（柊 ねむ）",
    "character_oriko": "美国织莉子（美国 織莉子）",
    "character_reira": "伊吹丽良（伊吹 れいら）",
    "character_ren": "五十铃怜（五十鈴 れん）",
    "character_rena": "水波玲奈（水波 レナ）",
    "character_rika": "绫野梨花（綾野 梨花）",
    "character_riko": "千秋理子（千秋 理子）",
    "character_sana": "二叶莎奈（二葉 さな）",
    "character_sayaka": "美树沙耶香（美樹 さやか）",
    "character_seika": "桑水清佳（桑水 せいか）",
    "character_senpai": "小圆前辈（まどか先輩）",
    "character_shinobu": "忍野忍（忍野 忍）",
    "character_sumire": "夜明堇（夜明 すみれ）",
    "character_touka": "里见灯花（里見 灯花）",
    "character_tsukasa": "天音月咲（天音 月咲）",
    "character_tsukuyo": "天音月夜（天音 月夜）",
    "character_tsuruno": "由比鹤乃（由比 鶴乃）",
    "character_ui": "环忧（環 うい）",
    "character_yachiyo": "七海八千代（七海 やちよ）",
    "character_yotsugi": "斧乃木余接（斧乃木 余接）",
    "character_yuma": "千岁由麻（千歳 ゆま）",
}

# These are the only known Magia Record stories whose CN and JP parent folders
# use different display translations while the reader-visible story structure
# is identical.  Pairing remains an explicit allowlist: an unlisted
# cross-folder match is never guessed from a short numeric ID.
MAGIRECO_AUDITED_CROSS_FOLDER_GROUPS = (
    (
        (
            "event_story",
            "5101 - 常夜之国的叛乱者～魔法少女贞德～",
        ),
        (
            "event_story",
            "5101 - 常夜之国的叛乱者 ~魔法少女贞德~",
        ),
        (
            "510101-09_0-6",
            "510101_0-8",
            "510102_1-9",
            "510103_1-9",
            "510104_1-4",
            "510105_1-7",
            "510106_1-4",
            "510107_1-2",
            "510108_1-5",
            "510109_1-6",
            "510110-12_1-10",
            "510110_1-3",
            "510111_1-2",
            "510112_1-10",
        ),
    ),
    (
        (
            "event_story",
            "5175 - Dream Halloween Festa～阿莉娜前辈！做个好孩子！～",
        ),
        (
            "event_story",
            "5175 - Dream Halloween Festa～阿莉娜前辈！做要好孩子的说！～",
        ),
        (
            "517501-09_0-33",
            "517501_0-4",
            "517502_5-7",
            "517503_8-12",
            "517504_13-16",
            "517505_17-20",
            "517506_21-22",
            "517507_23-26",
            "517508_27-28",
            "517509_29-33",
            "517510-15_34-50",
            "517510_34-35",
            "517511_36-38",
            "517512_39-44",
            "517513_45-46",
            "517514_47-47",
            "517515_48-50",
        ),
    ),
    (
        (
            "event_story",
            "5216 - 海岸边的缎带",
        ),
        (
            "event_story",
            "5216 - 海边的缎带",
        ),
        (
            "521610_0-20",
            "521620_1-23",
        ),
    ),
)
MAGIRECO_AUDITED_CROSS_FOLDER_PAIRS = {
    stem.split("_", 1)[0]: (
        "/".join((*cn_parent, stem)),
        "/".join((*jp_parent, stem)),
    )
    for cn_parent, jp_parent, stems in MAGIRECO_AUDITED_CROSS_FOLDER_GROUPS
    for stem in stems
}
if (
    sum(
        len(stems)
        for _, _, stems in MAGIRECO_AUDITED_CROSS_FOLDER_GROUPS
    )
    != 33
    or len(MAGIRECO_AUDITED_CROSS_FOLDER_PAIRS) != 33
):
    raise RuntimeError("Magia Record 审计配对白名单必须恰好包含 33 个唯一 ID")
# 618401 曾使用 CN 第 1 节对 JP 第 1–7 节的临时配对。
# 完整中文语料现已提供 618401_1-7，交由正常精确配对处理。

MAGIRECO_LEGACY_ROUTE_IDENTITIES = {
    "310031": (
        "character_story/1003 - 由比鹤乃（由比 鶴乃）/310031_1-4"
    ),
    "310061": "character_story/1006 - 梓美冬（梓 みふゆ）/310061_1-4",
    "310112": "character_story/1011 - 秋野枫（秋野 かえで）/310112_1-4",
    "310301": (
        "character_story/1030 - 安积育梦（安積 はぐむ）/310301_1-4"
    ),
    "330023": (
        "character_story/3002 - 空穗夏希（空穂 夏希）/330023_1-5"
    ),
    "330191": (
        "character_story/3019 - 毬子亚弥华（毬子 あやか）/330191_1-4"
    ),
    "330311": (
        "character_story/3031 - 绫野梨花（綾野 梨花）/330311_1-4"
    ),
    "330431": (
        "character_story/3043 - 万年樱之谣（万年桜のウワサ）/"
        "330431_1-4"
    ),
    "504203": (
        "event_story/5042 - Whereabouts of the feather ～羽翼的去向～/"
        "504203_1-4"
    ),
    "504502": (
        "event_story/5045 - 阿莉娜进城来 ～白色圣诞狂想曲～/"
        "504502_9-17"
    ),
    "510041": (
        "event_story/51004 - 御魂的特训 杏子、菲莉希亚篇/510041_1-4"
    ),
    "511970": (
        "event_story/5119 - Angels on the Road～驯鹿圣诞老人兴隆记～/"
        "511970_20"
    ),
    "515170": (
        "event_story/5151 - Angels on the Road～驯鹿圣诞老人兴隆记～/"
        "515170_20"
    ),
    "102901": (
        "main_story/1029-19 - 第II部 第8章 - 集結の百禍編/102901_1"
    ),
    "420131": (
        "mirror_story/420131-1~4记忆博物馆-篠目夜鹤/420131_1-4"
    ),
    # These 33 routes become canonical again after the explicitly audited
    # cross-folder CN/JP records are paired.
    **{
        raw_id: identities[0]
        for raw_id, identities in MAGIRECO_AUDITED_CROSS_FOLDER_PAIRS.items()
    },
    # These four raw IDs remain ambiguous, so the old route is attached only
    # to the audited complete/bilingual record.
    "5170100-09": (
        "event_story/5170 - 七彩夏日绘～笔记中记录的日常～/"
        "5170100-09_30-39"
    ),
    "5170110-17": (
        "event_story/5170 - 七彩夏日绘～笔记中记录的日常～/"
        "5170110-17_40-47"
    ),
    "618401": "login_story/6184 - 2021新年 各自的福袋梦/618401_1-7",
    "103001": (
        "main_story/1030-20 - 第II部 第9章 - 集結の百禍編/"
        "103001_1-10"
    ),
}
EXEDRA_TEXT_ACTIONS = {"talk", "narration", "charactertalk", "onlytext"}
EXEDRA_SECTION_RE = re.compile(
    r"^---\s*\[Section\s+(\d+)\]\s*"
    r"\(Source:\s*(.+?\.json)\s*\)\s*---$",
    flags=re.I,
)
EXEDRA_IMPORT_REPORT_SCHEMA_VERSION = 1
EXEDRA_IMPORT_REPORT_SUFFIX = "_cn.import-report.json"
EXEDRA_NARRATION_SPEAKERS = frozenset(
    {"Narration", "ナレーション", "旁白", "旁白（无角色）"}
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PipelineError(RuntimeError):
    """A validation or safe-generation failure."""


def _is_link_like(path: Path) -> bool:
    """Return True for symbolic links and Windows directory junctions."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError as exc:
        raise PipelineError(f"无法检查路径重解析状态: {path}: {exc}") from exc


def _absolute_lexical(path: Path) -> Path:
    """Make a path absolute without resolving a final link or junction."""

    return Path(os.path.abspath(os.fspath(path)))


def _assert_no_link_ancestors(path: Path, *, label: str) -> None:
    current = _absolute_lexical(path)
    while True:
        if _is_link_like(current):
            raise PipelineError(
                f"{label} 的祖先路径包含符号链接或 Windows 联接点: {current}"
            )
        if current.parent == current:
            break
        current = current.parent


def _plain_tree_entries(
    root: Path,
) -> list[tuple[Path, Path, bool]]:
    """Enumerate a tree without following any link-like directory."""

    root = _absolute_lexical(root)
    _assert_no_link_ancestors(root, label="文件树根目录")
    if not root.is_dir():
        raise PipelineError(f"文件树不存在: {root}")
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"无法解析文件树根目录: {root}: {exc}") from exc

    result: list[tuple[Path, Path, bool]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                entries = sorted(scan, key=lambda item: item.name.casefold())
        except OSError as exc:
            raise PipelineError(f"无法枚举文件树: {current}: {exc}") from exc

        child_directories: list[Path] = []
        for entry in entries:
            path = Path(entry.path)
            if _is_link_like(path):
                raise PipelineError(
                    f"文件树包含符号链接或 Windows 联接点，拒绝处理: {path}"
                )
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except ValueError as exc:
                raise PipelineError(f"文件树路径越界: {path}") from exc
            except OSError as exc:
                raise PipelineError(f"无法检查文件树条目: {path}: {exc}") from exc
            if not is_directory and not is_file:
                raise PipelineError(f"文件树包含非普通条目，拒绝处理: {path}")
            relative = path.relative_to(root)
            result.append((path, relative, is_directory))
            if is_directory:
                child_directories.append(path)
        stack.extend(reversed(child_directories))
    return result


def _source_key(path: Path) -> str:
    """Return a stable, case-insensitive key for a physical input source."""

    return os.path.normcase(os.fspath(path.resolve())).casefold()


@dataclass
class SourceAudit:
    """Track canonical input files and their one-to-one manifest ownership."""

    expected: dict[str, str] = field(default_factory=dict)
    owners: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    ownership_collisions: int = 0

    def expect(self, source_path: Path) -> None:
        key = _source_key(source_path)
        self.expected.setdefault(key, os.fspath(source_path.resolve()))

    def claim(
        self,
        source_path: Path,
        *,
        story_id: str,
        lang_key: str,
        web_path: str,
    ) -> None:
        key = _source_key(source_path)
        if key not in self.expected:
            raise PipelineError(f"来源未登记为可读输入: {source_path}")
        previous = self.owners.get(key)
        if previous is not None:
            self.ownership_collisions += 1
            raise PipelineError(
                "同一输入来源被重复分配: "
                f"{source_path}: {previous[0]}/{previous[1]}, "
                f"{story_id}/{lang_key}"
            )
        self.owners[key] = (story_id, lang_key, web_path)

    def validate_manifest(
        self,
        stories: Sequence[Mapping[str, Any]],
    ) -> dict[str, int]:
        orphan_keys = set(self.expected) - set(self.owners)
        unexpected_keys = set(self.owners) - set(self.expected)
        if orphan_keys:
            examples = ", ".join(self.expected[key] for key in sorted(orphan_keys)[:3])
            raise PipelineError(
                f"有 {len(orphan_keys)} 个可读输入未被 story_index 覆盖: {examples}"
            )
        if unexpected_keys:
            raise PipelineError(
                f"有 {len(unexpected_keys)} 个未登记输入被发布"
            )

        manifest_slots: set[tuple[str, str, str]] = set()
        for story in stories:
            story_id = str(story.get("id") or "")
            for lang_key in ("cn", "jp"):
                web_path = str(story.get(f"path_{lang_key}") or "")
                if web_path:
                    manifest_slots.add(
                        (story_id, lang_key, web_path.casefold())
                    )
        ownership_slots = {
            (story_id, lang_key, web_path.casefold())
            for story_id, lang_key, web_path in self.owners.values()
        }
        missing_slots = ownership_slots - manifest_slots
        unowned_slots = manifest_slots - ownership_slots
        if missing_slots or unowned_slots:
            raise PipelineError(
                "输入所有权与 story_index 不一致: "
                f"缺失 {len(missing_slots)}, 无所有者 {len(unowned_slots)}"
            )

        return {
            "input_source_files": len(self.expected),
            "manifest_source_files": len(self.owners),
            "orphan_sources": 0,
            "ownership_collisions": self.ownership_collisions,
        }


def sanitize_path(path: str | os.PathLike[str]) -> str:
    return os.fspath(path).replace("\\", "/")


def decode_hash_u(value: str) -> str:
    """Decode ZIP paths such as ``#U4e3b#U7ebf`` to Unicode."""

    def repl(match: re.Match[str]) -> str:
        try:
            return chr(int(match.group(1), 16))
        except ValueError:
            return match.group(0)

    return re.sub(r"#U([0-9a-fA-F]{4,6})", repl, value)


def get_category(path: str | os.PathLike[str]) -> str:
    """Return the legacy Magia Record category without changing old IDs."""

    decoded_path = decode_hash_u(os.fspath(path)).replace("\\", "/")
    lower = decoded_path.lower()
    if "main_story" in lower:
        return "main_story"
    if "event_story" in lower:
        return "event_story"
    if "character_story" in lower:
        return "character_story"
    if "costume_story" in lower:
        return "costume_story"
    if "login_story" in lower:
        return "login_story"
    if "mirror_story" in lower:
        return "mirror_story"
    if "scene0" in lower or "s0" in lower:
        if "支线" in decoded_path or "sub" in lower:
            return "scene0_sub"
        return "scene0_main"
    return "Unclassified"


def strip_lang_suffix_filename(file_name: str) -> str:
    stem = Path(file_name).stem
    return re.sub(r"_(cn|jp)$", "", stem, flags=re.I)


def _normalize_identity_text(value: str) -> str:
    return unicodedata.normalize("NFC", decode_hash_u(value)).strip()


def magireco_source_identity(
    base_dir: Path,
    source_path: Path,
) -> tuple[str, tuple[str, ...], str]:
    """Return exact logical identity, display parent parts, and clean stem.

    JP and CN are paired only when the complete normalized relative parent and
    filename stem match.  A short numeric prefix is never sufficient identity.
    """

    relative = source_path.relative_to(base_dir)
    parent_parts = tuple(
        _normalize_identity_text(part) for part in relative.parent.parts
    )
    file_stem = _normalize_identity_text(
        strip_lang_suffix_filename(relative.name)
    )
    identity = "/".join((*parent_parts, file_stem))
    return identity.casefold(), parent_parts, file_stem


def safe_scene0_story_id(category: str, folder_name: str, file_stem: str) -> str:
    """Preserve the Scene0 collision fix used by the existing site."""

    basis = f"{category}/{folder_name}/{file_stem}"
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8]
    clean_stem = re.sub(r"[^0-9A-Za-z_.-]+", "-", file_stem).strip("-") or "scene0"
    return f"{category}_{clean_stem}_{digest}"


def safe_magireco_collision_id(
    category: str,
    source_identity: str,
    file_stem: str,
) -> str:
    """Create a readable stable ID when a legacy short ID is ambiguous."""

    digest = hashlib.sha1(source_identity.encode("utf-8")).hexdigest()[:10]
    clean_stem = re.sub(r"[^0-9A-Za-z_.-]+", "-", file_stem).strip("-")
    clean_stem = (clean_stem or "story")[:96]
    return f"{category}_{clean_stem}_{digest}"


def make_story_key(
    category: str,
    folder_name: str,
    file_stem: str,
    raw_id: str,
) -> str:
    if category.startswith("scene0_"):
        return safe_scene0_story_id(category, folder_name, file_stem)
    return raw_id


def safe_exedra_story_id(category: str, relative_source: str, file_stem: str) -> str:
    """Create a stable URL-safe ID from the complete Exedra source identity."""

    normalized_source = sanitize_path(relative_source).strip("/")
    digest = hashlib.sha1(
        f"exedra/{category}/{normalized_source}".encode("utf-8")
    ).hexdigest()[:10]
    clean_stem = re.sub(r"[^0-9A-Za-z_.-]+", "-", file_stem).strip("-")
    clean_stem = (clean_stem or "scenario")[:96]
    return f"{category}_{clean_stem}_{digest}"


def load_titles(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise PipelineError(f"标题库必须是 JSON 对象: {path}")
    return {str(key): str(value) for key, value in data.items()}


def extract_sections(
    filepath: str | os.PathLike[str],
    titles: Mapping[str, str] | None = None,
) -> list[str]:
    """Extract legacy Magia Record Section/Branch navigation labels."""

    title_map = TITLES if titles is None else titles
    headers: list[str] = []
    path = Path(filepath)
    if not path.exists():
        return headers

    try:
        with path.open("r", encoding="utf-8-sig", newline=None) as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not (line.startswith("---") and "Section" in line):
                    continue

                source_match = re.search(
                    r"\(Source:\s*(.+?\.json)\s*\)",
                    line,
                    flags=re.I,
                )
                file_id = ""
                if source_match:
                    file_id = Path(source_match.group(1).strip()).stem

                sec_match = re.search(r"Section\s*(\d+)", line, flags=re.I)
                branch_match = re.search(
                    r"(?:Branch|group_)\s*_?\s*(\d+)",
                    line,
                    flags=re.I,
                )
                if not sec_match:
                    continue

                base_sec = f"Section {sec_match.group(1)}"
                if branch_match:
                    base_sec += f" - Branch {branch_match.group(1)}"
                title_part = (
                    f" : {title_map[file_id]}"
                    if file_id and file_id in title_map
                    else ""
                )
                headers.append(f"{file_id} {base_sec}{title_part}".strip())
    except (OSError, UnicodeError):
        return []
    return headers


def _cell(cells: Sequence[Any], index: int) -> Any:
    if index < 0 or index >= len(cells):
        return ""
    return cells[index]


def extract_exedra_dialogue_rows(
    data: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract display/search rows from an Exedra spreadsheet JSON.

    Headers are resolved by name for every sheet.  Duplicate sheets are
    fingerprinted so the one known duplicate-sheet fixture is not repeated.
    ``OnlyText`` with an empty Name is retained instead of silently discarded.
    """

    diagnostics: list[str] = []
    extracted: list[dict[str, Any]] = []
    sheet_list = data.get("sheetList")
    if not isinstance(sheet_list, list):
        return [], ["缺少 sheetList 数组"]

    seen_sheet_fingerprints: set[str] = set()
    for sheet_index, sheet in enumerate(sheet_list):
        if not isinstance(sheet, dict):
            diagnostics.append(f"sheetList[{sheet_index}] 不是对象")
            continue

        header_cells = sheet.get("headerRow", {}).get("cellList")
        content_rows = sheet.get("contentRowList")
        if not isinstance(header_cells, list) or not isinstance(content_rows, list):
            diagnostics.append(f"sheetList[{sheet_index}] 缺少表头或内容行")
            continue

        headers = [str(cell).strip() if cell is not None else "" for cell in header_cells]
        action_index = headers.index("ActionType") if "ActionType" in headers else -1
        comment_index = headers.index("Comment") if "Comment" in headers else -1
        name_index = headers.index("Name") if "Name" in headers else -1
        if action_index < 0 or comment_index < 0:
            diagnostics.append(
                f"sheetList[{sheet_index}] 缺少 ActionType/Comment 表头"
            )
            continue

        sheet_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(content_rows):
            if not isinstance(row, dict) or not isinstance(row.get("cellList"), list):
                diagnostics.append(
                    f"sheetList[{sheet_index}].contentRowList[{row_index}] 非法"
                )
                continue
            cells = row["cellList"]
            action_raw = str(_cell(cells, action_index) or "").strip()
            action = action_raw.casefold()
            comment_value = _cell(cells, comment_index)
            if action not in EXEDRA_TEXT_ACTIONS or not isinstance(comment_value, str):
                continue
            text = comment_value.strip()
            if not text:
                continue
            name = str(_cell(cells, name_index) or "").strip() if name_index >= 0 else ""
            sheet_rows.append(
                {
                    "sheet_index": sheet_index,
                    "row_number": row.get("rowNumber", row_index + 2),
                    "action": action_raw,
                    "speaker": name,
                    "text": text,
                }
            )

        fingerprint_payload = [
            (row["action"], row["speaker"], row["text"]) for row in sheet_rows
        ]
        fingerprint = json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if fingerprint in seen_sheet_fingerprints:
            diagnostics.append(f"sheetList[{sheet_index}] 与前一工作表重复，已去重")
            continue
        seen_sheet_fingerprints.add(fingerprint)
        extracted.extend(sheet_rows)

    return extracted, diagnostics


def load_exedra_dialogue_rows(
    path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Exedra JSON 读取失败: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError(f"Exedra JSON 顶层必须是对象: {path}")
    return extract_exedra_dialogue_rows(data)


def _new_story_record(
    *,
    story_id: str,
    raw_id: str,
    file_stem: str,
    category: str,
    folder: str,
    title: str,
) -> dict[str, Any]:
    return {
        "id": story_id,
        "raw_id": raw_id,
        "file_stem": file_stem,
        "category": category,
        "folder": folder,
        "cn_path": "",
        "jp_path": "",
        "has_cn": False,
        "has_jp": False,
        "sections": [],
        "title": title,
        "filename_cn": "",
        "filename_jp": "",
    }


def _set_language_source(
    story: MutableMapping[str, Any],
    *,
    lang_key: str,
    web_path: str,
    source_filename: str,
    sections: Sequence[str],
) -> None:
    if lang_key not in {"cn", "jp"}:
        raise PipelineError(f"不支持的站内语言槽: {lang_key}")
    existing_path = str(
        story.get(f"{lang_key}_path")
        or story.get(f"path_{lang_key}")
        or ""
    )
    if story.get(f"has_{lang_key}") or existing_path:
        raise PipelineError(
            f"{story.get('id', '<unknown>')}: {lang_key} 语言槽被重复写入: "
            f"{existing_path}, {web_path}"
        )
    story[f"{lang_key}_path"] = web_path
    story[f"path_{lang_key}"] = web_path
    # cn_path/jp_path are internal builder names retained for compatibility.
    story[f"has_{lang_key}"] = True
    story[f"filename_{lang_key}"] = source_filename
    if sections and (lang_key == "cn" or not story.get("sections")):
        story["sections"] = list(sections)


def _copy_to_stage(source: Path, destination: Path) -> None:
    if not source.is_file() or _is_link_like(source):
        raise PipelineError(f"拒绝复制非普通来源文件: {source}")
    if destination.exists():
        raise PipelineError(f"staging 目标冲突，拒绝覆盖: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _collect_magireco_directory(
    *,
    base_dir: Path,
    lang_key: str,
    logical_sources: MutableMapping[str, dict[str, Any]],
    source_audit: SourceAudit,
    stats: Counter[str],
) -> None:
    if not base_dir.exists():
        stats[f"magireco_{lang_key}_missing"] += 1
        return

    base_dir = _absolute_lexical(base_dir)
    for source_path, relative, is_directory in _plain_tree_entries(base_dir):
        if is_directory or source_path.suffix.casefold() != ".txt":
            continue
        if "WEBSITE_DATA" in relative.parts:
            continue

        identity_key, parent_parts, file_stem = magireco_source_identity(
            base_dir,
            source_path,
        )
        raw_id = file_stem.split("_")[0]
        if not raw_id:
            raise PipelineError(f"无法从文件名取得旧格式 ID: {source_path}")

        category = get_category("/".join(parent_parts))
        folder_name = parent_parts[-1] if parent_parts else category
        source_audit.expect(source_path)
        record = logical_sources.get(identity_key)
        if record is None:
            record = {
                "identity": "/".join((*parent_parts, file_stem)),
                "parent_parts": parent_parts,
                "file_stem": file_stem,
                "raw_id": raw_id,
                "category": category,
                "folder": folder_name,
                "sources": {},
                "language_stems": {},
            }
            logical_sources[identity_key] = record
        else:
            identity_fields = (
                record["file_stem"],
                record["raw_id"],
                record["category"],
            )
            new_fields = (file_stem, raw_id, category)
            if identity_fields != new_fields:
                raise PipelineError(
                    f"规范化来源身份冲突: {record['identity']}, "
                    f"{source_path}"
                )

        sources = record["sources"]
        if lang_key in sources:
            raise PipelineError(
                f"同一逻辑故事存在多个 {lang_key} 输入: "
                f"{sources[lang_key]}, {source_path}"
            )
        sources[lang_key] = source_path
        record["language_stems"][lang_key] = file_stem
        stats[f"magireco_{lang_key}_txt"] += 1


MAGIRECO_ALIAS_SECTION_RE = re.compile(
    r"^--- ?\[Section \d+(?: - Branch \d+)?\] "
    r"\(Source: [^()\r\n]+\.json\) ---$",
)


def _normalized_magireco_alias_text(source_path: Path) -> str:
    """Normalize only proven format-only legacy Section differences."""

    try:
        text = source_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise PipelineError(
            f"旧格式 TXT 无法按 UTF-8 读取: {source_path}: {error}"
        ) from error
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Ignore only the presence of the one terminating newline. Additional
    # blank lines remain significant.
    if text.endswith("\n"):
        text = text[:-1]
    lines = text.split("\n")
    normalized_lines: list[str] = []
    for line in lines:
        if MAGIRECO_ALIAS_SECTION_RE.fullmatch(line) is None:
            normalized_lines.append(line)
            continue
        normalized_lines.append(
            f"---{line[4:]}" if line.startswith("--- ") else line
        )
    return "\n".join(normalized_lines)


def _magireco_redundant_alias_base(file_stem: str) -> str | None:
    """Map ``story_N-N`` to ``story_N`` only when both N values match."""

    match = re.fullmatch(
        r"(?P<prefix>.+)_(?P<section>\d+)-(?P=section)",
        file_stem,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return f"{match.group('prefix')}_{match.group('section')}"


def _deduplicate_magireco_format_aliases(
    logical_sources: MutableMapping[str, dict[str, Any]],
    stats: Counter[str],
) -> None:
    """Remove only byte-semantic duplicate ``N-N`` filename aliases.

    Some old source folders contain both ``story_N.txt`` and
    ``story_N-N.txt``.  They are aliases only when their decoded text is
    identical after normalizing BOM/newlines/final newline and the known
    ``--- [Section`` versus ``---[Section`` header-space variant.  Any dialogue,
    speaker, punctuation, or other whitespace difference keeps both records.
    Scene0 remains exact because its suffixes carry branch identity.
    """

    buckets: dict[
        tuple[str, tuple[str, ...], str],
        list[tuple[str, dict[str, Any]]],
    ] = {}
    for identity_key, record in logical_sources.items():
        if str(record["category"]).startswith("scene0_"):
            continue
        bucket_key = (
            str(record["category"]).casefold(),
            tuple(str(part).casefold() for part in record["parent_parts"]),
            str(record["raw_id"]).casefold(),
        )
        buckets.setdefault(bucket_key, []).append((identity_key, record))

    for records in buckets.values():
        if len(records) < 2:
            continue
        by_stem = {
            str(record["file_stem"]).casefold(): (identity_key, record)
            for identity_key, record in records
        }
        bucket_changed = False
        for alias_key, alias_record in sorted(
            records,
            key=lambda item: str(item[1]["file_stem"]).casefold(),
        ):
            alias_stem = str(alias_record["file_stem"])
            base_stem = _magireco_redundant_alias_base(alias_stem)
            if base_stem is None:
                continue
            base_entry = by_stem.get(base_stem.casefold())
            if base_entry is None:
                continue
            _, base_record = base_entry

            for lang_key in ("jp", "cn"):
                alias_source = alias_record["sources"].get(lang_key)
                base_source = base_record["sources"].get(lang_key)
                if alias_source is None or base_source is None:
                    continue
                if (
                    _normalized_magireco_alias_text(alias_source)
                    != _normalized_magireco_alias_text(base_source)
                ):
                    stats["magireco_alias_content_mismatches"] += 1
                    continue

                aliases = base_record.setdefault("all_sources", {}).setdefault(
                    lang_key,
                    [],
                )
                aliases.append(alias_source)
                del alias_record["sources"][lang_key]
                alias_record.get("language_stems", {}).pop(lang_key, None)
                stats["magireco_format_alias_sources"] += 1
                bucket_changed = True

            if not alias_record["sources"]:
                del logical_sources[alias_key]
                stats["magireco_format_alias_records"] += 1

        if bucket_changed:
            stats["magireco_format_alias_groups"] += 1


MAGIRECO_READER_SECTION_RE = re.compile(
    r"^---\s*\[Section\s+(\d+)"
    r"(?:\s+-\s+Branch\s+(\d+))?\]\s*"
    r"\(Source:\s*[^()\r\n]+\.json\s*\)\s*---$",
    flags=re.I,
)
MAGIRECO_READER_SPEAKER_SEPARATOR_RE = re.compile(r"[:：﹕︰︓]")
MAGIRECO_READER_CHOICE_RE = re.compile(
    r"^(?:选项|選択肢|Choice)\s*[:：]\s*"
    r"【?(.+?)】?\s*(?:→|->)\s*(\S+)",
    flags=re.I,
)
MAGIRECO_READER_CHAPTER_SPEAKER_RE = re.compile(
    r"^(?:第\s*\d+\s*[话話章章节節回幕]|"
    r"(?:chapter|episode)\s*\d+)$",
    flags=re.I,
)


def _magireco_reader_structure_signature(
    source_path: Path,
) -> tuple[tuple[Any, ...], ...]:
    """Return the reader-visible block/speaker recurrence structure.

    The signature intentionally ignores translated speaker names, dialogue
    text length, and JSON source suffixes.  It preserves Section positions,
    narration/dialogue/choice kinds, consecutive-speaker block merging, and
    the recurrence pattern of every distinct speaker.  That validates the
    existing utterance-level alignment without ever attempting physical-line
    alignment.
    """

    try:
        text = source_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise PipelineError(
            f"审计配对 TXT 无法按 UTF-8 读取: {source_path}: {error}"
        ) from error

    speaker_classes: dict[str, int] = {}
    signature: list[tuple[Any, ...]] = []
    previous_merge_speaker: str | None = None
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\0", "")
    )
    for line_number, raw_line in enumerate(normalized.split("\n"), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("@S0\t"):
            raise PipelineError(
                f"审计配对只允许普通 TXT，发现 Scene0 行: "
                f"{source_path}:{line_number}"
            )
        if line.startswith("---"):
            section = MAGIRECO_READER_SECTION_RE.fullmatch(line)
            if section is None:
                raise PipelineError(
                    f"审计配对含阅读器无法严格识别的 Section: "
                    f"{source_path}:{line_number}"
                )
            signature.append(
                ("header", section.group(1), section.group(2) or "")
            )
            previous_merge_speaker = None
            continue
        if MAGIRECO_READER_CHOICE_RE.match(line):
            signature.append(("choice",))
            previous_merge_speaker = None
            continue

        separator = MAGIRECO_READER_SPEAKER_SEPARATOR_RE.search(line)
        separator_index = separator.start() if separator is not None else -1
        possible_speaker = (
            line[:separator_index].strip() if separator_index > 0 else ""
        )
        is_speaker_line = (
            separator_index > 0
            and separator_index <= 64
            and not line.startswith("[")
            and re.fullmatch(
                r"(?:https?|file|data)",
                possible_speaker,
                flags=re.I,
            )
            is None
            and not possible_speaker.isdigit()
            and MAGIRECO_READER_CHAPTER_SPEAKER_RE.fullmatch(
                possible_speaker
            )
            is None
            and re.search(r"[<>{}]", possible_speaker) is None
        )
        if is_speaker_line:
            speaker = re.sub(r"\s+", "", possible_speaker) or "旁白"
            is_narration = (
                re.fullmatch(
                    r"(?:Narration|ナレーション|旁白)",
                    speaker,
                    flags=re.I,
                )
                is not None
            )
            kind = "narration" if is_narration else "dialogue"
            if is_narration:
                speaker = "旁白"
        else:
            kind = "narration"
            speaker = "旁白"

        if previous_merge_speaker == speaker:
            continue
        previous_merge_speaker = speaker
        if kind == "dialogue":
            speaker_class = speaker_classes.setdefault(
                speaker,
                len(speaker_classes) + 1,
            )
            signature.append((kind, speaker_class))
        else:
            signature.append((kind,))

    if not signature:
        raise PipelineError(f"审计配对 TXT 没有可读内容: {source_path}")
    return tuple(signature)


def _merge_audited_magireco_pair(
    logical_sources: MutableMapping[str, dict[str, Any]],
    *,
    cn_identity: str,
    jp_identity: str,
    stats: Counter[str],
    partial_cn_prefix: bool,
) -> bool:
    """Merge one explicit CN/JP identity pair after structural validation."""

    cn_key = _normalize_identity_text(cn_identity).casefold()
    jp_key = _normalize_identity_text(jp_identity).casefold()
    cn_record = logical_sources.get(cn_key)
    jp_record = logical_sources.get(jp_key)
    if cn_record is None and jp_record is None:
        return False
    if cn_record is None or jp_record is None:
        missing = cn_identity if cn_record is None else jp_identity
        raise PipelineError(f"审计配对只出现一侧，拒绝猜测合并: {missing}")
    if cn_key == jp_key:
        raise PipelineError(f"审计配对的中日来源身份相同: {cn_identity}")
    if set(cn_record["sources"]) != {"cn"}:
        raise PipelineError(f"审计配对中文来源方向异常: {cn_identity}")
    if set(jp_record["sources"]) != {"jp"}:
        raise PipelineError(f"审计配对日文来源方向异常: {jp_identity}")
    if (
        str(cn_record["identity"]).casefold() != cn_identity.casefold()
        or str(jp_record["identity"]).casefold() != jp_identity.casefold()
    ):
        raise PipelineError(f"审计配对来源身份不一致: {cn_identity}")
    if (
        cn_record["raw_id"] != jp_record["raw_id"]
        or cn_record["category"] != jp_record["category"]
        or str(cn_record["category"]).startswith("scene0_")
    ):
        raise PipelineError(f"审计配对元数据不一致: {cn_identity}")

    cn_signature = _magireco_reader_structure_signature(
        cn_record["sources"]["cn"]
    )
    jp_signature = _magireco_reader_structure_signature(
        jp_record["sources"]["jp"]
    )
    if partial_cn_prefix:
        cn_headers = [
            index
            for index, token in enumerate(cn_signature)
            if token[0] == "header"
        ]
        jp_next_header = next(
            (
                index
                for index, token in enumerate(jp_signature[1:], start=1)
                if token[0] == "header"
            ),
            len(jp_signature),
        )
        jp_headers = [
            token for token in jp_signature if token[0] == "header"
        ]
        signatures_match = (
            cn_headers == [0]
            and jp_headers
            == [
                ("header", str(section), "")
                for section in range(1, 8)
            ]
            and cn_signature == jp_signature[:jp_next_header]
        )
    else:
        signatures_match = cn_signature == jp_signature
    if not signatures_match:
        raise PipelineError(
            "审计配对的 Section/说话轮次结构不一致，拒绝合并: "
            f"{cn_identity}, {jp_identity}"
        )

    merged = dict(cn_record)
    # The old public catalogue displayed the JP-side folder label while each
    # language retained its own physical parent path.  Preserve that UI
    # contract even though the stable audited identity is the CN identity.
    merged["parent_parts"] = tuple(
        str(part) for part in jp_record["parent_parts"]
    )
    merged["folder"] = jp_record["folder"]
    merged["sources"] = {
        "cn": cn_record["sources"]["cn"],
        "jp": jp_record["sources"]["jp"],
    }
    merged["language_stems"] = {
        "cn": cn_record["language_stems"]["cn"],
        "jp": jp_record["language_stems"]["jp"],
    }
    merged["language_parent_parts"] = {
        "cn": tuple(str(part) for part in cn_record["parent_parts"]),
        "jp": tuple(str(part) for part in jp_record["parent_parts"]),
    }
    all_sources: dict[str, list[Path]] = {}
    for lang_key, source_record in (("cn", cn_record), ("jp", jp_record)):
        aliases = list(
            source_record.get("all_sources", {}).get(lang_key, ())
        )
        if aliases:
            all_sources[lang_key] = aliases
    if all_sources:
        merged["all_sources"] = all_sources
    else:
        merged.pop("all_sources", None)

    del logical_sources[jp_key]
    logical_sources[cn_key] = merged
    stats[
        "magireco_audited_partial_pairs"
        if partial_cn_prefix
        else "magireco_audited_cross_folder_pairs"
    ] += 1
    return True


def _pair_audited_magireco_sources(
    logical_sources: MutableMapping[str, dict[str, Any]],
    stats: Counter[str],
    *,
    require_all: bool,
) -> None:
    """Apply only the reviewed cross-folder pairings."""

    satisfied: set[str] = set()
    for raw_id, (cn_identity, jp_identity) in (
        MAGIRECO_AUDITED_CROSS_FOLDER_PAIRS.items()
    ):
        if _merge_audited_magireco_pair(
            logical_sources,
            cn_identity=cn_identity,
            jp_identity=jp_identity,
            stats=stats,
            partial_cn_prefix=False,
        ):
            satisfied.add(raw_id)

    if require_all:
        expected = set(MAGIRECO_AUDITED_CROSS_FOLDER_PAIRS)
        missing = sorted(expected - satisfied)
        if missing:
            raise PipelineError(
                "完整 Magia Record 语料缺少审计配对目标: "
                + ", ".join(missing)
            )


def _pair_unique_magireco_range_variants(
    logical_sources: MutableMapping[str, dict[str, Any]],
    stats: Counter[str],
) -> None:
    """Pair one JP-only and one CN-only numeric range without touching text."""

    buckets: dict[
        tuple[str, tuple[str, ...], str],
        list[tuple[str, dict[str, Any]]],
    ] = {}
    for identity_key, record in logical_sources.items():
        if str(record["category"]).startswith("scene0_"):
            continue
        bucket_key = (
            str(record["category"]).casefold(),
            tuple(str(part).casefold() for part in record["parent_parts"]),
            str(record["raw_id"]).casefold(),
        )
        buckets.setdefault(bucket_key, []).append((identity_key, record))

    for records in buckets.values():
        if len(records) != 2:
            continue
        jp_only = [
            item for item in records if set(item[1]["sources"]) == {"jp"}
        ]
        cn_only = [
            item for item in records if set(item[1]["sources"]) == {"cn"}
        ]
        if len(jp_only) != 1 or len(cn_only) != 1:
            continue

        jp_key, jp_record = jp_only[0]
        cn_key, cn_record = cn_only[0]
        raw_id = str(jp_record["raw_id"])
        range_stem_re = re.compile(
            rf"^{re.escape(raw_id)}_(\d+)(?:-(\d+))?$",
            flags=re.IGNORECASE,
        )
        jp_stem = str(jp_record["file_stem"])
        cn_stem = str(cn_record["file_stem"])
        jp_range = range_stem_re.fullmatch(jp_stem)
        cn_range = range_stem_re.fullmatch(cn_stem)
        if not re.fullmatch(r"\d+(?:-\d+)*", raw_id) or not jp_range or not cn_range:
            continue
        jp_start = int(jp_range.group(1))
        jp_end = int(jp_range.group(2) or jp_range.group(1))
        cn_start = int(cn_range.group(1))
        cn_end = int(cn_range.group(2) or cn_range.group(1))
        if (
            jp_end < jp_start
            or cn_end < cn_start
            or max(jp_start, cn_start) > min(jp_end, cn_end)
        ):
            continue

        parent_parts = tuple(str(part) for part in jp_record["parent_parts"])
        identity = (
            "/".join((*parent_parts, raw_id))
            + f"[cn={cn_stem};jp={jp_stem}]"
        )
        merged_key = identity.casefold()
        if merged_key in logical_sources and merged_key not in {jp_key, cn_key}:
            raise PipelineError(f"区间变体配对后的来源身份冲突: {identity}")
        merged = {
            "identity": identity,
            "parent_parts": parent_parts,
            "file_stem": raw_id,
            "raw_id": raw_id,
            "category": jp_record["category"],
            "folder": jp_record["folder"],
            "sources": {
                "jp": jp_record["sources"]["jp"],
                "cn": cn_record["sources"]["cn"],
            },
            "language_stems": {
                "jp": jp_stem,
                "cn": cn_stem,
            },
        }
        all_sources: dict[str, list[Path]] = {}
        for lang_key, source_record in (
            ("jp", jp_record),
            ("cn", cn_record),
        ):
            aliases = list(
                source_record.get("all_sources", {}).get(lang_key, ())
            )
            if aliases:
                all_sources[lang_key] = aliases
        if all_sources:
            merged["all_sources"] = all_sources
        del logical_sources[jp_key]
        del logical_sources[cn_key]
        logical_sources[merged_key] = merged
        stats["magireco_range_variant_pairs"] += 1


def _allocate_magireco_ids(
    logical_sources: Mapping[str, Mapping[str, Any]],
    stats: Counter[str],
) -> dict[str, str]:
    candidate_groups: dict[str, list[str]] = {}
    candidates: dict[str, str] = {}
    for identity_key, record in logical_sources.items():
        category = str(record["category"])
        if category.startswith("scene0_"):
            candidate = safe_scene0_story_id(
                category,
                str(record["folder"]),
                str(record["file_stem"]),
            )
        else:
            candidate = str(record["raw_id"])
        candidates[identity_key] = candidate
        candidate_groups.setdefault(candidate.casefold(), []).append(identity_key)

    allocated: dict[str, str] = {}
    seen_ids: dict[str, str] = {}
    for candidate_key in sorted(candidate_groups):
        identities = sorted(candidate_groups[candidate_key])
        collided = len(identities) > 1
        if collided:
            stats["magireco_legacy_id_collision_groups"] += 1
            stats["magireco_collision_stories"] += len(identities)
        for identity_key in identities:
            record = logical_sources[identity_key]
            story_id = (
                safe_magireco_collision_id(
                    str(record["category"]),
                    str(record["identity"]),
                    str(record["file_stem"]),
                )
                if collided
                else candidates[identity_key]
            )
            normalized_id = story_id.casefold()
            previous = seen_ids.get(normalized_id)
            if previous is not None:
                raise PipelineError(
                    f"分配后仍有重复 story id: {story_id}: "
                    f"{previous}, {record['identity']}"
                )
            seen_ids[normalized_id] = str(record["identity"])
            allocated[identity_key] = story_id
    return allocated


def _attach_magireco_legacy_route_aliases(
    logical_sources: MutableMapping[str, dict[str, Any]],
    allocated_ids: Mapping[str, str],
    stats: Counter[str],
    *,
    require_all: bool,
) -> None:
    """Preserve only audited old routes that resolve to the exact same story."""

    records_by_raw_id: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for identity_key, record in logical_sources.items():
        raw_id = str(record["raw_id"]).casefold()
        records_by_raw_id.setdefault(raw_id, []).append(
            (identity_key, record)
        )

    satisfied: set[str] = set()
    for legacy_id, expected_identity in MAGIRECO_LEGACY_ROUTE_IDENTITIES.items():
        records = records_by_raw_id.get(legacy_id.casefold(), [])
        if not records:
            continue
        matches = [
            (identity_key, record)
            for identity_key, record in records
            if str(record["identity"]).casefold()
            == expected_identity.casefold()
        ]
        if not matches:
            continue
        if len(matches) != 1:
            raise PipelineError(
                "安全旧路由的来源身份不唯一: "
                f"{legacy_id}: {expected_identity}"
            )
        identity_key, record = matches[0]
        canonical_id = allocated_ids[identity_key]
        satisfied.add(legacy_id)
        if canonical_id.casefold() == legacy_id.casefold():
            continue
        record["legacy_ids"] = [legacy_id]
        stats["magireco_legacy_route_aliases"] += 1
    if require_all:
        missing = sorted(
            set(MAGIRECO_LEGACY_ROUTE_IDENTITIES) - satisfied
        )
        if missing:
            raise PipelineError(
                "完整 Magia Record 语料缺少安全旧路由目标: "
                + ", ".join(missing)
            )


def scan_magireco_sources(
    *,
    jp_dir: Path,
    cn_dir: Path,
    staging_data_dir: Path,
    story_map: MutableMapping[str, dict[str, Any]],
    titles: Mapping[str, str],
    stats: Counter[str],
    source_audit: SourceAudit,
    require_legacy_route_aliases: bool,
) -> None:
    """Collect both languages first, then publish exact logical identities."""

    logical_sources: dict[str, dict[str, Any]] = {}
    _collect_magireco_directory(
        base_dir=jp_dir,
        lang_key="jp",
        logical_sources=logical_sources,
        source_audit=source_audit,
        stats=stats,
    )
    _collect_magireco_directory(
        base_dir=cn_dir,
        lang_key="cn",
        logical_sources=logical_sources,
        source_audit=source_audit,
        stats=stats,
    )
    _deduplicate_magireco_format_aliases(logical_sources, stats)
    _pair_audited_magireco_sources(
        logical_sources,
        stats,
        require_all=require_legacy_route_aliases,
    )
    _pair_unique_magireco_range_variants(logical_sources, stats)
    allocated_ids = _allocate_magireco_ids(logical_sources, stats)
    _attach_magireco_legacy_route_aliases(
        logical_sources,
        allocated_ids,
        stats,
        require_all=require_legacy_route_aliases,
    )

    for identity_key in sorted(logical_sources):
        record = logical_sources[identity_key]
        story_id = allocated_ids[identity_key]
        if story_id in story_map:
            raise PipelineError(f"重复 story id: {story_id}")
        file_stem = str(record["file_stem"])
        raw_id = str(record["raw_id"])
        category = str(record["category"])
        parent_parts = tuple(str(part) for part in record["parent_parts"])
        story = _new_story_record(
            story_id=story_id,
            raw_id=raw_id,
            file_stem=file_stem,
            category=category,
            folder=str(record["folder"]),
            title=(
                titles.get(file_stem)
                or titles.get(raw_id)
                or titles.get(
                    str(record.get("language_stems", {}).get("jp") or "")
                )
                or titles.get(
                    str(record.get("language_stems", {}).get("cn") or "")
                )
                or ""
            ),
        )
        story["game"] = "magireco"
        story["source_identity"] = str(record["identity"])
        if record.get("legacy_ids"):
            story["legacy_ids"] = list(record["legacy_ids"])

        for lang_key in ("jp", "cn"):
            source_path = record["sources"].get(lang_key)
            if source_path is None:
                continue
            language_parent_parts = tuple(
                str(part)
                for part in record.get("language_parent_parts", {}).get(
                    lang_key,
                    parent_parts,
                )
            )
            # Known source category roots are replaced by the normalized
            # public category. Unknown roots (for example ``special``) are
            # meaningful legacy folders and must remain in the published URL.
            # Audited cross-folder pairs retain each language's original
            # parent, preserving every production URL.
            destination_tail = (
                language_parent_parts[1:]
                if (
                    language_parent_parts
                    and get_category(language_parent_parts[0])
                    != "Unclassified"
                )
                else language_parent_parts
            )
            destination_rel = Path(category, *destination_tail)
            language_stem = str(
                record.get("language_stems", {}).get(lang_key)
                or file_stem
            )
            destination_filename = f"{language_stem}_{lang_key}.txt"
            destination_path = (
                staging_data_dir / destination_rel / destination_filename
            )
            _copy_to_stage(source_path, destination_path)
            web_path = (
                f"/data/{sanitize_path(destination_rel)}/"
                f"{destination_filename}"
            )
            _set_language_source(
                story,
                lang_key=lang_key,
                web_path=web_path,
                source_filename=source_path.name,
                sections=extract_sections(source_path, titles),
            )
            source_audit.claim(
                source_path,
                story_id=story_id,
                lang_key=lang_key,
                web_path=web_path,
            )
            for variant_source in record.get("all_sources", {}).get(
                lang_key,
                (),
            ):
                if variant_source == source_path:
                    continue
                variant_stem = _normalize_identity_text(
                    strip_lang_suffix_filename(variant_source.name)
                )
                compatibility_filename = (
                    f"{variant_stem}_{lang_key}.txt"
                )
                compatibility_path = (
                    staging_data_dir
                    / destination_rel
                    / compatibility_filename
                )
                _copy_to_stage(variant_source, compatibility_path)
                source_audit.claim(
                    variant_source,
                    story_id=story_id,
                    lang_key=lang_key,
                    web_path=web_path,
                )
                stats["magireco_compatibility_alias_files"] += 1
        story_map[story_id] = story

    stats["magireco_logical_stories"] = len(logical_sources)
    stats["magireco_paired_stories"] = sum(
        1
        for record in logical_sources.values()
        if set(record["sources"]) == {"jp", "cn"}
    )


def get_exedra_category(raw_category: str) -> str:
    normalized = re.sub(r"_full$", "", raw_category, flags=re.I)
    for source_name, category in EXEDRA_CATEGORY_MAP.items():
        if normalized.casefold() == source_name.casefold():
            return category
    return "exedra_unclassified"


def _humanize_exedra_title(file_stem: str) -> str:
    return file_stem.replace("_", " ").strip()


@dataclass(frozen=True)
class OrganizedExedraGroup:
    manifest_id: str
    raw_category: str
    category: str
    group_key: str
    output_dir: Path
    text_file: Path
    source_paths: tuple[str, ...]
    source_names: tuple[str, ...]
    title: str


@dataclass(frozen=True)
class ExedraSectionAlignment:
    number: int
    source_name: str
    reader_block_count: int
    speaker_sequence_sha256: str


def _manifest_relative_path(value: Any, *, field_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"Exedra manifest 的 {field_name} 必须是非空字符串")
    if "\\" in value:
        raise PipelineError(
            f"Exedra manifest 的 {field_name} 必须使用 POSIX 路径: {value!r}"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PipelineError(
            f"Exedra manifest 的 {field_name} 不是安全相对路径: {value!r}"
        )
    return Path(*pure.parts)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_utf8_text_file(path: Path) -> str:
    """Hash the decoded text exactly as the schema-v1 importer does."""

    try:
        value = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise PipelineError(f"Exedra TXT 无法按 UTF-8 读取: {path}: {error}") from error
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_exedra_section_sources(path: Path) -> list[str]:
    sources: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline=None) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line.startswith("---"):
                continue
            match = EXEDRA_SECTION_RE.fullmatch(line)
            if not match:
                raise PipelineError(
                    f"Exedra TXT 含非规范章节头: {path}:{line_number}: {line}"
                )
            section_number = int(match.group(1))
            expected_number = len(sources) + 1
            if section_number != expected_number:
                raise PipelineError(
                    f"Exedra TXT Section 不连续: {path}:{line_number}: "
                    f"期望 {expected_number}，实际 {section_number}"
                )
            source_name = PurePosixPath(match.group(2).strip()).name
            if not source_name.lower().endswith(".json"):
                raise PipelineError(
                    f"Exedra TXT Section 来源不是 JSON: {path}:{line_number}"
                )
            sources.append(source_name)
    if not sources:
        raise PipelineError(f"Exedra 合并 TXT 缺少 Section 来源头: {path}")
    return sources


def _normalize_exedra_speaker(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _exedra_speaker_identity(speaker: str) -> tuple[str, ...]:
    if speaker in EXEDRA_NARRATION_SPEAKERS:
        return ("@narration",)
    return tuple(part for part in re.split(r"[＆&]", speaker) if part)


def _exedra_sequence_hash(
    signatures: Sequence[tuple[str, tuple[str, ...]]],
) -> str:
    serialized = [
        {"kind": kind, "speaker": list(speaker)}
        for kind, speaker in signatures
    ]
    value = json.dumps(
        serialized,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _exedra_alignment_sections(path: Path) -> tuple[ExedraSectionAlignment, ...]:
    """Independently reproduce the importer's Section-local reader blocks."""

    sections: list[ExedraSectionAlignment] = []
    current_number: int | None = None
    current_source = ""
    previous_speaker: str | None = None
    signatures: list[tuple[str, tuple[str, ...]]] = []

    def flush() -> None:
        nonlocal current_number, current_source, previous_speaker, signatures
        if current_number is None:
            return
        sections.append(
            ExedraSectionAlignment(
                number=current_number,
                source_name=current_source,
                reader_block_count=len(signatures),
                speaker_sequence_sha256=_exedra_sequence_hash(signatures),
            )
        )
        current_number = None
        current_source = ""
        previous_speaker = None
        signatures = []

    try:
        handle = path.open("r", encoding="utf-8-sig", newline=None)
    except OSError as error:
        raise PipelineError(f"Exedra TXT 无法读取: {path}: {error}") from error
    try:
        with handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("---"):
                    match = EXEDRA_SECTION_RE.fullmatch(line)
                    if not match:
                        raise PipelineError(
                            f"Exedra TXT 含非规范章节头: "
                            f"{path}:{line_number}: {line}"
                        )
                    flush()
                    section_number = int(match.group(1))
                    expected_number = len(sections) + 1
                    if section_number != expected_number:
                        raise PipelineError(
                            f"Exedra TXT Section 不连续: {path}:{line_number}: "
                            f"期望 {expected_number}，实际 {section_number}"
                        )
                    current_number = section_number
                    current_source = PurePosixPath(
                        match.group(2).strip()
                    ).name
                    continue
                if current_number is None:
                    raise PipelineError(
                        f"Exedra TXT 在第一个 Section 前含正文: "
                        f"{path}:{line_number}"
                    )

                separator_positions = [
                    position
                    for position in (line.find(":"), line.find("："))
                    if position >= 0
                ]
                separator = min(separator_positions) if separator_positions else -1
                if separator > 0:
                    speaker = _normalize_exedra_speaker(line[:separator])
                    text = line[separator + 1 :].strip()
                else:
                    speaker = "旁白"
                    text = line
                if not speaker or not text:
                    raise PipelineError(
                        f"Exedra TXT 含无效事件: {path}:{line_number}: {line}"
                    )
                kind = (
                    "narration"
                    if speaker in EXEDRA_NARRATION_SPEAKERS
                    else "dialogue"
                )
                if speaker != previous_speaker:
                    signatures.append(
                        (kind, _exedra_speaker_identity(speaker))
                    )
                    previous_speaker = speaker
    except UnicodeDecodeError as error:
        raise PipelineError(f"Exedra TXT 无法按 UTF-8 读取: {path}: {error}") from error

    flush()
    if not sections:
        raise PipelineError(f"Exedra 合并 TXT 缺少 Section 来源头: {path}")
    return tuple(sections)


def _exedra_turn_counts(path: Path) -> tuple[list[str], list[int]]:
    sections = _exedra_alignment_sections(path)
    return (
        [section.source_name for section in sections],
        [section.reader_block_count for section in sections],
    )


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _report_mapping(
    value: Any,
    *,
    report_path: Path,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError(
            f"Exedra 中文导入报告字段 {field_name} 必须是对象: {report_path}"
        )
    return value


def _validate_exedra_cn_import_report(
    *,
    group: OrganizedExedraGroup,
    jp_path: Path,
    cn_path: Path,
    jp_sections: Sequence[ExedraSectionAlignment],
    cn_sections: Sequence[ExedraSectionAlignment],
) -> None:
    """Require a schema-v1 proof binding current JP/CN bytes and block order."""

    report_path = cn_path.with_name(
        f"{group.group_key}{EXEDRA_IMPORT_REPORT_SUFFIX}"
    )
    if not report_path.is_file():
        raise PipelineError(
            "Exedra 中文缺少相邻的 schema v1 导入报告，拒绝发布: "
            f"{report_path}"
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PipelineError(
            f"Exedra 中文导入报告无法读取: {report_path}: {error}"
        ) from error
    if not isinstance(report, dict):
        raise PipelineError(f"Exedra 中文导入报告顶层必须是对象: {report_path}")
    if (
        not _is_plain_int(report.get("schemaVersion"))
        or report.get("schemaVersion") != EXEDRA_IMPORT_REPORT_SCHEMA_VERSION
    ):
        raise PipelineError(
            f"Exedra 中文导入报告 schemaVersion 必须为 "
            f"{EXEDRA_IMPORT_REPORT_SCHEMA_VERSION}: {report_path}"
        )
    if report.get("status") != "validated":
        raise PipelineError(
            f"Exedra 中文导入报告状态不是 validated: {report_path}"
        )

    report_group = _report_mapping(
        report.get("group"),
        report_path=report_path,
        field_name="group",
    )
    if (
        report_group.get("category") != group.raw_category
        or report_group.get("groupKey") != group.group_key
    ):
        raise PipelineError(
            "Exedra 中文导入报告 group 与逻辑组不一致: "
            f"{group.manifest_id}: {report_path}"
        )

    validation = _report_mapping(
        report.get("validation"),
        report_path=report_path,
        field_name="validation",
    )
    if validation.get("passed") is not True:
        raise PipelineError(
            f"Exedra 中文导入报告 validation.passed 不是 true: {report_path}"
        )
    mismatch_count = validation.get("mismatchCount")
    if not _is_plain_int(mismatch_count) or mismatch_count != 0:
        raise PipelineError(
            f"Exedra 中文导入报告 mismatchCount 必须为 0: {report_path}"
        )
    for field_name in ("usesLcs", "usesFuzzyMatching", "allowsReordering"):
        if validation.get(field_name) is not False:
            raise PipelineError(
                "Exedra 中文导入报告必须明确禁止 LCS、模糊匹配和重排: "
                f"{field_name}: {report_path}"
            )
    if report.get("mismatches") != []:
        raise PipelineError(
            f"Exedra 中文导入报告 mismatches 必须为空: {report_path}"
        )

    report_jp = _report_mapping(
        report.get("jp"),
        report_path=report_path,
        field_name="jp",
    )
    report_cn = _report_mapping(
        report.get("cn"),
        report_path=report_path,
        field_name="cn",
    )
    current_jp_sha256 = _sha256_utf8_text_file(jp_path)
    current_cn_sha256 = _sha256_utf8_text_file(cn_path)
    jp_sha256 = report_jp.get("contentSha256")
    cn_sha256 = report_cn.get("renderedSha256")
    if not _valid_sha256(jp_sha256) or jp_sha256 != current_jp_sha256:
        raise PipelineError(
            "Exedra 中文导入报告的 JP 内容哈希与当前文件不一致: "
            f"{group.manifest_id}: {report_path}"
        )
    if not _valid_sha256(cn_sha256) or cn_sha256 != current_cn_sha256:
        raise PipelineError(
            "Exedra 中文导入报告的 CN 内容哈希与当前文件不一致: "
            f"{group.manifest_id}: {report_path}"
        )

    section_count = len(jp_sections)
    for side_name, side, sections in (
        ("jp", report_jp, jp_sections),
        ("cn", report_cn, cn_sections),
    ):
        if (
            not _is_plain_int(side.get("sectionCount"))
            or side.get("sectionCount") != section_count
        ):
            raise PipelineError(
                f"Exedra 中文导入报告 {side_name}.sectionCount 不正确: "
                f"{report_path}"
            )
        expected_blocks = sum(
            section.reader_block_count for section in sections
        )
        if (
            not _is_plain_int(side.get("readerNormalizedBlockCount"))
            or side.get("readerNormalizedBlockCount") != expected_blocks
        ):
            raise PipelineError(
                f"Exedra 中文导入报告 {side_name} 总块数不正确: {report_path}"
            )

    report_sections = report.get("sections")
    if not isinstance(report_sections, list) or len(report_sections) != section_count:
        raise PipelineError(
            f"Exedra 中文导入报告 sections 数量不正确: {report_path}"
        )
    for index, (jp_section, cn_section, report_section) in enumerate(
        zip(jp_sections, cn_sections, report_sections),
        start=1,
    ):
        if not isinstance(report_section, dict):
            raise PipelineError(
                f"Exedra 中文导入报告 Section {index} 必须是对象: {report_path}"
            )
        if (
            not _is_plain_int(report_section.get("section"))
            or report_section.get("section") != index
            or report_section.get("source") != jp_section.source_name
            or cn_section.source_name != jp_section.source_name
        ):
            raise PipelineError(
                "Exedra 中文导入报告 Section 编号/来源与当前中日文件不一致: "
                f"{group.manifest_id} Section {index}: {report_path}"
            )
        wiki_episode = report_section.get("wikiEpisode")
        if not _is_plain_int(wiki_episode) or wiki_episode < 0:
            raise PipelineError(
                f"Exedra 中文导入报告 Section {index} 缺少有效 Wiki 编号: "
                f"{report_path}"
            )
        source_episode = re.search(
            r"_(\d+)\.json$",
            jp_section.source_name,
            flags=re.I,
        )
        if (
            source_episode is not None
            and wiki_episode != int(source_episode.group(1))
        ):
            raise PipelineError(
                f"Exedra 中文导入报告 Section {index} 的来源编号与 "
                f"Wiki 编号不一致: {report_path}"
            )

        block_counts = _report_mapping(
            report_section.get("readerNormalizedBlocks"),
            report_path=report_path,
            field_name=f"sections[{index}].readerNormalizedBlocks",
        )
        if (
            not _is_plain_int(block_counts.get("jp"))
            or not _is_plain_int(block_counts.get("cn"))
            or block_counts.get("jp") != jp_section.reader_block_count
            or block_counts.get("cn") != cn_section.reader_block_count
            or block_counts.get("jp") != block_counts.get("cn")
            or block_counts.get("matches") is not True
        ):
            raise PipelineError(
                "Exedra 中文导入报告的逐节 readerNormalizedBlocks "
                f"不匹配: {group.manifest_id} Section {index}: {report_path}"
            )

        sequence_hashes = _report_mapping(
            report_section.get("speakerSequenceSha256"),
            report_path=report_path,
            field_name=f"sections[{index}].speakerSequenceSha256",
        )
        jp_sequence_sha256 = sequence_hashes.get("jp")
        cn_sequence_sha256 = sequence_hashes.get("cn")
        if (
            not _valid_sha256(jp_sequence_sha256)
            or not _valid_sha256(cn_sequence_sha256)
            or jp_sequence_sha256 != cn_sequence_sha256
            or cn_sequence_sha256 != cn_section.speaker_sequence_sha256
        ):
            raise PipelineError(
                "Exedra 中文导入报告的说话人/旁白顺序哈希不匹配，"
                "拒绝按数量放行: "
                f"{group.manifest_id} Section {index}: {report_path}"
            )


def load_exedra_manifest(
    base_dir: Path,
    *,
    stats: Counter[str],
) -> list[OrganizedExedraGroup]:
    """Load and independently verify the organizer's lossless manifest."""

    base_dir = _absolute_lexical(base_dir)
    tree_entries = _plain_tree_entries(base_dir)
    tree_files: dict[str, tuple[Path, str]] = {}
    for path, relative, is_directory in tree_entries:
        if is_directory:
            continue
        relative_name = relative.as_posix()
        relative_key = relative_name.casefold()
        if relative_key in tree_files:
            raise PipelineError(
                f"Exedra 来源存在大小写冲突: "
                f"{tree_files[relative_key][0]}, {path}"
            )
        tree_files[relative_key] = (path, relative_name)

    manifest_path = base_dir / EXEDRA_MANIFEST_NAME
    manifest_record = tree_files.get(EXEDRA_MANIFEST_NAME.casefold())
    if (
        manifest_record is None
        or manifest_record[1] != EXEDRA_MANIFEST_NAME
        or manifest_record[0] != manifest_path
    ):
        raise PipelineError(
            f"Exedra 来源缺少 {EXEDRA_MANIFEST_NAME}: {base_dir}；"
            "请先运行 organize_exedra_scenarios.py"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Exedra manifest 无法读取: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PipelineError("Exedra manifest 顶层必须是对象")
    if manifest.get("schemaVersion") != 1:
        raise PipelineError(
            f"不支持的 Exedra manifest schemaVersion: "
            f"{manifest.get('schemaVersion')!r}"
        )

    category_order = manifest.get("categoryOrder")
    expected_categories = list(EXEDRA_CATEGORY_MAP)
    if category_order != expected_categories:
        raise PipelineError(
            "Exedra manifest categoryOrder 必须严格为: "
            + ", ".join(expected_categories)
        )

    raw_groups = manifest.get("groups")
    raw_sources = manifest.get("sources")
    if not isinstance(raw_groups, list) or not isinstance(raw_sources, list):
        raise PipelineError("Exedra manifest 缺少 groups/sources 数组")

    groups: list[OrganizedExedraGroup] = []
    groups_by_id: dict[str, OrganizedExedraGroup] = {}
    group_source_paths: dict[str, tuple[str, ...]] = {}
    seen_group_keys: set[tuple[str, str]] = set()

    for index, raw_group in enumerate(raw_groups):
        if not isinstance(raw_group, dict):
            raise PipelineError(f"Exedra manifest groups[{index}] 不是对象")
        manifest_id = str(raw_group.get("id") or "").strip()
        raw_category = str(raw_group.get("category") or "").strip()
        group_key = str(raw_group.get("groupKey") or "").strip()
        if not manifest_id or not group_key:
            raise PipelineError(
                f"Exedra manifest groups[{index}] 缺少 id/groupKey"
            )
        if raw_category not in EXEDRA_CATEGORY_MAP:
            raise PipelineError(
                f"Exedra manifest groups[{index}] 类别不受支持: {raw_category}"
            )
        if (
            group_key in {".", ".."}
            or "/" in group_key
            or "\\" in group_key
            or "\0" in group_key
        ):
            raise PipelineError(f"Exedra groupKey 非法: {group_key!r}")
        expected_manifest_id = f"exedra:{raw_category}:{group_key.casefold()}"
        if manifest_id != expected_manifest_id:
            raise PipelineError(
                f"Exedra group id 不稳定: {manifest_id!r}，"
                f"期望 {expected_manifest_id!r}"
            )
        normalized_group_key = (raw_category.casefold(), group_key.casefold())
        if normalized_group_key in seen_group_keys:
            raise PipelineError(
                f"Exedra 逻辑组大小写冲突: {raw_category}/{group_key}"
            )
        seen_group_keys.add(normalized_group_key)

        output_dir = _manifest_relative_path(
            raw_group.get("outputDir"),
            field_name=f"groups[{index}].outputDir",
        )
        text_file = _manifest_relative_path(
            raw_group.get("textFile"),
            field_name=f"groups[{index}].textFile",
        )
        expected_output_dir = Path(raw_category, group_key)
        expected_text_file = expected_output_dir / f"{group_key}_jp.txt"
        if output_dir != expected_output_dir or text_file != expected_text_file:
            raise PipelineError(
                f"Exedra 组输出路径不符合规范: {manifest_id}: "
                f"{output_dir.as_posix()}, {text_file.as_posix()}"
            )
        text_path = base_dir / text_file
        text_record = tree_files.get(text_file.as_posix().casefold())
        if (
            text_record is None
            or text_record[1] != text_file.as_posix()
            or text_record[0] != text_path
            or text_path.stat().st_size <= 0
        ):
            raise PipelineError(f"Exedra 合并 TXT 不存在或为空: {text_path}")
        expected_text_sha = str(
            raw_group.get("textSha256") or ""
        ).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_text_sha):
            raise PipelineError(
                f"Exedra 组缺少有效 textSha256: {manifest_id}"
            )
        if _sha256_file(text_path) != expected_text_sha:
            raise PipelineError(
                f"Exedra 合并 TXT 与 manifest 哈希不一致: {text_path}"
            )

        source_values = raw_group.get("sources")
        if not isinstance(source_values, list) or not source_values:
            raise PipelineError(f"Exedra 组没有来源 JSON: {manifest_id}")
        source_paths = tuple(str(value) for value in source_values)
        if len({value.casefold() for value in source_paths}) != len(source_paths):
            raise PipelineError(f"Exedra 组内来源重复: {manifest_id}")
        if raw_group.get("sourceCount") != len(source_paths):
            raise PipelineError(f"Exedra 组 sourceCount 不正确: {manifest_id}")
        source_names = tuple(PurePosixPath(value).name for value in source_paths)
        section_names = tuple(_read_exedra_section_sources(text_path))
        if section_names != source_names:
            raise PipelineError(
                f"Exedra 合并 TXT 的 Section 来源顺序与 manifest 不一致: "
                f"{manifest_id}"
            )

        group = OrganizedExedraGroup(
            manifest_id=manifest_id,
            raw_category=raw_category,
            category=EXEDRA_CATEGORY_MAP[raw_category],
            group_key=group_key,
            output_dir=output_dir,
            text_file=text_file,
            source_paths=source_paths,
            source_names=source_names,
            title="",
        )
        if manifest_id.casefold() in groups_by_id:
            raise PipelineError(f"Exedra group id 重复: {manifest_id}")
        groups_by_id[manifest_id.casefold()] = group
        group_source_paths[manifest_id.casefold()] = source_paths
        groups.append(group)

    source_records_by_group: dict[str, list[Mapping[str, Any]]] = {
        key: [] for key in groups_by_id
    }
    seen_source_paths: set[str] = set()
    seen_output_json: set[str] = set()
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, dict):
            raise PipelineError(f"Exedra manifest sources[{index}] 不是对象")
        source_path = str(raw_source.get("sourcePath") or "").strip()
        group_id = str(raw_source.get("groupId") or "").strip()
        if not source_path or not group_id:
            raise PipelineError(
                f"Exedra manifest sources[{index}] 缺少 sourcePath/groupId"
            )
        source_key = source_path.casefold()
        if source_key in seen_source_paths:
            raise PipelineError(f"Exedra 来源 JSON 重复登记: {source_path}")
        seen_source_paths.add(source_key)

        group_key = group_id.casefold()
        group = groups_by_id.get(group_key)
        if group is None:
            raise PipelineError(
                f"Exedra 来源指向不存在的逻辑组: {source_path}: {group_id}"
            )
        if source_path not in group_source_paths[group_key]:
            raise PipelineError(
                f"Exedra 来源未出现在对应 group.sources: {source_path}"
            )

        output_json = _manifest_relative_path(
            raw_source.get("outputJson"),
            field_name=f"sources[{index}].outputJson",
        )
        if output_json.parent != group.output_dir:
            raise PipelineError(
                f"Exedra JSON 未复制到逻辑组文件夹: {source_path}: "
                f"{output_json.as_posix()}"
            )
        if output_json.name != PurePosixPath(source_path).name:
            raise PipelineError(
                f"Exedra JSON 复制时改名: {source_path}: {output_json.name}"
            )
        output_key = output_json.as_posix().casefold()
        if output_key in seen_output_json:
            raise PipelineError(f"Exedra 输出 JSON 冲突: {output_json.as_posix()}")
        seen_output_json.add(output_key)
        output_path = base_dir / output_json
        output_record = tree_files.get(output_key)
        if (
            output_record is None
            or output_record[1] != output_json.as_posix()
            or output_record[0] != output_path
        ):
            raise PipelineError(f"Exedra 输出 JSON 不存在: {output_path}")

        expected_sha = str(raw_source.get("sha256") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise PipelineError(f"Exedra 来源缺少有效 sha256: {source_path}")
        if _sha256_file(output_path) != expected_sha:
            raise PipelineError(
                f"Exedra JSON 与 manifest 哈希不一致: {output_path}"
            )
        source_records_by_group[group_key].append(raw_source)

    for group_key, group in groups_by_id.items():
        records = source_records_by_group[group_key]
        record_sources = tuple(str(record["sourcePath"]) for record in records)
        if record_sources != group.source_paths:
            raise PipelineError(
                f"Exedra 顶层 sources 顺序/归属与 group 不一致: "
                f"{group.manifest_id}"
            )

    actual_output_json = {
        relative.casefold()
        for path, relative in tree_files.values()
        if path.suffix.casefold() == ".json" and path != manifest_path
    }
    if actual_output_json != seen_output_json:
        missing = sorted(seen_output_json - actual_output_json)
        extra = sorted(actual_output_json - seen_output_json)
        raise PipelineError(
            "Exedra JSON 所有权不完整: "
            f"缺失 {len(missing)}，未登记 {len(extra)}；"
            f"示例 {((missing or extra)[:1] or ['无'])[0]}"
        )

    titled_groups: list[OrganizedExedraGroup] = []
    for group in groups:
        records = source_records_by_group[group.manifest_id.casefold()]
        book_titles = [
            str(record.get("bookTitle") or "").strip()
            for record in records
            if str(record.get("bookTitle") or "").strip()
        ]
        unique_titles = list(dict.fromkeys(book_titles))
        title = (
            unique_titles[0]
            if len(unique_titles) == 1
            else _humanize_exedra_title(group.group_key)
        )
        titled_groups.append(
            OrganizedExedraGroup(
                manifest_id=group.manifest_id,
                raw_category=group.raw_category,
                category=group.category,
                group_key=group.group_key,
                output_dir=group.output_dir,
                text_file=group.text_file,
                source_paths=group.source_paths,
                source_names=group.source_names,
                title=title,
            )
        )

    stats["exedra_manifest_groups"] = len(titled_groups)
    stats["exedra_manifest_json_sources"] = len(raw_sources)
    stats["exedra_manifest_json_verified"] = len(seen_output_json)
    return titled_groups


def _find_exedra_cn_sources(
    cn_dir: Path,
    groups: Sequence[OrganizedExedraGroup],
) -> dict[str, Path]:
    if not cn_dir.exists():
        return {}
    cn_dir = _absolute_lexical(cn_dir)
    actual_files: dict[str, Path] = {}
    for path, relative, is_directory in _plain_tree_entries(cn_dir):
        if is_directory or path.suffix.casefold() != ".txt":
            continue
        relative_key = relative.as_posix().casefold()
        if relative_key in actual_files:
            raise PipelineError(
                f"Exedra 中文文件存在大小写冲突: "
                f"{actual_files[relative_key]}, {path}"
            )
        actual_files[relative_key] = path

    matched: dict[str, Path] = {}
    consumed: set[str] = set()
    for group in groups:
        base = Path(group.raw_category, group.group_key)
        candidates = (
            base / f"{group.group_key}_cn.txt",
            base / f"{group.group_key}.txt",
        )
        matches = [
            actual_files[candidate.as_posix().casefold()]
            for candidate in candidates
            if candidate.as_posix().casefold() in actual_files
        ]
        if len(matches) > 1:
            raise PipelineError(
                f"Exedra 中文组同时存在两种文件名，无法确定唯一来源: "
                f"{group.raw_category}/{group.group_key}"
            )
        if matches:
            matched[group.manifest_id] = matches[0]
            consumed.add(matches[0].relative_to(cn_dir).as_posix().casefold())

    orphan_keys = sorted(set(actual_files) - consumed)
    if orphan_keys:
        raise PipelineError(
            f"有 {len(orphan_keys)} 个 Exedra 中文 TXT 未匹配日文逻辑组: "
            f"{actual_files[orphan_keys[0]]}"
        )
    return matched


def scan_exedra_sources(
    *,
    jp_dir: Path,
    cn_dir: Path,
    staging_data_dir: Path,
    story_map: MutableMapping[str, dict[str, Any]],
    stats: Counter[str],
    source_audit: SourceAudit,
) -> None:
    """Publish one story per organizer group without changing turn alignment."""

    groups = load_exedra_manifest(jp_dir, stats=stats)
    cn_sources = _find_exedra_cn_sources(cn_dir, groups)
    unnamed_characters = sorted(
        group.group_key
        for group in groups
        if group.category == "exedra_character"
        and group.group_key not in EXEDRA_CHARACTER_DISPLAY_NAMES
    )
    if unnamed_characters:
        raise PipelineError(
            "Exedra 角色缺少中文目录名映射: "
            + ", ".join(unnamed_characters)
        )

    for group in groups:
        if not EXEDRA_ROUTE_GROUP_RE.fullmatch(group.group_key):
            raise PipelineError(
                "Exedra 逻辑组名无法由阅读器路由无损反推，拒绝发布: "
                f"{group.manifest_id}"
            )
        jp_path = jp_dir / group.text_file
        jp_alignment = _exedra_alignment_sections(jp_path)
        jp_section_sources = [
            section.source_name for section in jp_alignment
        ]
        jp_turn_counts = [
            section.reader_block_count for section in jp_alignment
        ]
        if tuple(jp_section_sources) != group.source_names:
            raise PipelineError(
                f"Exedra JP Section 来源与 manifest 不一致: {group.manifest_id}"
            )

        relative_identity = (
            f"{group.raw_category}/{group.group_key}/"
            f"{group.group_key}_jp.txt"
        )
        story_id = safe_exedra_story_id(
            group.category,
            relative_identity,
            group.group_key,
        )
        if story_id in story_map:
            raise PipelineError(f"Exedra story id 冲突: {story_id}")
        story = _new_story_record(
            story_id=story_id,
            raw_id=group.group_key,
            file_stem=group.group_key,
            category=group.category,
            folder=(
                EXEDRA_CHARACTER_DISPLAY_NAMES[group.group_key]
                if group.category == "exedra_character"
                else group.group_key
            ),
            title=group.title,
        )
        story.update(
            {
                "game": "exedra",
                "source_format": "organized_txt",
                "source_identity": group.manifest_id,
                "source_count": len(group.source_paths),
                "turns_jp": sum(jp_turn_counts),
            }
        )
        destination_rel = Path(group.category, group.group_key)

        source_audit.expect(jp_path)
        jp_destination_name = f"{group.group_key}_jp.txt"
        jp_destination = (
            staging_data_dir / destination_rel / jp_destination_name
        )
        _copy_to_stage(jp_path, jp_destination)
        jp_web_path = (
            f"/data/{sanitize_path(destination_rel)}/{jp_destination_name}"
        )
        _set_language_source(
            story,
            lang_key="jp",
            web_path=jp_web_path,
            source_filename=jp_path.name,
            sections=extract_sections(jp_path),
        )
        source_audit.claim(
            jp_path,
            story_id=story_id,
            lang_key="jp",
            web_path=jp_web_path,
        )
        stats["exedra_jp_groups"] += 1

        cn_path = cn_sources.get(group.manifest_id)
        if cn_path is not None:
            cn_alignment = _exedra_alignment_sections(cn_path)
            cn_section_sources = [
                section.source_name for section in cn_alignment
            ]
            cn_turn_counts = [
                section.reader_block_count for section in cn_alignment
            ]
            if cn_section_sources != jp_section_sources:
                raise PipelineError(
                    f"Exedra 中日 Section 来源/顺序不同，拒绝发布: "
                    f"{group.manifest_id}"
                )
            if cn_turn_counts != jp_turn_counts:
                mismatches = [
                    (
                        index + 1,
                        jp_turn_counts[index],
                        cn_turn_counts[index],
                    )
                    for index in range(len(jp_turn_counts))
                    if jp_turn_counts[index] != cn_turn_counts[index]
                ]
                section, jp_count, cn_count = mismatches[0]
                raise PipelineError(
                    "Exedra 中日说话轮次不一致，拒绝用物理行或推测算法重排: "
                    f"{group.manifest_id} Section {section}: "
                    f"JP {jp_count}, CN {cn_count}"
                )
            _validate_exedra_cn_import_report(
                group=group,
                jp_path=jp_path,
                cn_path=cn_path,
                jp_sections=jp_alignment,
                cn_sections=cn_alignment,
            )
            source_audit.expect(cn_path)
            cn_destination_name = f"{group.group_key}_cn.txt"
            cn_destination = (
                staging_data_dir / destination_rel / cn_destination_name
            )
            _copy_to_stage(cn_path, cn_destination)
            cn_web_path = (
                f"/data/{sanitize_path(destination_rel)}/{cn_destination_name}"
            )
            _set_language_source(
                story,
                lang_key="cn",
                web_path=cn_web_path,
                source_filename=cn_path.name,
                sections=extract_sections(cn_path),
            )
            source_audit.claim(
                cn_path,
                story_id=story_id,
                lang_key="cn",
                web_path=cn_web_path,
            )
            story["turns_cn"] = sum(cn_turn_counts)
            stats["exedra_cn_groups"] += 1

        story_map[story_id] = story

    stats["exedra_untranslated_groups"] = len(groups) - len(cn_sources)


def custom_sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    id_val = str(item.get("file_stem") or item.get("raw_id") or item["id"])
    match = re.match(r"^(\d+)", id_val)
    number = int(match.group(1)) if match else 0
    if id_val.startswith("51701"):
        number += 100000
    return (str(item.get("category", "")), number, id_val)


def _natsorted_stories(stories: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    values = list(stories)
    if natsort is not None:
        return natsort.natsorted(values, key=custom_sort_key)
    return sorted(values, key=custom_sort_key)


def finalize_story_list(
    story_map: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    final_list: list[dict[str, Any]] = []
    for value in story_map.values():
        entry = {
            "id": value["id"],
            "raw_id": value.get("raw_id", value["id"]),
            "file_stem": value.get("file_stem", value["id"]),
            "category": value["category"],
            "folder": value["folder"],
            "percent": 100 if value.get("has_cn") else 0,
            "has_cn": bool(value.get("has_cn")),
            "has_jp": bool(value.get("has_jp")),
            "path_cn": value.get("cn_path") or value.get("path_cn") or "",
            "path_jp": value.get("jp_path") or value.get("path_jp") or "",
            "title": value.get("title", ""),
            "sections": list(value.get("sections", [])),
            "filename_cn": value.get("filename_cn", ""),
            "filename_jp": value.get("filename_jp", ""),
        }
        for extra_key in (
            "game",
            "legacy_ids",
            "source_format",
            "source_path",
            "source_identity",
            "source_count",
            "turns_jp",
            "turns_cn",
        ):
            if extra_key in value:
                entry[extra_key] = value[extra_key]
        final_list.append(entry)
    return _natsorted_stories(final_list)


def _resolve_public_source(public_dir: Path, web_path: str) -> Path:
    if not web_path.startswith("/"):
        raise PipelineError(f"索引路径必须以 / 开头: {web_path}")
    public_dir = _absolute_lexical(public_dir)
    if _is_link_like(public_dir):
        raise PipelineError(f"public 根目录是链接或联接点: {public_dir}")
    candidate_path = public_dir / web_path.lstrip("/")
    if candidate_path.exists() and _is_link_like(candidate_path):
        raise PipelineError(f"索引来源是链接或联接点: {web_path}")
    candidate = candidate_path.resolve()
    public_resolved = public_dir.resolve()
    try:
        candidate.relative_to(public_resolved)
    except ValueError as exc:
        raise PipelineError(f"索引路径越界: {web_path}") from exc
    return candidate


def validate_catalog(
    stories: Sequence[Mapping[str, Any]],
    public_dir: Path,
    *,
    source_audit: SourceAudit | None = None,
    require_magireco_legacy_aliases: bool = False,
) -> dict[str, int]:
    if not isinstance(stories, list) or not stories:
        raise PipelineError("story_index 为空或不是数组")

    route_owners: dict[str, str] = {}
    for index, story in enumerate(stories):
        story_id = str(story.get("id") or "")
        if not STORY_ROUTE_ID_RE.fullmatch(story_id):
            raise PipelineError(f"story_index[{index}] 的 id 无效")
        folded_id = story_id.casefold()
        previous = route_owners.get(folded_id)
        if previous is not None:
            raise PipelineError(f"重复 story id: {previous}, {story_id}")
        route_owners[folded_id] = story_id

    legacy_alias_count = 0
    for story in stories:
        story_id = str(story["id"])
        legacy_ids = story.get("legacy_ids")
        if legacy_ids is None:
            continue
        if (
            story.get("game") != "magireco"
            or not isinstance(legacy_ids, list)
            or not legacy_ids
            or len(legacy_ids) > MAX_LEGACY_IDS_PER_STORY
        ):
            raise PipelineError(f"{story_id}: legacy_ids 无效")
        for legacy_id in legacy_ids:
            if (
                not isinstance(legacy_id, str)
                or not STORY_ROUTE_ID_RE.fullmatch(legacy_id)
            ):
                raise PipelineError(f"{story_id}: legacy_ids 包含无效编号")
            folded_id = legacy_id.casefold()
            previous = route_owners.get(folded_id)
            if previous is not None:
                raise PipelineError(
                    f"旧路由编号与现有路由冲突: {legacy_id}: {previous}"
                )
            route_owners[folded_id] = story_id
            legacy_alias_count += 1
            if legacy_alias_count > MAX_LEGACY_ROUTE_ALIASES:
                raise PipelineError("旧路由编号总数超过安全限制")

    if require_magireco_legacy_aliases:
        stories_by_identity: dict[str, list[Mapping[str, Any]]] = {}
        for story in stories:
            if story.get("game") != "magireco":
                continue
            source_identity = str(story.get("source_identity") or "")
            stories_by_identity.setdefault(
                source_identity.casefold(),
                [],
            ).append(story)
        for legacy_id, expected_identity in (
            MAGIRECO_LEGACY_ROUTE_IDENTITIES.items()
        ):
            matches = stories_by_identity.get(
                expected_identity.casefold(),
                [],
            )
            if len(matches) != 1:
                raise PipelineError(
                    "已生成目录缺少唯一安全旧路由目标: "
                    f"{legacy_id}: {expected_identity}"
                )
            target_id = str(matches[0]["id"])
            if route_owners.get(legacy_id.casefold()) != target_id:
                raise PipelineError(
                    "已生成目录未保留安全旧路由: "
                    f"{legacy_id} -> {target_id}"
                )

    source_owners: dict[str, tuple[str, str]] = {}
    counts: Counter[str] = Counter()
    for index, story in enumerate(stories):
        story_id = str(story.get("id") or "")
        counts[str(story.get("category") or "Unclassified")] += 1

        if story.get("game") == "exedra":
            category = str(story.get("category") or "")
            group_key = str(story.get("raw_id") or "")
            if not EXEDRA_ROUTE_GROUP_RE.fullmatch(group_key):
                raise PipelineError(
                    f"{story_id}: Exedra 组名不能由阅读器路由无损反推"
                )
            raw_category = EXEDRA_CATEGORY_MAP_REVERSE.get(category)
            if raw_category is None:
                raise PipelineError(
                    f"{story_id}: 未知 Exedra 分类，无法验证阅读器路由"
                )
            relative_identity = (
                f"{raw_category}/{group_key}/"
                f"{group_key}_jp.txt"
            )
            expected_id = safe_exedra_story_id(
                category,
                relative_identity,
                group_key,
            )
            if story_id != expected_id:
                raise PipelineError(
                    f"{story_id}: Exedra 路由编号与来源身份不一致"
                )
            expected_jp = (
                f"/data/{category}/{group_key}/{group_key}_jp.txt"
            )
            expected_cn = (
                f"/data/{category}/{group_key}/{group_key}_cn.txt"
            )
            if story.get("path_jp") != expected_jp or (
                bool(story.get("has_cn"))
                and story.get("path_cn") != expected_cn
            ):
                raise PipelineError(
                    f"{story_id}: Exedra 路由反推路径与清单路径不一致"
                )

        for lang in ("cn", "jp"):
            web_path = str(story.get(f"path_{lang}") or "")
            has_lang = bool(story.get(f"has_{lang}"))
            if has_lang != bool(web_path):
                raise PipelineError(
                    f"{story_id}: has_{lang} 与 path_{lang} 不一致"
                )
            if not web_path:
                continue
            source_path = _resolve_public_source(public_dir, web_path)
            if not source_path.is_file():
                raise PipelineError(f"{story_id}: 文件不存在: {source_path}")
            try:
                source_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise PipelineError(f"{story_id}: 非有效 UTF-8: {source_path}") from exc

            owner_key = web_path.casefold()
            previous_owner = source_owners.get(owner_key)
            if previous_owner is not None:
                raise PipelineError(
                    f"来源路径被多个故事复用: {web_path}: "
                    f"{previous_owner[0]}/{previous_owner[1]}, "
                    f"{story_id}/{lang}"
                )
            source_owners[owner_key] = (story_id, lang)

            if source_path.suffix.lower() == ".json":
                rows, _ = load_exedra_dialogue_rows(source_path)
                if not rows:
                    raise PipelineError(f"{story_id}: Exedra JSON 没有可读文本")

    counts["stories"] = len(stories)
    counts["legacy_story_ids"] = legacy_alias_count
    counts["source_files"] = len(source_owners)
    story_ids_path = public_dir / "data" / STORY_IDS_FILENAME
    if (
        not story_ids_path.is_file()
        or _is_link_like(story_ids_path)
    ):
        raise PipelineError(f"缺少精确剧情编号清单: {story_ids_path}")
    try:
        with story_ids_path.open("r", encoding="utf-8-sig") as handle:
            story_ids = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(
            f"剧情编号清单不是有效 UTF-8 JSON: {story_ids_path}"
        ) from exc
    expected_story_ids = [str(story["id"]) for story in stories]
    if story_ids != expected_story_ids:
        raise PipelineError("剧情编号清单与 story_index 的精确顺序或内容不一致")
    counts["story_ids"] = len(story_ids)
    if source_audit is not None:
        counts.update(source_audit.validate_manifest(stories))
    return dict(counts)


def build_story_catalog(
    *,
    staging_public_dir: Path,
    jp_dir: Path,
    cn_dir: Path,
    exedra_jp_dir: Path | None,
    exedra_cn_dir: Path | None,
    titles_path: Path,
    include_magireco: bool = True,
    require_magireco_legacy_aliases: bool = False,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    staging_data_dir = staging_public_dir / "data"
    staging_data_dir.mkdir(parents=True, exist_ok=False)
    titles = load_titles(titles_path)
    story_map: dict[str, dict[str, Any]] = {}
    stats: Counter[str] = Counter()
    source_audit = SourceAudit()
    stats["titles"] = len(titles)

    if include_magireco:
        scan_magireco_sources(
            jp_dir=jp_dir,
            cn_dir=cn_dir,
            staging_data_dir=staging_data_dir,
            story_map=story_map,
            titles=titles,
            stats=stats,
            source_audit=source_audit,
            require_legacy_route_aliases=require_magireco_legacy_aliases,
        )

    if exedra_jp_dir is not None:
        scan_exedra_sources(
            jp_dir=exedra_jp_dir,
            cn_dir=exedra_cn_dir or Path("__missing_exedra_cn__"),
            staging_data_dir=staging_data_dir,
            story_map=story_map,
            stats=stats,
            source_audit=source_audit,
        )

    stories = finalize_story_list(story_map)
    story_ids_path = staging_data_dir / STORY_IDS_FILENAME
    with story_ids_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            [str(story["id"]) for story in stories],
            handle,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        handle.write("\n")
    index_path = staging_public_dir / "story_index.json"
    with index_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(stories, handle, ensure_ascii=False, indent=2)
    validation = validate_catalog(
        stories,
        staging_public_dir,
        source_audit=source_audit,
        require_magireco_legacy_aliases=(
            require_magireco_legacy_aliases
        ),
    )
    for key in (
        "input_source_files",
        "manifest_source_files",
        "orphan_sources",
        "ownership_collisions",
    ):
        stats[key] = validation[key]
    stats["stories"] = len(stories)
    return stories, stats


def _assert_direct_child(path: Path, parent: Path) -> None:
    _assert_no_link_ancestors(parent, label="父目录")
    if path.exists() and _is_link_like(path):
        raise PipelineError(f"目标是链接或联接点，拒绝操作: {path}")
    resolved_path = path.resolve()
    resolved_parent = parent.resolve()
    if resolved_path.parent != resolved_parent:
        raise PipelineError(f"拒绝操作非预期路径: {resolved_path}")


def _assert_inside(path: Path, root: Path) -> None:
    _assert_no_link_ancestors(root, label="根目录")
    if path.exists() and _is_link_like(path):
        raise PipelineError(f"路径是链接或联接点，拒绝操作: {path}")
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise PipelineError(f"拒绝操作目录外路径: {resolved_path}")


def _file_tree_snapshot(
    root: Path,
) -> dict[str, tuple[str, int, str]]:
    """Return a case-insensitive, content-addressed inventory of regular files."""

    snapshot: dict[str, tuple[str, int, str]] = {}
    for path, relative_path, is_directory in _plain_tree_entries(root):
        if is_directory:
            continue
        relative = relative_path.as_posix()
        key = relative.casefold()
        if key in snapshot:
            raise PipelineError(f"文件树存在大小写冲突: {root}: {relative}")
        snapshot[key] = (relative, path.stat().st_size, _sha256_file(path))
    return snapshot


def _replace_with_retry(source: Path, destination: Path) -> None:
    """Retry short-lived Windows sharing violations without hiding failures."""

    delays = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8)
    last_error: PermissionError | None = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            os.replace(source, destination)
            return
        except PermissionError as error:
            last_error = error
    assert last_error is not None
    raise last_error


def _atomic_copy_verified(source: Path, destination: Path) -> None:
    """Copy through a same-directory temporary file, verify, then replace."""

    if not source.is_file() or _is_link_like(source):
        raise PipelineError(f"拒绝复制非普通文件: {source}")
    if _is_link_like(destination.parent):
        raise PipelineError(f"复制目标父目录是链接或联接点: {destination.parent}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / (
        f".{destination.name}.magi-reader-{uuid.uuid4().hex}.tmp"
    )
    _assert_inside(temporary, destination.parent)
    expected_hash = _sha256_file(source)
    try:
        shutil.copy2(source, temporary)
        if _sha256_file(temporary) != expected_hash:
            raise PipelineError(f"临时复制校验失败: {source}")
        _replace_with_retry(temporary, destination)
        if _sha256_file(destination) != expected_hash:
            raise PipelineError(f"原子替换后校验失败: {destination}")
    finally:
        if temporary.exists():
            temporary.unlink()


def _sync_file_tree(source_root: Path, target_root: Path) -> None:
    """Mirror regular files without renaming or deleting the target root."""

    source_snapshot = _file_tree_snapshot(source_root)
    if target_root.exists() and (
        not target_root.is_dir() or _is_link_like(target_root)
    ):
        raise PipelineError(f"目标 data 不是目录: {target_root}")
    target_root.mkdir(parents=True, exist_ok=True)
    target_snapshot = _file_tree_snapshot(target_root)

    for key, (relative, size, digest) in sorted(source_snapshot.items()):
        existing = target_snapshot.get(key)
        if existing is not None and existing[1:] == (size, digest):
            continue
        source = source_root.joinpath(*PurePosixPath(relative).parts)
        destination = target_root.joinpath(*PurePosixPath(relative).parts)
        _assert_inside(destination, target_root)
        _atomic_copy_verified(source, destination)

    # New files are already durable and verified before stale files are
    # removed. A complete rollback snapshot must exist before this function is
    # called on user-visible data.
    for key in sorted(set(target_snapshot) - set(source_snapshot)):
        relative = target_snapshot[key][0]
        stale = target_root.joinpath(*PurePosixPath(relative).parts)
        _assert_inside(stale, target_root)
        stale.unlink()

    target_entries = _plain_tree_entries(target_root)
    for directory, _, is_directory in sorted(
        target_entries,
        key=lambda item: len(item[0].parts),
        reverse=True,
    ):
        if not is_directory:
            continue
        _assert_inside(directory, target_root)
        try:
            directory.rmdir()
        except OSError:
            pass

    if _file_tree_snapshot(target_root) != source_snapshot:
        raise PipelineError(
            f"镜像同步后的文件树与 staging 不一致: {target_root}"
        )


def _clear_file_tree(root: Path) -> None:
    if not root.exists():
        return
    snapshot = _file_tree_snapshot(root)
    for relative, _, _ in snapshot.values():
        path = root.joinpath(*PurePosixPath(relative).parts)
        _assert_inside(path, root)
        path.unlink()
    entries = _plain_tree_entries(root)
    for directory, _, is_directory in sorted(
        entries,
        key=lambda item: len(item[0].parts),
        reverse=True,
    ):
        if not is_directory:
            continue
        _assert_inside(directory, root)
        try:
            directory.rmdir()
        except OSError:
            pass
    root.rmdir()


def _safe_copy_sync_replace(
    *,
    staged_data: Path,
    staged_index: Path,
    target_data: Path,
    target_index: Path,
    backup_root: Path,
    backup_data: Path,
    backup_index: Path,
) -> Path | None:
    """Windows fallback with a verified backup and byte-exact rollback."""

    had_data = target_data.exists()
    had_index = target_index.exists()
    if had_data and (not target_data.is_dir() or _is_link_like(target_data)):
        raise PipelineError(f"既有 data 不是目录: {target_data}")
    if had_index and (not target_index.is_file() or _is_link_like(target_index)):
        raise PipelineError(f"既有 story_index 不是普通文件: {target_index}")

    old_data_snapshot = (
        _file_tree_snapshot(target_data) if had_data else None
    )
    old_index_hash = _sha256_file(target_index) if had_index else None
    backup_root.mkdir(parents=True, exist_ok=False)

    try:
        if had_data:
            shutil.copytree(target_data, backup_data, copy_function=shutil.copy2)
            if _file_tree_snapshot(backup_data) != old_data_snapshot:
                raise PipelineError("旧 data 的回撤备份校验失败")
        if had_index:
            _atomic_copy_verified(target_index, backup_index)
            if _sha256_file(backup_index) != old_index_hash:
                raise PipelineError("旧 story_index 的回撤备份校验失败")
    except Exception:
        # No target bytes have changed at this point. Only the newly allocated,
        # direct-child partial backup is removed.
        _assert_direct_child(backup_root, backup_root.parent)
        shutil.rmtree(backup_root)
        raise

    try:
        _sync_file_tree(staged_data, target_data)
        _atomic_copy_verified(staged_index, target_index)
        if _file_tree_snapshot(target_data) != _file_tree_snapshot(staged_data):
            raise PipelineError("安装后的 data 与 staging 不一致")
        if _sha256_file(target_index) != _sha256_file(staged_index):
            raise PipelineError("安装后的 story_index 与 staging 不一致")
    except Exception as install_error:
        try:
            if had_data:
                _sync_file_tree(backup_data, target_data)
            else:
                _clear_file_tree(target_data)
            if had_index:
                _atomic_copy_verified(backup_index, target_index)
            elif target_index.exists():
                _assert_direct_child(target_index, target_index.parent)
                target_index.unlink()
            if had_data and _file_tree_snapshot(target_data) != old_data_snapshot:
                raise PipelineError("回滚后的 data 与原始快照不一致")
            if not had_data and target_data.exists():
                raise PipelineError("回滚后意外保留 data")
            if had_index and _sha256_file(target_index) != old_index_hash:
                raise PipelineError("回滚后的 story_index 与原始文件不一致")
            if not had_index and target_index.exists():
                raise PipelineError("回滚后意外保留 story_index")
        except Exception as rollback_error:
            raise PipelineError(
                "新数据安装失败且自动回滚未完成；完整备份保留在 "
                f"{backup_root}: install={install_error}; "
                f"rollback={rollback_error}"
            ) from rollback_error
        raise PipelineError(
            f"新数据安装失败，已恢复旧版本；备份保留在 {backup_root}: "
            f"{install_error}"
        ) from install_error

    if had_data or had_index:
        return backup_root
    try:
        backup_root.rmdir()
        backup_root.parent.rmdir()
    except OSError:
        pass
    return None


def safe_replace_generated(
    staging_public_dir: Path,
    target_public_dir: Path,
) -> Path | None:
    """Install a complete staged catalogue and retain a rollback snapshot."""

    staging_public_dir = _absolute_lexical(staging_public_dir)
    target_public_dir = _absolute_lexical(target_public_dir)
    _assert_no_link_ancestors(staging_public_dir, label="staging public")
    _assert_no_link_ancestors(target_public_dir, label="目标 public")
    staged_data = staging_public_dir / "data"
    staged_index = staging_public_dir / "story_index.json"
    if (
        not staged_data.is_dir()
        or _is_link_like(staged_data)
        or not staged_index.is_file()
        or _is_link_like(staged_index)
    ):
        raise PipelineError("staging 缺少 data 或 story_index.json")
    # Enumerate the complete staged tree before any backup or target mutation.
    _file_tree_snapshot(staged_data)

    target_public_dir.mkdir(parents=True, exist_ok=True)
    target_data = target_public_dir / "data"
    target_index = target_public_dir / "story_index.json"
    backup_container = (
        target_public_dir.parent / ".magi-reader-generation-backups"
    )
    _assert_no_link_ancestors(backup_container, label="回撤备份容器")
    if backup_container.exists() and (
        not backup_container.is_dir() or _is_link_like(backup_container)
    ):
        raise PipelineError(
            f"回撤备份容器不是普通目录: {backup_container}"
        )
    backup_root = backup_container / uuid.uuid4().hex
    backup_data = backup_root / "data"
    backup_index = backup_root / "story_index.json"
    _assert_direct_child(target_data, target_public_dir)
    _assert_direct_child(target_index, target_public_dir)
    _assert_direct_child(backup_root, backup_container)

    if os.name == "nt":
        return _safe_copy_sync_replace(
            staged_data=staged_data,
            staged_index=staged_index,
            target_data=target_data,
            target_index=target_index,
            backup_root=backup_root,
            backup_data=backup_data,
            backup_index=backup_index,
        )

    moved_old_data = False
    moved_old_index = False
    installed_new_data = False
    installed_new_index = False
    backup_root.mkdir(parents=True, exist_ok=False)
    try:
        if target_data.exists():
            _replace_with_retry(target_data, backup_data)
            moved_old_data = True
        if target_index.exists():
            _replace_with_retry(target_index, backup_index)
            moved_old_index = True
        _replace_with_retry(staged_data, target_data)
        installed_new_data = True
        _replace_with_retry(staged_index, target_index)
        installed_new_index = True
    except Exception:
        if installed_new_index and target_index.exists():
            target_index.unlink()
        if installed_new_data and target_data.exists():
            _assert_direct_child(target_data, target_public_dir)
            shutil.rmtree(target_data)
        if moved_old_index and backup_index.exists():
            _replace_with_retry(backup_index, target_index)
        if moved_old_data and backup_data.exists():
            _replace_with_retry(backup_data, target_data)
        try:
            backup_root.rmdir()
            backup_container.rmdir()
        except OSError:
            pass
        raise

    if moved_old_data or moved_old_index:
        return backup_root
    try:
        backup_root.rmdir()
        backup_container.rmdir()
    except OSError:
        pass
    return None


def _resolve_argument_path(value: str | None, default: Path | None) -> Path | None:
    if value is None:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = SCRIPT_DIR / path
    return _absolute_lexical(path)


def _print_stats(stats: Mapping[str, int], validation: Mapping[str, int]) -> None:
    print("=== 数据管线报告 ===")
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")
    print("=== 验证报告 ===")
    for key in sorted(validation):
        print(f"{key}: {validation[key]}")


def run_generation(args: argparse.Namespace) -> int:
    public_dir = _resolve_argument_path(args.public_dir, DEFAULT_PUBLIC_DIR)
    titles_path = _resolve_argument_path(args.titles, DEFAULT_TITLES_PATH)
    jp_dir = _resolve_argument_path(args.jp_dir, DEFAULT_DIR_JP)
    cn_dir = _resolve_argument_path(args.cn_dir, DEFAULT_DIR_CN)
    legacy_exedra_dir = getattr(args, "exedra_dir", None)
    explicit_exedra_jp = getattr(args, "exedra_jp_dir", None)
    if legacy_exedra_dir and explicit_exedra_jp:
        raise PipelineError("--exedra-dir 与 --exedra-jp-dir 不能同时使用")
    exedra_jp_dir = _resolve_argument_path(
        explicit_exedra_jp or legacy_exedra_dir,
        DEFAULT_EXEDRA_JP_DIR,
    )
    exedra_cn_dir = _resolve_argument_path(
        getattr(args, "exedra_cn_dir", None),
        DEFAULT_EXEDRA_CN_DIR,
    )
    include_exedra = not getattr(args, "skip_exedra", False)
    assert public_dir is not None
    assert titles_path is not None
    assert jp_dir is not None
    assert cn_dir is not None
    require_magireco_legacy_aliases = (
        not args.skip_magireco
        and jp_dir.resolve() == DEFAULT_DIR_JP.resolve()
        and cn_dir.resolve() == DEFAULT_DIR_CN.resolve()
    )

    if args.validate_only:
        index_path = public_dir / "story_index.json"
        if not index_path.is_file():
            raise PipelineError(f"story_index 不存在: {index_path}")
        with index_path.open("r", encoding="utf-8-sig") as handle:
            stories = json.load(handle)
        validation = validate_catalog(
            stories,
            public_dir,
            require_magireco_legacy_aliases=(
                require_magireco_legacy_aliases
            ),
        )
        _print_stats(Counter(), validation)
        return 0

    if include_exedra and (
        exedra_jp_dir is None or not exedra_jp_dir.is_dir()
    ):
        raise PipelineError(f"Exedra 日文整理目录不存在: {exedra_jp_dir}")

    if args.dry_run:
        with tempfile.TemporaryDirectory(prefix="magi-reader-dryrun-") as temp_dir:
            staging_public = Path(temp_dir) / "public"
            staging_public.mkdir()
            stories, stats = build_story_catalog(
                staging_public_dir=staging_public,
                jp_dir=jp_dir,
                cn_dir=cn_dir,
                exedra_jp_dir=exedra_jp_dir if include_exedra else None,
                exedra_cn_dir=exedra_cn_dir,
                titles_path=titles_path,
                include_magireco=not args.skip_magireco,
                require_magireco_legacy_aliases=(
                    require_magireco_legacy_aliases
                ),
            )
            validation = validate_catalog(
                stories,
                staging_public,
                require_magireco_legacy_aliases=(
                    require_magireco_legacy_aliases
                ),
            )
            _print_stats(stats, validation)
        print("DRY-RUN：验证通过，未替换 website/public 数据。")
        return 0

    public_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".magi-reader-stage-",
        dir=public_dir.parent,
    ) as temp_dir:
        staging_public = Path(temp_dir) / "public"
        staging_public.mkdir()
        stories, stats = build_story_catalog(
            staging_public_dir=staging_public,
            jp_dir=jp_dir,
            cn_dir=cn_dir,
            exedra_jp_dir=exedra_jp_dir if include_exedra else None,
            exedra_cn_dir=exedra_cn_dir,
            titles_path=titles_path,
            include_magireco=not args.skip_magireco,
            require_magireco_legacy_aliases=require_magireco_legacy_aliases,
        )
        validation = validate_catalog(
            stories,
            staging_public,
            require_magireco_legacy_aliases=(
                require_magireco_legacy_aliases
            ),
        )
        backup_path = safe_replace_generated(staging_public, public_dir)
        _print_stats(stats, validation)
        if backup_path is not None:
            print(f"旧版 data/story_index 回撤备份: {backup_path}")
    print("story_index 与 data 已从完整 staging 安全替换。")
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jp-dir", help="Magia Record 日文 Scenarios_full")
    parser.add_argument("--cn-dir", help="Magia Record 中文 Scenarios_full")
    parser.add_argument(
        "--exedra-jp-dir",
        help="整理后的 Magia Exedra 日文 Scenarios_full",
    )
    parser.add_argument(
        "--exedra-cn-dir",
        help="与日文逻辑组镜像的 Magia Exedra 中文 Scenarios_full",
    )
    parser.add_argument(
        "--exedra-dir",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--public-dir", help="目标 website/public")
    parser.add_argument("--titles", help="titles.json 路径")
    parser.add_argument(
        "--skip-magireco",
        action="store_true",
        help="只构建 Exedra（用于隔离验证/测试）",
    )
    parser.add_argument(
        "--skip-exedra",
        action="store_true",
        help="只构建 Magia Record（用于隔离验证/测试）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="在临时 staging 中完整构建和验证，但不替换目标",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只验证现有 story_index 及其路径映射",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.validate_only:
        parser.error("--dry-run 与 --validate-only 不能同时使用")
    try:
        return run_generation(args)
    except PipelineError as exc:
        parser.exit(2, f"错误: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
