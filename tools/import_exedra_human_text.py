#!/usr/bin/env python3
"""Import trusted Exedra Wiki and rounddora 0728 human subtitles.

Priority is enforced per Section:
1. an Exedra Wiki Chinese Episode with an exact Japanese Wiki/JSON anchor;
2. a rounddora 0728 ASS subtitle with the same exact Japanese anchor;
3. reject the whole group without leaving partial output.

Existing Chinese groups are never changed. Japanese JSON is always the
structural template; only Comment text cells are replaced. Canonical TXT is
generated from the validated JSON event sequence, never the other way around.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import itertools
import json
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import generate_story_index as pipeline  # noqa: E402
import import_exedra_official_tw as common  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
AUDIT_PATH = ROOT / "artifacts/exedra_human_text_import_report.json"
INVENTORY_PATH = (
    ROOT / "artifacts/source-archives/rounddora-text-0728.files.json"
)
EXPECTED_ARCHIVE_SHA256 = (
    "2f55e92bd8ceb310ba37c7a7b5dd94dffe5849d1266017021ff52366595b572c"
)
WIKI_API = "https://exedra.wiki/w/api.php"
USER_AGENT = "MagiReader-trusted-human-import/1.0"

CHARACTER_WIKI_SLUGS: dict[str, tuple[str, ...]] = {
    "character_arina": ("Alina_Gray",),
    "character_ashley": ("Ashley_Taylor",),
    "character_asuka": ("Asuka_Tatsuki",),
    "character_ayame": ("Ayame_Mikuri",),
    "character_corbeau": ("Corbeau",),
    "character_darc": ("Tart", "Darc"),
    "character_felicia": ("Felicia_Mitsuki",),
    "character_fuka": ("Fuka_Higurashi",),
    "character_hanna": ("Hanna_Sarasa",),
    "character_hazuki": ("Hazuki_Yusa",),
    "character_himika": ("Himika_Mao",),
    "character_homura": ("Homura_Akemi",),
    "character_iroha": ("Iroha_Tamaki",),
    "character_kaede": ("Kaede_Akino",),
    "character_kako": ("Kako_Natsume",),
    "character_kanae": ("Kanae_Yukino",),
    "character_karin": ("Karin_Misono",),
    "character_kirika": ("Kirika_Kure",),
    "character_koito": ("Koito_Asako",),
    "character_kokoro": ("Kokoro_Awane",),
    "character_konoha": ("Konoha_Shizumi",),
    "character_kush": ("Kush_Irnam", "Kush"),
    "character_kyoko": ("Kyoko_Sakura",),
    "character_liz": ("Liz_Hawkwood", "Riz_Hawkwood"),
    "character_mabayu": ("Mabayu_Aki",),
    "character_madoka": ("Madoka_Kaname",),
    "character_mami": ("Mami_Tomoe",),
    "character_mannenzakura": ("Rumor_of_the_Ten-Thousand-Year_Sakura",),
    "character_masara": ("Masara_Kagami",),
    "character_mayoi": ("Mayoi_Hachikuji",),
    "character_meiyui": ("Meiyui_Chun",),
    "character_melissa": ("Melissa_de_Vignolles", "Melissa"),
    "character_meru": ("Meru_Anna",),
    "character_mifuyu": ("Mifuyu_Azusa",),
    "character_mitama": ("Mitama_Yakumo",),
    "character_mito": ("Mito_Aino",),
    "character_momoko": ("Momoko_Togame",),
    "character_nagisa": ("Nagisa_Momoe",),
    "character_nanaka": ("Nanaka_Tokiwa",),
    "character_natsuki": ("Natsuki_Utsuho",),
    "character_nemu": ("Nemu_Hiiragi",),
    "character_oriko": ("Oriko_Mikuni",),
    "character_reira": ("Leila_Ibuki", "Reira_Ibuki"),
    "character_ren": ("Ren_Isuzu",),
    "character_rena": ("Rena_Minami",),
    "character_rika": ("Rika_Ayano",),
    "character_riko": ("Riko_Chiaki",),
    "character_sana": ("Sana_Futaba",),
    "character_sayaka": ("Sayaka_Miki",),
    "character_seika": ("Seika_Kumi",),
    "character_senpai": ("Madoka-senpai", "Madoka_Senpai"),
    "character_shinobu": ("Shinobu_Oshino",),
    "character_sumire": ("Sumire_Yomeiji",),
    "character_touka": ("Touka_Satomi",),
    "character_tsukasa": ("Tsukasa_Amane",),
    "character_tsukuyo": ("Tsukuyo_Amane",),
    "character_tsuruno": ("Tsuruno_Yui",),
    "character_ui": ("Ui_Tamaki",),
    "character_yachiyo": ("Yachiyo_Nanami",),
    "character_yotsugi": ("Yotsugi_Ononoki",),
    "character_yuma": ("Yuma_Chitose",),
}

ASS_CHARACTER_BASES: dict[str, str] = {
    "character_arina": "AlinaGrey",
    "character_ashley": "AshleyTaylor",
    "character_asuka": "TatsukiAsuka",
    "character_ayame": "MikuriAyame",
    "character_corbeau": "Corbeau",
    "character_darc": "Tart",
    "character_felicia": "MitsukiFelicia",
    "character_fuka": "HigureFuuka",
    "character_hanna": "SarasaHanna",
    "character_hazuki": "YusaHazuki",
    "character_himika": "MaoHimika",
    "character_homura": "AkemiHomura",
    "character_iroha": "TamakiIroha",
    "character_kaede": "AkinoKaede",
    "character_kako": "NatsumeKako",
    "character_kanae": "YukinoKanae",
    "character_karin": "MisonoKarin",
    "character_kirika": "KureKirika",
    "character_koito": "AsakoKoito",
    "character_kokoro": "AwaneKokoro",
    "character_konoha": "ShizumiKonoha",
    "character_kush": "IrinaKushu",
    "character_kyoko": "SakuraKyoko",
    "character_liz": "Liz",
    "character_mabayu": "AkiMabayu",
    "character_madoka": "KanameMadoka",
    "character_mami": "TomoeMami",
    "character_mannenzakura": "MannenSakura",
    "character_masara": "KagamiMasara",
    "character_mayoi": "HachikujiMayoi",
    "character_meiyui": "ChunMeiyu",
    "character_melissa": "Melissa",
    "character_meru": "AnnaMeru",
    "character_mifuyu": "AzusaMifuyu",
    "character_mitama": "YakumoMitama",
    "character_mito": "AinoMito",
    "character_momoko": "TogameMomoko",
    "character_nagisa": "MomoeNagisa",
    "character_nanaka": "TokiwaNanaka",
    "character_natsuki": "UtsuhoNatsuki",
    "character_nemu": "HiiragiNemu",
    "character_oriko": "MikuniOriko",
    "character_reira": "IbukiReira",
    "character_ren": "IsuzuRen",
    "character_rena": "MinamiRena",
    "character_rika": "AyanoRika",
    "character_riko": "ChiakiRiko",
    "character_sana": "FutabaSana",
    "character_sayaka": "MikiSayaka",
    "character_seika": "KumiSeika",
    "character_senpai": "MadokaSenpai",
    "character_shinobu": "OshinoShinobu",
    "character_sumire": "YoakeSumire",
    "character_touka": "SatomiTouka",
    "character_tsukasa": "AmaneTsukasa",
    "character_tsukuyo": "AmaneTsukuyo",
    "character_tsuruno": "UiTsuruno",
    "character_ui": "TamakiUi",
    "character_yachiyo": "NanamiYachiyo",
    "character_yotsugi": "OnonokiYotsugi",
    "character_yuma": "ChitoseYuma",
}


@dataclass(frozen=True)
class HumanEpisode:
    texts: tuple[str, ...]
    speaker_keys: tuple[tuple[str, ...], ...]
    source_type: str
    source_name: str
    source_url: str
    source_sha256: str
    anchor_keys: tuple[str, ...] = ()
    alignment: dict[str, Any] | None = None


@dataclass(frozen=True)
class ParsedWikiEpisode:
    texts: tuple[str, ...]
    speaker_keys: tuple[tuple[str, ...], ...]
    anchor_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentChunk:
    wiki_start: int
    wiki_count: int
    target_start: int
    target_count: int


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def clean_wiki_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"''+", "", value)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    return html.unescape(value).strip()


def parse_wiki_entries(raw: str) -> dict[int, ParsedWikiEpisode]:
    episodes: dict[int, list[str]] = {}
    speakers: dict[int, list[tuple[str, ...]]] = {}
    anchors: dict[int, list[str]] = {}
    current: int | None = None
    pending_narration: list[str] = []
    current_markers: list[str] = []

    def current_anchor() -> str:
        return "|".join(current_markers)

    def flush_narration() -> None:
        nonlocal pending_narration
        if current is not None and pending_narration:
            text = "\\n".join(part for part in pending_narration if part).strip()
            if text:
                episodes[current].append(text)
                speakers[current].append(())
                anchors[current].append(current_anchor())
        pending_narration = []

    dialogue_re = re.compile(
        r"^\s*(?:\{\{Audio\|[^}]+\}\}\s*)?"
        r"\{\{Color Dialogue\|[^}]+\}\}"
        r"(?:\s*[＆&]\s*\{\{Color Dialogue\|[^}]+\}\})*"
        r"\s*[:：]\s*(.*)$",
        re.I,
    )
    for raw_line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        heading = re.fullmatch(
            r"===\s*(?:Episode\s+(\d+)|第\s*(\d+)\s*[话話])\s*===",
            raw_line.strip(),
            flags=re.I,
        )
        if heading:
            flush_narration()
            current = int(heading.group(1) or heading.group(2))
            episodes[current] = []
            speakers[current] = []
            anchors[current] = []
            current_markers = []
            continue
        if current is None:
            continue
        for kind, value in re.findall(
            r"\{\{(BackgroundImage|BGMAudio|Video)\|([^{}]+)\}\}",
            raw_line,
            flags=re.I,
        ):
            current_markers.append(
                f"{kind.casefold()}:{normalize_japanese_anchor(value)}"
            )
        dialogue = dialogue_re.match(raw_line)
        if dialogue:
            flush_narration()
            text = clean_wiki_text(dialogue.group(1))
            if text:
                episodes[current].append(text)
                identities: list[str] = []
                for template in re.findall(
                    r"\{\{Color Dialogue\|([^{}]+)\}\}",
                    raw_line,
                    flags=re.I,
                ):
                    parts = [part.strip() for part in template.split("|")]
                    identity = parts[-1] if len(parts) > 1 else parts[0]
                    if identity:
                        identities.append(
                            re.sub(r"\s+", "_", identity.casefold())
                        )
                speakers[current].append(tuple(identities))
                anchors[current].append(current_anchor())
            continue
        stripped = raw_line.strip()
        if stripped.startswith("'''") and stripped.endswith("'''"):
            pending_narration.append(clean_wiki_text(stripped))
            continue
        if not stripped:
            flush_narration()
        elif pending_narration:
            flush_narration()
    flush_narration()
    return {
        key: ParsedWikiEpisode(
            texts=tuple(value),
            speaker_keys=tuple(speakers[key]),
            anchor_keys=tuple(anchors[key]),
        )
        for key, value in episodes.items()
    }


def parse_wiki_wikitext(raw: str) -> dict[int, tuple[str, ...]]:
    """Compatibility wrapper used by the audit tests and older callers."""
    return {
        episode: parsed.texts
        for episode, parsed in parse_wiki_entries(raw).items()
    }


def _fetch_wiki_page(
    slug: str,
    language: str,
) -> tuple[dict[int, ParsedWikiEpisode], str, str]:
    title = f":{slug}/Story/{language}"
    query = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext|revid",
            "redirects": "1",
            "format": "json",
            "formatversion": "2",
            "origin": "*",
        }
    )
    url = f"{WIKI_API}?{query}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise RuntimeError("Wiki 响应超过 8 MiB")
    data = json.loads(payload.decode("utf-8"))
    parsed = data.get("parse") if isinstance(data, dict) else None
    wikitext = parsed.get("wikitext") if isinstance(parsed, dict) else None
    if not isinstance(wikitext, str):
        code = (
            data.get("error", {}).get("code", "missing")
            if isinstance(data, dict)
            else "invalid"
        )
        raise RuntimeError(code)
    source_url = (
        "https://exedra.wiki/wiki/"
        + urllib.parse.quote(title.replace(" ", "_"), safe="/:_-")
    )
    return (
        parse_wiki_entries(wikitext),
        source_url,
        digest_bytes(wikitext.encode("utf-8")),
    )


def fetch_wiki_group(
    item: tuple[str, tuple[str, ...]],
) -> tuple[
    str,
    dict[int, HumanEpisode],
    dict[int, ParsedWikiEpisode],
    str,
    str,
    list[str],
]:
    group_key, slugs = item
    errors: list[str] = []
    japanese: dict[int, ParsedWikiEpisode] = {}
    japanese_url = ""
    japanese_sha = ""
    for slug in slugs:
        slug_japanese: dict[int, ParsedWikiEpisode] = {}
        slug_japanese_url = ""
        slug_japanese_sha = ""
        try:
            (
                slug_japanese,
                slug_japanese_url,
                slug_japanese_sha,
            ) = _fetch_wiki_page(slug, "Japanese")
            if slug_japanese and not japanese:
                japanese = slug_japanese
                japanese_url = slug_japanese_url
                japanese_sha = slug_japanese_sha
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            RuntimeError,
            urllib.error.URLError,
        ) as exc:
            errors.append(
                f":{slug}/Story/Japanese:"
                f"{type(exc).__name__}:{str(exc)[:160]}"
            )
        try:
            parsed_chinese, source_url, raw_sha = _fetch_wiki_page(
                slug,
                "Chinese",
            )
            episodes = {
                number: HumanEpisode(
                    texts=parsed_episode.texts,
                    speaker_keys=parsed_episode.speaker_keys,
                    source_type="exedra_wiki_human",
                    source_name=f":{slug}/Story/Chinese",
                    source_url=source_url,
                    source_sha256=raw_sha,
                    anchor_keys=parsed_episode.anchor_keys,
                )
                for number, parsed_episode in parsed_chinese.items()
            }
            if episodes and slug_japanese:
                return (
                    group_key,
                    episodes,
                    slug_japanese,
                    slug_japanese_url,
                    slug_japanese_sha,
                    errors,
                )
            if episodes:
                errors.append(
                    f":{slug}/Story/Chinese:"
                    "same-slug-japanese-anchor-missing"
                )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            RuntimeError,
            urllib.error.URLError,
        ) as exc:
            errors.append(
                f":{slug}/Story/Chinese:"
                f"{type(exc).__name__}:{str(exc)[:160]}"
            )
    return (
        group_key,
        {},
        japanese,
        japanese_url,
        japanese_sha,
        errors,
    )


def ass_episode_path(
    ass_files: dict[str, Path],
    group_key: str,
    episode: int,
) -> Path | None:
    if group_key == "character_tsuruno":
        base = "UiTsuruno" if episode in {0, 1, 2, 3, 4, 7} else "YuiTsuruno"
    else:
        base = ASS_CHARACTER_BASES[group_key]
    return ass_files.get(f"{base}{episode}.ass")


def parse_ass(path: Path) -> tuple[str, ...]:
    texts: list[str] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        1,
    ):
        if not raw.startswith("Dialogue:"):
            continue
        fields = raw[len("Dialogue:") :].split(",", 9)
        if len(fields) != 10:
            raise RuntimeError(f"ASS Dialogue 字段数无效：{path}:{line_number}")
        text = fields[9]
        text = re.sub(r"\{[^{}]*\}", "", text)
        text = text.replace("\\N", "\\n").replace("\\n", "\\n")
        text = text.replace("\\h", " ").strip()
        if not text:
            continue
        texts.append(text)
    if not texts:
        raise RuntimeError(f"ASS 不含 Dialogue：{path}")
    return tuple(texts)


def inventory_ass(ass_root: Path) -> tuple[dict[str, Path], dict[str, Any]]:
    root = ass_root.resolve(strict=True)
    files: dict[str, Path] = {}
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.ass")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.resolve().relative_to(root).as_posix()
        if path.name in files:
            raise RuntimeError(f"ASS basename 重复：{path.name}")
        raw = path.read_bytes()
        try:
            decoded = raw.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"ASS 不是 UTF-8：{path}") from exc
        files[path.name] = path
        records.append(
            {
                "path": relative,
                "name": path.name,
                "bytes": len(raw),
                "sha256": digest_bytes(raw),
                "encoding": encoding,
                "lineCount": len(decoded.splitlines()),
                "dialogueCount": sum(
                    line.startswith("Dialogue:") for line in decoded.splitlines()
                ),
            }
        )
    if len(files) != 640:
        raise RuntimeError(f"0728 ASS 应为 640 个，实际 {len(files)}")
    return files, {
        "schemaVersion": 1,
        "archiveSha256": EXPECTED_ARCHIVE_SHA256,
        "fileCount": len(files),
        "totalBytes": sum(item["bytes"] for item in records),
        "files": records,
    }


def normalize_japanese_anchor(value: str) -> str:
    """Normalize only presentation details, never Japanese text semantics."""
    value = html.unescape(value).replace("\\n", "\n")
    value = re.sub(
        r"<r=([\"']?)([^>\"']+)\1>(.*?)</r>",
        lambda match: f"{match.group(3)}{match.group(2)}",
        value,
        flags=re.I | re.S,
    )
    value = re.sub(r"<[^>]+>", "", value)
    value = unicodedata.normalize("NFKC", value)
    return "".join(character for character in value if not character.isspace())


def _exact_chunk_alignment(
    wiki_texts: tuple[str, ...],
    target_texts: tuple[str, ...],
    *,
    max_chunk: int = 4,
) -> tuple[AlignmentChunk, ...]:
    """Return the unique least-regrouped exact sequential alignment."""
    wiki_normalized = tuple(normalize_japanese_anchor(text) for text in wiki_texts)
    target_normalized = tuple(
        normalize_japanese_anchor(text) for text in target_texts
    )
    if not all(wiki_normalized) or not all(target_normalized):
        raise RuntimeError("日文 Wiki/JSON 锚点含空文本")

    memo: dict[
        tuple[int, int],
        tuple[int, tuple[tuple[AlignmentChunk, ...], ...]] | None,
    ] = {}

    def solve(
        wiki_index: int,
        target_index: int,
    ) -> tuple[int, tuple[tuple[AlignmentChunk, ...], ...]] | None:
        key = (wiki_index, target_index)
        if key in memo:
            return memo[key]
        if wiki_index == len(wiki_normalized) and target_index == len(
            target_normalized
        ):
            return (0, ((),))
        if wiki_index >= len(wiki_normalized) or target_index >= len(
            target_normalized
        ):
            memo[key] = None
            return None

        shapes = [(1, 1)]
        shapes.extend(
            (1, count)
            for count in range(2, max_chunk + 1)
        )
        shapes.extend(
            (count, 1)
            for count in range(2, max_chunk + 1)
        )
        candidates: list[tuple[int, tuple[AlignmentChunk, ...]]] = []
        for wiki_count, target_count in shapes:
            if wiki_index + wiki_count > len(wiki_normalized):
                continue
            if target_index + target_count > len(target_normalized):
                continue
            wiki_value = "".join(
                wiki_normalized[wiki_index : wiki_index + wiki_count]
            )
            target_value = "".join(
                target_normalized[target_index : target_index + target_count]
            )
            if wiki_value != target_value:
                continue
            remainder = solve(
                wiki_index + wiki_count,
                target_index + target_count,
            )
            if remainder is None:
                continue
            remainder_cost, remainder_paths = remainder
            chunk = AlignmentChunk(
                wiki_start=wiki_index,
                wiki_count=wiki_count,
                target_start=target_index,
                target_count=target_count,
            )
            cost = remainder_cost + wiki_count + target_count - 2
            candidates.extend(
                (cost, (chunk, *path))
                for path in remainder_paths
            )
        if not candidates:
            memo[key] = None
            return None
        minimum = min(cost for cost, _ in candidates)
        unique: list[tuple[AlignmentChunk, ...]] = []
        for cost, path in candidates:
            if cost == minimum and path not in unique:
                unique.append(path)
            if len(unique) > 1:
                break
        memo[key] = (minimum, tuple(unique))
        return memo[key]

    result = solve(0, 0)
    if result is None:
        raise RuntimeError("日文 Wiki 文本无法精确锚定日文 JSON")
    _, paths = result
    if len(paths) != 1:
        raise RuntimeError("日文 Wiki 与日文 JSON 存在多个等价对齐，拒绝猜测")
    return paths[0]


def _speaker_mapping_after_chunk(
    chinese: tuple[str, ...],
    japanese: tuple[tuple[str, ...], ...],
    mapping_items: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...] | None:
    if len(japanese) > 1 and not chinese:
        return mapping_items if all(not item for item in japanese) else None
    if len(japanese) > 1 and any(item != japanese[0] for item in japanese):
        return None
    japanese_speaker = japanese[0]
    if not chinese or not japanese_speaker:
        return mapping_items if len(japanese) == 1 else None
    if len(chinese) != len(japanese_speaker):
        return None
    forward = dict(mapping_items)
    reverse = {value: key for key, value in mapping_items}
    for chinese_name, japanese_name in zip(chinese, japanese_speaker):
        if chinese_name in forward and forward[chinese_name] != japanese_name:
            return None
        if japanese_name in reverse and reverse[japanese_name] != chinese_name:
            return None
        forward[chinese_name] = japanese_name
        reverse[japanese_name] = chinese_name
    return tuple(sorted(forward.items()))


def _align_chinese_to_japanese(
    chinese: ParsedWikiEpisode,
    japanese: ParsedWikiEpisode,
    *,
    max_chunk: int = 4,
) -> tuple[AlignmentChunk, ...]:
    """Align one Chinese Wiki row to one-or-more JP Wiki rows by structure."""
    memo: dict[
        tuple[int, int, tuple[tuple[str, str], ...]],
        tuple[int, tuple[tuple[AlignmentChunk, ...], ...]] | None,
    ] = {}

    def solve(
        chinese_index: int,
        japanese_index: int,
        mapping_items: tuple[tuple[str, str], ...],
    ) -> tuple[int, tuple[tuple[AlignmentChunk, ...], ...]] | None:
        key = (chinese_index, japanese_index, mapping_items)
        if key in memo:
            return memo[key]
        if chinese_index == len(chinese.texts) and japanese_index == len(
            japanese.texts
        ):
            return (0, ((),))
        if chinese_index >= len(chinese.texts) or japanese_index >= len(
            japanese.texts
        ):
            memo[key] = None
            return None
        candidates: list[tuple[int, tuple[AlignmentChunk, ...]]] = []
        for japanese_count in range(1, max_chunk + 1):
            if japanese_index + japanese_count > len(japanese.texts):
                break
            japanese_speakers = japanese.speaker_keys[
                japanese_index : japanese_index + japanese_count
            ]
            chinese_anchor = (
                chinese.anchor_keys[chinese_index]
                if chinese.anchor_keys
                else ""
            )
            japanese_anchors = (
                japanese.anchor_keys[
                    japanese_index : japanese_index + japanese_count
                ]
                if japanese.anchor_keys
                else tuple("" for _ in range(japanese_count))
            )
            if (
                japanese_count > 1
                and (chinese_anchor or any(japanese_anchors))
                and any(
                    anchor != chinese_anchor
                    for anchor in japanese_anchors
                )
            ):
                continue
            updated_mapping = _speaker_mapping_after_chunk(
                chinese.speaker_keys[chinese_index],
                japanese_speakers,
                mapping_items,
            )
            if updated_mapping is None:
                continue
            remainder = solve(
                chinese_index + 1,
                japanese_index + japanese_count,
                updated_mapping,
            )
            if remainder is None:
                continue
            remainder_cost, remainder_paths = remainder
            chunk = AlignmentChunk(
                wiki_start=chinese_index,
                wiki_count=1,
                target_start=japanese_index,
                target_count=japanese_count,
            )
            cost = remainder_cost + japanese_count - 1
            candidates.extend(
                (cost, (chunk, *path))
                for path in remainder_paths
            )
        if not candidates:
            memo[key] = None
            return None
        minimum = min(cost for cost, _ in candidates)
        unique: list[tuple[AlignmentChunk, ...]] = []
        for cost, path in candidates:
            if cost == minimum and path not in unique:
                unique.append(path)
            if len(unique) > 1:
                break
        memo[key] = (minimum, tuple(unique))
        return memo[key]

    result = solve(0, 0, ())
    if result is None:
        raise RuntimeError("中文 Wiki 行无法按说话人结构锚定日文 Wiki")
    _, paths = result
    if len(paths) != 1:
        raise RuntimeError("中文 Wiki 与日文 Wiki 存在多个结构对齐，拒绝猜测")
    return paths[0]


def _split_text_at_punctuation(
    text: str,
    count: int,
    target_texts: tuple[str, ...],
) -> tuple[str, ...]:
    if count == 1:
        if not text.strip():
            raise RuntimeError("待分配中文为空")
        return (text,)
    boundaries: list[int] = []
    for match in re.finditer(r"(?:\\n|\r?\n|[，,。！？!?；;：:]+)", text):
        end = match.end()
        if 0 < end < len(text) and end not in boundaries:
            boundaries.append(end)
    if len(boundaries) < count - 1:
        raise RuntimeError(
            f"中文合并行需要拆为 {count} 段，但没有足够标点/换行边界"
        )

    target_lengths = [
        len(normalize_japanese_anchor(value))
        for value in target_texts
    ]
    target_total = sum(target_lengths)
    scored: list[tuple[int, tuple[str, ...]]] = []
    for selected in itertools.combinations(boundaries, count - 1):
        offsets = (0, *selected, len(text))
        parts = tuple(
            text[offsets[index] : offsets[index + 1]].strip()
            for index in range(count)
        )
        if any(not part for part in parts):
            continue
        part_lengths = [
            len(normalize_japanese_anchor(value))
            for value in parts
        ]
        part_total = sum(part_lengths)
        score = sum(
            abs(
                part_length * target_total
                - target_length * part_total
            )
            for part_length, target_length in zip(
                part_lengths,
                target_lengths,
            )
        )
        scored.append((score, parts))
    if not scored:
        raise RuntimeError("中文合并行无法得到全部非空分段")
    minimum = min(score for score, _ in scored)
    winners = {
        parts
        for score, parts in scored
        if score == minimum
    }
    if len(winners) != 1:
        raise RuntimeError("中文标点分段存在多个等价结果，拒绝猜测")
    return next(iter(winners))


def _chunks_json(chunks: tuple[AlignmentChunk, ...]) -> list[dict[str, int]]:
    return [
        {
            "sourceStart": chunk.wiki_start,
            "sourceCount": chunk.wiki_count,
            "targetStart": chunk.target_start,
            "targetCount": chunk.target_count,
        }
        for chunk in chunks
    ]


def align_wiki_episode(
    chinese: HumanEpisode,
    japanese: ParsedWikiEpisode,
    json_texts: tuple[str, ...],
    *,
    japanese_url: str,
    japanese_sha256: str,
) -> HumanEpisode:
    japanese_to_json = _exact_chunk_alignment(
        japanese.texts,
        json_texts,
    )
    parsed_chinese = ParsedWikiEpisode(
        texts=chinese.texts,
        speaker_keys=chinese.speaker_keys,
        anchor_keys=chinese.anchor_keys,
    )
    chinese_to_japanese = _align_chinese_to_japanese(
        parsed_chinese,
        japanese,
    )
    chinese_by_japanese: list[str | None] = [None] * len(japanese.texts)
    for chunk in chinese_to_japanese:
        chinese_text = chinese.texts[chunk.wiki_start]
        japanese_slice = japanese.texts[
            chunk.target_start : chunk.target_start + chunk.target_count
        ]
        split = _split_text_at_punctuation(
            chinese_text,
            chunk.target_count,
            japanese_slice,
        )
        for offset, value in enumerate(split):
            chinese_by_japanese[chunk.target_start + offset] = value
    if any(value is None or not value.strip() for value in chinese_by_japanese):
        raise RuntimeError("中文 Wiki 未覆盖全部日文 Wiki 锚点")

    output: list[str] = []
    for chunk in japanese_to_json:
        chinese_slice = tuple(
            str(value)
            for value in chinese_by_japanese[
                chunk.wiki_start : chunk.wiki_start + chunk.wiki_count
            ]
        )
        target_slice = json_texts[
            chunk.target_start : chunk.target_start + chunk.target_count
        ]
        if chunk.wiki_count > 1:
            if chunk.target_count != 1:
                raise RuntimeError("禁止未证明的多对多 Wiki/JSON 对齐")
            output.append("\\n".join(chinese_slice))
        elif chunk.target_count > 1:
            output.extend(
                _split_text_at_punctuation(
                    chinese_slice[0],
                    chunk.target_count,
                    target_slice,
                )
            )
        else:
            output.append(chinese_slice[0])
    if len(output) != len(json_texts) or any(not value.strip() for value in output):
        raise RuntimeError("中文 Wiki 对齐后未生成完整 JSON 文本序列")
    return HumanEpisode(
        texts=tuple(output),
        speaker_keys=tuple(() for _ in output),
        source_type=chinese.source_type,
        source_name=chinese.source_name,
        source_url=chinese.source_url,
        source_sha256=chinese.source_sha256,
        alignment={
            "method": "exact_japanese_wiki_anchor",
            "japaneseWikiUrl": japanese_url,
            "japaneseWikiSha256": japanese_sha256,
            "japaneseWikiRows": len(japanese.texts),
            "chineseWikiRows": len(chinese.texts),
            "jsonEvents": len(json_texts),
            "chineseToJapanese": _chunks_json(chinese_to_japanese),
            "japaneseToJson": _chunks_json(japanese_to_json),
        },
    )


def _punctuation_only(value: str) -> bool:
    normalized = normalize_japanese_anchor(value)
    return bool(normalized) and not any(
        unicodedata.category(character)[0] in {"L", "N"}
        for character in normalized
    )


def _align_ass_with_punctuation_omissions(
    texts: tuple[str, ...],
    json_texts: tuple[str, ...],
) -> tuple[tuple[str, ...], list[int]]:
    """Align ASS ordinally, permitting only exactly identified silent punctuation."""
    memo: dict[
        tuple[int, int],
        tuple[tuple[tuple[str, ...], tuple[int, ...]], ...],
    ] = {}

    def solve(
        ass_index: int,
        json_index: int,
    ) -> tuple[tuple[tuple[str, ...], tuple[int, ...]], ...]:
        key = (ass_index, json_index)
        if key in memo:
            return memo[key]
        if ass_index == len(texts) and json_index == len(json_texts):
            return (((), ()),)
        if json_index >= len(json_texts):
            return ()
        candidates: list[tuple[tuple[str, ...], tuple[int, ...]]] = []
        json_text = json_texts[json_index]
        punctuation = _punctuation_only(json_text)
        if ass_index < len(texts) and (
            not punctuation
            or normalize_japanese_anchor(texts[ass_index])
            == normalize_japanese_anchor(json_text)
        ):
            for output, omitted in solve(ass_index + 1, json_index + 1):
                candidates.append(((texts[ass_index], *output), omitted))
        if punctuation:
            for output, omitted in solve(ass_index, json_index + 1):
                candidates.append(
                    ((json_text, *output), (json_index, *omitted))
                )
        unique: list[tuple[tuple[str, ...], tuple[int, ...]]] = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
            if len(unique) > 1:
                break
        memo[key] = tuple(unique)
        return memo[key]

    paths = solve(0, 0)
    if not paths:
        raise RuntimeError("ASS 缺口不能由逐项精确匹配的静默标点事件解释")
    if len(paths) != 1:
        raise RuntimeError("ASS 的静默标点缺口存在多个等价位置，拒绝猜测")
    output, omitted = paths[0]
    return output, list(omitted)


def align_ass_episode(
    texts: tuple[str, ...],
    japanese: ParsedWikiEpisode,
    json_texts: tuple[str, ...],
    *,
    source_name: str,
    source_sha256: str,
    japanese_url: str,
    japanese_sha256: str,
) -> HumanEpisode:
    japanese_to_json = _exact_chunk_alignment(
        japanese.texts,
        json_texts,
    )
    if len(texts) == len(json_texts):
        output = texts
        method = "exact_count_with_exact_japanese_wiki_anchor"
        omitted: list[int] = []
    elif len(texts) < len(json_texts):
        output, omitted = _align_ass_with_punctuation_omissions(
            texts,
            json_texts,
        )
        method = "exact_japanese_wiki_anchor_plus_unique_punctuation_omission"
    elif len(texts) == len(japanese.texts):
        chinese_by_japanese = texts
        projected: list[str] = []
        for chunk in japanese_to_json:
            source_slice = chinese_by_japanese[
                chunk.wiki_start : chunk.wiki_start + chunk.wiki_count
            ]
            target_slice = json_texts[
                chunk.target_start : chunk.target_start + chunk.target_count
            ]
            if chunk.wiki_count > 1 and chunk.target_count == 1:
                projected.append("\\n".join(source_slice))
            elif chunk.wiki_count == 1 and chunk.target_count > 1:
                projected.extend(
                    _split_text_at_punctuation(
                        source_slice[0],
                        chunk.target_count,
                        target_slice,
                    )
                )
            elif chunk.wiki_count == chunk.target_count == 1:
                projected.append(source_slice[0])
            else:
                raise RuntimeError("禁止未证明的 ASS 多对多重排")
        output = tuple(projected)
        method = "ordinal_ass_to_exact_japanese_wiki_anchor"
        omitted = []
    else:
        raise RuntimeError(
            "ASS 数量无法由日文 Wiki 精确锚点证明："
            f"ASS {len(texts)} / Wiki {len(japanese.texts)} / "
            f"JSON {len(json_texts)}"
        )
    if len(output) != len(json_texts) or any(not value.strip() for value in output):
        raise RuntimeError("ASS 对齐后未生成完整 JSON 文本序列")
    return HumanEpisode(
        texts=tuple(output),
        speaker_keys=tuple(() for _ in output),
        source_type="rounddora_0728_human",
        source_name=source_name,
        source_url="",
        source_sha256=source_sha256,
        alignment={
            "method": method,
            "japaneseWikiUrl": japanese_url,
            "japaneseWikiSha256": japanese_sha256,
            "japaneseWikiRows": len(japanese.texts),
            "assRows": len(texts),
            "jsonEvents": len(json_texts),
            "omittedPunctuationJsonIndexes": omitted,
            "japaneseToJson": _chunks_json(japanese_to_json),
        },
    )


def group_jp_json(group: dict[str, Any], source: str) -> Path:
    path = JP_ROOT / str(group["outputDir"]) / PurePosixPath(source).name
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"日文 JSON 不存在：{path}")
    return path


def import_group(
    group: dict[str, Any],
    wiki: dict[int, HumanEpisode],
    japanese_wiki: dict[int, ParsedWikiEpisode],
    japanese_wiki_url: str,
    japanese_wiki_sha256: str,
    ass_files: dict[str, Path],
    *,
    write: bool,
) -> dict[str, Any]:
    category = str(group["category"])
    group_key = str(group["groupKey"])
    output_dir = CN_ROOT / category / group_key
    cn_path = output_dir / f"{group_key}_cn.txt"
    if cn_path.exists():
        return {"groupKey": group_key, "status": "existing_local"}

    jp_path = JP_ROOT / str(group["textFile"])
    sections = common.parse_txt(jp_path)
    source_paths = group.get("sources")
    if not isinstance(source_paths, list) or len(source_paths) != len(sections):
        raise RuntimeError(f"{group_key}: manifest/Section 数量不一致")

    translations: list[list[str]] = []
    episode_sources: list[HumanEpisode] = []
    rejected: list[dict[str, Any]] = []
    for episode, (section, raw_source) in enumerate(zip(sections, source_paths)):
        jp_json = group_jp_json(group, str(raw_source))
        rows = common.extract_rows(jp_json)
        json_texts = tuple(str(row["text"]) for row in rows)
        event_count = len(json_texts)
        wiki_episode = wiki.get(episode)
        japanese_episode = japanese_wiki.get(episode)
        ass_path = ass_episode_path(ass_files, group_key, episode)
        ass_texts: tuple[str, ...] = ()
        selected: HumanEpisode | None = None
        alignment_errors: list[str] = []
        if wiki_episode:
            if japanese_episode:
                try:
                    selected = align_wiki_episode(
                        wiki_episode,
                        japanese_episode,
                        json_texts,
                        japanese_url=japanese_wiki_url,
                        japanese_sha256=japanese_wiki_sha256,
                    )
                except RuntimeError as exc:
                    alignment_errors.append(f"wiki:{exc}")
            else:
                alignment_errors.append("wiki:缺少同角色日文 Wiki Episode 锚点")
        if selected is None and ass_path:
            ass_texts = parse_ass(ass_path)
            if japanese_episode:
                try:
                    selected = align_ass_episode(
                        ass_texts,
                        japanese_episode,
                        json_texts,
                        source_name=ass_path.name,
                        source_sha256=digest_file(ass_path),
                        japanese_url=japanese_wiki_url,
                        japanese_sha256=japanese_wiki_sha256,
                    )
                except RuntimeError as exc:
                    alignment_errors.append(f"ass:{exc}")
            elif len(ass_texts) == event_count:
                selected = HumanEpisode(
                    texts=ass_texts,
                    speaker_keys=tuple(() for _ in ass_texts),
                    source_type="rounddora_0728_human",
                    source_name=ass_path.name,
                    source_url="",
                    source_sha256=digest_file(ass_path),
                    alignment={
                        "method": "exact_count_without_adjustment",
                        "assRows": len(ass_texts),
                        "jsonEvents": event_count,
                    },
                )
            else:
                alignment_errors.append(
                    "ass:数量不等且缺少日文 Wiki 锚点，禁止调整"
                )
        if selected is None:
            rejected.append(
                {
                    "episode": episode,
                    "source": section.source,
                    "jsonEvents": event_count,
                    "wikiEvents": len(wiki_episode.texts) if wiki_episode else None,
                    "japaneseWikiEvents": (
                        len(japanese_episode.texts)
                        if japanese_episode
                        else None
                    ),
                    "assFile": ass_path.name if ass_path else None,
                    "assEvents": len(ass_texts) if ass_path else None,
                    "alignmentErrors": alignment_errors,
                }
            )
        else:
            translations.append(list(selected.texts))
            episode_sources.append(selected)
    if rejected:
        return {
            "groupKey": group_key,
            "status": "rejected",
            "reasons": rejected,
        }

    with tempfile.TemporaryDirectory(
        prefix=f".{group_key}-",
        dir=output_dir.parent,
    ) as temporary:
        stage = Path(temporary)
        json_meta: list[dict[str, Any]] = []
        for section, raw_source, texts, human_source in zip(
            sections,
            source_paths,
            translations,
            episode_sources,
        ):
            jp_json = group_jp_json(group, str(raw_source))
            destination = stage / section.source
            output_sha = common.apply_translated_texts(
                jp_json,
                texts,
                destination,
            )
            json.loads(destination.read_text(encoding="utf-8"))
            json_meta.append(
                {
                    "source": section.source,
                    "jpSha256": digest_file(jp_json),
                    "cnSha256": output_sha,
                    "provenance": human_source.source_type,
                    "sourceName": human_source.source_name,
                    "sourceUrl": human_source.source_url,
                    "sourceSha256": human_source.source_sha256,
                    "eventCount": len(texts),
                    "alignment": human_source.alignment,
                }
            )

        staged_cn = stage / f"{group_key}_cn.txt"
        staged_cn.write_text(
            common.render_cn(sections, translations),
            encoding="utf-8",
        )
        report = common.build_report(
            category,
            group_key,
            jp_path,
            staged_cn,
            "trusted-wiki-and-rounddora-0728",
            json_meta,
        )
        provenances = sorted({item.source_type for item in episode_sources})
        report["provenance"] = (
            provenances[0] if len(provenances) == 1 else "trusted_human_mixed"
        )
        report["sourcePriority"] = [
            "repository_existing_chinese",
            "exedra_wiki_human",
            "rounddora_0728_human",
        ]
        (stage / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}").write_bytes(
            common.json_bytes(report)
        )
        sidecar = {
            "version": 1,
            "sourceIdentity": str(group["id"]),
            "provenance": report["provenance"],
            "machineTranslation": False,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "jpSha256": pipeline._sha256_utf8_text_file(jp_path),
            "cnSha256": pipeline._sha256_utf8_text_file(staged_cn),
            "episodes": json_meta,
        }
        (stage / f"{group_key}_cn.provenance.json").write_bytes(
            common.json_bytes(sidecar)
        )
        pipeline._validate_exedra_cn_import_report(
            group=pipeline.OrganizedExedraGroup(
                manifest_id=str(group["id"]),
                raw_category=category,
                category=pipeline.EXEDRA_CATEGORY_MAP[category],
                group_key=group_key,
                output_dir=Path(category, group_key),
                text_file=Path(str(group["textFile"])),
                source_paths=tuple(str(value) for value in source_paths),
                source_names=tuple(section.source for section in sections),
                title="",
            ),
            jp_path=jp_path,
            cn_path=staged_cn,
            jp_sections=pipeline._exedra_alignment_sections(jp_path),
            cn_sections=pipeline._exedra_alignment_sections(staged_cn),
        )
        if write:
            common.commit_staged_group(stage, output_dir)
    return {
        "groupKey": group_key,
        "status": "imported" if write else "ready",
        "jsonCount": len(json_meta),
        "eventCount": sum(item["eventCount"] for item in json_meta),
        "provenances": sorted({item["provenance"] for item in json_meta}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ass_root", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--only-group", action="append", default=[])
    parser.add_argument("--wiki-workers", type=int, default=8)
    args = parser.parse_args()

    ass_files, inventory = inventory_ass(args.ass_root)
    manifest = common.load_json(MANIFEST)
    groups = [
        group
        for group in manifest.get("groups", [])
        if isinstance(group, dict)
        and group.get("category") == "3_Character"
        and (
            not args.only_group
            or str(group.get("groupKey")) in set(args.only_group)
        )
    ]
    expected_keys = {str(group["groupKey"]) for group in groups}
    missing_mapping = expected_keys - set(ASS_CHARACTER_BASES)
    if missing_mapping:
        raise SystemExit(f"缺少 ASS 显式角色映射：{sorted(missing_mapping)}")

    wiki_results: dict[str, dict[int, HumanEpisode]] = {}
    japanese_wiki_results: dict[str, dict[int, ParsedWikiEpisode]] = {}
    japanese_wiki_sources: dict[str, tuple[str, str]] = {}
    wiki_errors: dict[str, list[str]] = {}
    wiki_items = [
        (key, CHARACTER_WIKI_SLUGS[key])
        for key in expected_keys
    ]
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(args.wiki_workers, 16))
    ) as executor:
        for (
            key,
            episodes,
            japanese_episodes,
            japanese_url,
            japanese_sha,
            errors,
        ) in executor.map(fetch_wiki_group, wiki_items):
            wiki_results[key] = episodes
            japanese_wiki_results[key] = japanese_episodes
            japanese_wiki_sources[key] = (japanese_url, japanese_sha)
            if errors:
                wiki_errors[key] = errors

    results: list[dict[str, Any]] = []
    for group in groups:
        key = str(group["groupKey"])
        try:
            results.append(
                import_group(
                    group,
                    wiki_results.get(key, {}),
                    japanese_wiki_results.get(key, {}),
                    japanese_wiki_sources.get(key, ("", ""))[0],
                    japanese_wiki_sources.get(key, ("", ""))[1],
                    ass_files,
                    write=args.write,
                )
            )
        except Exception as exc:
            results.append(
                {
                    "groupKey": key,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "writeMode": args.write,
        "policy": (
            "existing_then_exact_japanese_anchored_wiki_then_"
            "exact_japanese_anchored_rounddora_0728"
        ),
        "machineTranslation": False,
        "inventory": {
            "fileCount": inventory["fileCount"],
            "totalBytes": inventory["totalBytes"],
        },
        "wiki": {
            "pageCount": sum(bool(value) for value in wiki_results.values()),
            "japaneseAnchorPageCount": sum(
                bool(value) for value in japanese_wiki_results.values()
            ),
            "errors": wiki_errors,
        },
        "counts": {
            status: sum(item["status"] == status for item in results)
            for status in (
                "existing_local",
                "ready",
                "imported",
                "rejected",
                "failed",
            )
        },
        "results": results,
    }
    if args.write:
        INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        INVENTORY_PATH.write_bytes(common.json_bytes(inventory))
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUDIT_PATH.write_bytes(common.json_bytes(report))
    print(json.dumps(report["counts"], ensure_ascii=False))
    for item in results:
        if item["status"] in {"rejected", "failed"}:
            print(json.dumps(item, ensure_ascii=False))
    return 2 if report["counts"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
