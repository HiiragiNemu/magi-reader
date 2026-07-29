#!/usr/bin/env python3
"""Generate a deterministic, deployment-safe Exedra reaction voice catalogue.

Only the reaction groups declared by the committed Exedra manifest are read.
Audio is hashed one file at a time; the full audio tree is never enumerated or
loaded into memory.  The generated catalogue contains no host-absolute paths,
so production builds do not depend on the local extraction directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER_ROOT = Path(
    r"D:\magia\magia_exedra_jp_data\manifests\ja-Jpan"
)
DEFAULT_AUDIO_ROOT = Path(
    r"D:\magia\ma-ex-data\gamedata\Resources\Sound\Cv"
)
DEFAULT_EXEDRA_ROOT = (
    ROOT / "magiraexedra-source-master" / "Scenarios_full"
)
DEFAULT_CN_ROOT = (
    ROOT / "magiraexedra-translate-data-master" / "Scenarios_full"
)
DEFAULT_DICTIONARY = ROOT / "website" / "app" / "config" / "dictionary.ts"
DEFAULT_OUTPUT = ROOT / "artifacts" / "exedra_voice_catalog.json"

EXPECTED_REACTION_GROUPS = 86
REACTION_CATEGORY = "6_Reaction"
GROUP_KEY_RE = re.compile(r"^cv_(\d{6})$")
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
BOOK_SUFFIX_RE = re.compile(
    r"_(?:覚醒ボイス|魔法少女ストーリーボイス|ストーリーボイス|ボイス)_\d+$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_PAIR_RE = re.compile(r'"([^"]+)"\s*:\s*"([^"]*)"')
CHARACTER_TITLE_ALIASES = {
    "アシュリー・テイラー": "アシュリー",
    "メリッサ・ド・ヴィニョル": "メリッサ",
}
CHARACTER_VARIANT_NAMES = {
    "鹿目まどか": ("アルティメットまどか",),
}


class CatalogError(RuntimeError):
    """Raised when a source cannot be mapped without guessing."""


def _load_json(path: Path) -> Any:
    if not path.is_file() or path.is_symlink():
        raise CatalogError(f"JSON 不存在、不是普通文件或是符号链接: {path}")
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"JSON 无法读取: {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _canonical_root(path: Path, *, label: str) -> Path:
    if _is_link_like(path):
        raise CatalogError(f"{label} 不允许是符号链接或目录联接: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CatalogError(f"{label} 不存在: {path}: {exc}") from exc
    if not resolved.is_dir() or _is_link_like(resolved):
        raise CatalogError(f"{label} 不是普通目录: {resolved}")
    return resolved


def _safe_relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{label} 必须是非空相对路径")
    if "\\" in value or "\0" in value:
        raise CatalogError(f"{label} 含非法字符: {value!r}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise CatalogError(f"{label} 不是安全相对路径: {value!r}")
    return relative


def _safe_child(root: Path, parts: Iterable[str], *, label: str) -> Path:
    component_list = tuple(parts)
    candidate = root.joinpath(*component_list)
    cursor = root
    for component in component_list:
        cursor = cursor / component
        if _is_link_like(cursor):
            raise CatalogError(f"{label} 不允许经过符号链接或目录联接: {cursor}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CatalogError(f"{label} 越界或不存在: {candidate}") from exc
    if not resolved.is_file() or _is_link_like(resolved):
        raise CatalogError(f"{label} 不是普通文件: {resolved}")
    return resolved


def _load_mst_list(master_root: Path, filename: str) -> list[Mapping[str, Any]]:
    payload = _load_json(master_root / filename)
    if not isinstance(payload, dict):
        raise CatalogError(f"{filename} 顶层必须是对象")
    body = payload.get("payload")
    rows = body.get("mstList") if isinstance(body, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CatalogError(f"{filename} 缺少 payload.mstList")
    return rows


def _unique_int_map(
    rows: Iterable[Mapping[str, Any]],
    key_name: str,
    *,
    label: str,
) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        value = row.get(key_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise CatalogError(f"{label}.{key_name} 不是整数: {value!r}")
        if value in result:
            raise CatalogError(f"{label}.{key_name} 重复: {value}")
        result[value] = row
    return result


def load_explicit_name_map(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise CatalogError(f"中文角色名字典不存在或不安全: {path}")
    text = path.read_text(encoding="utf-8")
    marker = "export const NAME_TRANSLATE_MAP"
    start = text.find(marker)
    if start < 0:
        raise CatalogError("dictionary.ts 缺少 NAME_TRANSLATE_MAP")
    end = text.find("\n};", start)
    if end < 0:
        raise CatalogError("dictionary.ts 的 NAME_TRANSLATE_MAP 未闭合")
    result: dict[str, str] = {}
    for match in NAME_PAIR_RE.finditer(text[start:end]):
        source, translated = match.groups()
        existing = result.get(source)
        if existing is not None and existing != translated:
            raise CatalogError(f"中文角色名字典冲突: {source!r}")
        result[source] = translated
    if not result:
        raise CatalogError("dictionary.ts 的 NAME_TRANSLATE_MAP 为空")
    return result


def first_cn_speaker(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("--- ["):
                continue
            match = re.match(r"^([^：:\r\n]{1,80})[：:]", line)
            if match:
                return match.group(1).strip() or None
    return None


def _normalise_book_base(book_title: str) -> str:
    base = BOOK_SUFFIX_RE.sub("", book_title.strip())
    if not base or base == book_title.strip():
        raise CatalogError(f"无法识别 reaction bookTitle: {book_title!r}")
    return base


def _split_character_form(
    base_title: str,
    manifest_character: str | None,
) -> tuple[str, str | None]:
    if manifest_character:
        title_characters = (
            manifest_character,
            CHARACTER_TITLE_ALIASES.get(manifest_character, manifest_character),
        )
        for title_character in dict.fromkeys(title_characters):
            if base_title == title_character:
                return manifest_character, None
            prefix = f"{title_character}_"
            if base_title.startswith(prefix):
                return manifest_character, base_title[len(prefix) :] or None
        for variant_name in CHARACTER_VARIANT_NAMES.get(manifest_character, ()):
            if base_title == variant_name:
                return manifest_character, variant_name
            if base_title == f"{variant_name}_魔法少女":
                return manifest_character, variant_name
        raise CatalogError(
            "bookTitle 与角色主表不一致: "
            f"{base_title!r}, manifest={manifest_character!r}"
        )
    character, separator, form = base_title.partition("_")
    if not character:
        raise CatalogError(f"bookTitle 缺少角色名: {base_title!r}")
    return character, form if separator and form else None


def _source_audio_reference(source: Mapping[str, Any], *, label: str) -> tuple[str, str]:
    sheets = source.get("sheetList")
    if not isinstance(sheets, list) or not sheets:
        raise CatalogError(f"{label} 缺少 sheetList")
    references: list[tuple[str, str]] = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise CatalogError(f"{label}.sheetList 含非对象")
        header = sheet.get("headerRow")
        headers = header.get("cellList") if isinstance(header, dict) else None
        rows = sheet.get("contentRowList")
        if not isinstance(headers, list) or not isinstance(rows, list):
            raise CatalogError(f"{label} sheet 结构无效")
        try:
            sound_file_index = headers.index("SoundFile")
            sound_name_index = headers.index("SoundName")
        except ValueError:
            continue
        for row in rows:
            cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(cells, list):
                raise CatalogError(f"{label} contentRowList 含无效行")
            sound_file = (
                str(cells[sound_file_index]).strip()
                if sound_file_index < len(cells)
                else ""
            )
            sound_name = (
                str(cells[sound_name_index]).strip()
                if sound_name_index < len(cells)
                else ""
            )
            if not sound_file and not sound_name:
                continue
            if not sound_file or not sound_name:
                raise CatalogError(f"{label} 的 SoundFile/SoundName 不完整")
            if (
                not SAFE_COMPONENT_RE.fullmatch(sound_file)
                or not SAFE_COMPONENT_RE.fullmatch(sound_name)
                or sound_file in {".", ".."}
                or sound_name in {".", ".."}
            ):
                raise CatalogError(f"{label} 含非法音频资源键")
            references.append((sound_file, sound_name))
    unique = list(dict.fromkeys(references))
    if len(unique) != 1:
        raise CatalogError(
            f"{label} 必须精确指向一个唯一音频，实际 {len(unique)} 个"
        )
    return unique[0]


def _display_title(
    character_jp: str,
    character_cn: str | None,
    form_jp: str | None,
) -> str:
    if character_cn and character_cn != character_jp:
        title = f"{character_cn}（{character_jp}）"
    else:
        title = character_cn or character_jp
    if form_jp:
        title = f"{title} · {form_jp}"
    if not title or len(title) > 240 or any(ord(char) < 32 for char in title):
        raise CatalogError(f"生成的显示标题无效: {title!r}")
    return title


def build_catalog(
    *,
    master_root: Path,
    audio_root: Path,
    exedra_root: Path,
    cn_root: Path,
    dictionary_path: Path,
    expected_group_count: int = EXPECTED_REACTION_GROUPS,
) -> dict[str, Any]:
    master_root = _canonical_root(master_root, label="Exedra 主表目录")
    audio_root = _canonical_root(audio_root, label="Exedra 语音目录")
    exedra_root = _canonical_root(exedra_root, label="Exedra 剧情目录")
    cn_root = cn_root.resolve(strict=False)

    characters = _unique_int_map(
        _load_mst_list(master_root, "getCharacterMstList.json"),
        "characterMstId",
        label="CharacterMst",
    )
    figures = _unique_int_map(
        _load_mst_list(master_root, "getStyleFigureMstList.json"),
        "styleFigureMstId",
        label="StyleFigureMst",
    )
    styles = _load_mst_list(master_root, "getStyleMstList.json")
    explicit_names = load_explicit_name_map(dictionary_path)

    manifest_path = exedra_root / "exedra_manifest.json"
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1:
        raise CatalogError("Exedra manifest schemaVersion 必须为 1")
    raw_groups = manifest.get("groups")
    if not isinstance(raw_groups, list):
        raise CatalogError("Exedra manifest 缺少 groups")
    reaction_groups = [
        group
        for group in raw_groups
        if isinstance(group, dict) and group.get("category") == REACTION_CATEGORY
    ]
    if len(reaction_groups) != expected_group_count:
        raise CatalogError(
            f"reaction 组数量不正确: {len(reaction_groups)}，"
            f"期望 {expected_group_count}"
        )

    style_names_by_figure: dict[int, list[str]] = {}
    for row in styles:
        figure_id = row.get("styleFigureMstId")
        name = str(row.get("name") or "").strip()
        if (
            isinstance(figure_id, int)
            and not isinstance(figure_id, bool)
            and row.get("isCollectionDisp") is True
            and name
        ):
            names = style_names_by_figure.setdefault(figure_id, [])
            if name not in names:
                names.append(name)

    groups: list[dict[str, Any]] = []
    seen_group_keys: set[str] = set()
    seen_audio_keys: set[str] = set()
    total_audio_bytes = 0
    total_sources = 0
    manifest_matched_groups = 0

    for group_index, raw_group in enumerate(reaction_groups):
        group_key = str(raw_group.get("groupKey") or "").strip()
        match = GROUP_KEY_RE.fullmatch(group_key)
        if not match:
            raise CatalogError(f"reaction groupKey 非法: {group_key!r}")
        if group_key in seen_group_keys:
            raise CatalogError(f"reaction groupKey 重复: {group_key}")
        seen_group_keys.add(group_key)
        figure_id = int(match.group(1))

        raw_source_paths = raw_group.get("sources")
        if not isinstance(raw_source_paths, list) or not raw_source_paths:
            raise CatalogError(f"{group_key} 没有 sources")
        if raw_group.get("sourceCount") != len(raw_source_paths):
            raise CatalogError(f"{group_key} sourceCount 与 sources 不一致")

        figure = figures.get(figure_id)
        manifest_character: str | None = None
        character_id: int | None = None
        cue_sheet_template: str | None = None
        if figure:
            raw_character_id = figure.get("characterMstId")
            if isinstance(raw_character_id, bool) or not isinstance(raw_character_id, int):
                raise CatalogError(f"{group_key} 的 characterMstId 无效")
            character = characters.get(raw_character_id)
            if character is None:
                raise CatalogError(f"{group_key} 指向不存在的角色 {raw_character_id}")
            manifest_character = str(character.get("name") or "").strip()
            if not manifest_character:
                raise CatalogError(f"{group_key} 的角色名为空")
            character_id = raw_character_id
            cue_sheet_template = str(figure.get("voiceCueSheetName") or "").strip()
            expected_template = f"{group_key}_{{0}}"
            if cue_sheet_template != expected_template:
                raise CatalogError(
                    f"{group_key} 的 voiceCueSheetName 不一致: "
                    f"{cue_sheet_template!r}"
                )
            manifest_matched_groups += 1

        source_records: list[dict[str, Any]] = []
        book_bases: list[str] = []
        for source_index, raw_source_path in enumerate(raw_source_paths):
            relative = _safe_relative_path(
                raw_source_path,
                label=f"groups[{group_index}].sources[{source_index}]",
            )
            if (
                len(relative.parts) < 3
                or relative.parts[0] != REACTION_CATEGORY
                or not relative.name.endswith(".json")
            ):
                raise CatalogError(
                    f"{group_key} sourcePath 不属于 reaction JSON: {relative}"
                )
            source_name = relative.name
            source_path = _safe_child(
                exedra_root,
                (REACTION_CATEGORY, group_key, source_name),
                label=f"{group_key}/{source_name}",
            )
            source = _load_json(source_path)
            if not isinstance(source, dict):
                raise CatalogError(f"{source_name} 顶层必须是对象")
            book_title = str(source.get("bookTitle") or "").strip()
            book_base = _normalise_book_base(book_title)
            if book_base not in book_bases:
                book_bases.append(book_base)
            sound_file, sound_name = _source_audio_reference(
                source,
                label=f"{group_key}/{source_name}",
            )
            audio_key = f"{sound_file}\0{sound_name}"
            if audio_key in seen_audio_keys:
                raise CatalogError(
                    "不同 source JSON 复用了同一音频键: "
                    f"{sound_file}/{sound_name}"
                )
            seen_audio_keys.add(audio_key)
            audio_path = _safe_child(
                audio_root,
                (sound_file, f"{sound_name}.ogg"),
                label=f"音频 {sound_file}/{sound_name}.ogg",
            )
            audio_bytes = audio_path.stat().st_size
            if audio_bytes <= 0:
                raise CatalogError(f"音频为空: {audio_path}")
            audio_sha = _sha256_file(audio_path)
            if not SHA256_RE.fullmatch(audio_sha):
                raise CatalogError(f"音频 SHA-256 无效: {audio_path}")
            total_audio_bytes += audio_bytes
            total_sources += 1
            wiki_filename = f"{sound_name}.ogg"
            source_records.append(
                {
                    "sourceJson": (
                        f"{REACTION_CATEGORY}/{group_key}/{source_name}"
                    ),
                    "sourceJsonSha256": _sha256_file(source_path),
                    "bookTitle": book_title,
                    "soundFile": sound_file,
                    "soundName": sound_name,
                    "audioKey": audio_key.replace("\0", ":"),
                    "audioRelativePath": f"{sound_file}/{wiki_filename}",
                    "localExists": True,
                    "bytes": audio_bytes,
                    "sha256": audio_sha,
                    "wikiAudioUrl": (
                        "https://exedra.wiki/wiki/Special:Redirect/file/"
                        + quote(wiki_filename, safe="._-")
                    ),
                }
            )

        resolved_titles = list(
            dict.fromkeys(
                _split_character_form(book_base, manifest_character)
                for book_base in book_bases
            )
        )
        if len(resolved_titles) != 1:
            raise CatalogError(
                f"{group_key} 的 bookTitle 角色/形态不一致: {book_bases}"
            )
        character_jp, form_jp = resolved_titles[0]
        cn_text = (
            cn_root
            / REACTION_CATEGORY
            / group_key
            / f"{group_key}_cn.txt"
        )
        cn_speaker = first_cn_speaker(cn_text)
        dictionary_name = explicit_names.get(character_jp)
        character_cn: str | None = None
        character_cn_source: str | None = None
        if cn_speaker and cn_speaker != character_jp:
            character_cn = cn_speaker
            character_cn_source = "cn_txt_speaker"
        elif dictionary_name:
            character_cn = dictionary_name
            character_cn_source = "dictionary"
        elif cn_speaker:
            character_cn = cn_speaker
            character_cn_source = "cn_txt_speaker"

        groups.append(
            {
                "groupId": str(raw_group.get("id") or ""),
                "groupKey": group_key,
                "figureId": figure_id if figure else None,
                "characterId": character_id,
                "characterNameJp": character_jp,
                "characterNameCn": character_cn,
                "characterNameCnSource": character_cn_source,
                "formNameJp": form_jp,
                "formNameCn": None,
                "styleNamesJp": style_names_by_figure.get(figure_id, []),
                "cueSheetTemplate": cue_sheet_template,
                "displayTitle": _display_title(
                    character_jp,
                    character_cn,
                    form_jp,
                ),
                "sourceCount": len(source_records),
                "sources": source_records,
            }
        )

    return {
        "schemaVersion": 1,
        "policy": "exedra_reaction_manifest_and_source_json_exact_audio",
        "wikiAudioUrlPolicy": "Special:Redirect/file/<SoundName>.ogg",
        "summary": {
            "groups": len(groups),
            "manifestMatchedGroups": manifest_matched_groups,
            "scriptNamedGroups": len(groups) - manifest_matched_groups,
            "sources": total_sources,
            "uniqueAudioKeys": len(seen_audio_keys),
            "localAudioBytes": total_audio_bytes,
        },
        "inputs": {
            "exedraManifestSha256": _sha256_file(manifest_path),
            "characterMstSha256": _sha256_file(
                master_root / "getCharacterMstList.json"
            ),
            "styleFigureMstSha256": _sha256_file(
                master_root / "getStyleFigureMstList.json"
            ),
            "styleMstSha256": _sha256_file(
                master_root / "getStyleMstList.json"
            ),
        },
        "groups": groups,
    }


def catalog_bytes(catalog: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            catalog,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n"
    ).encode("utf-8")


def write_catalog(path: Path, catalog: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = catalog_bytes(catalog)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master-root", type=Path, default=DEFAULT_MASTER_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--exedra-root", type=Path, default=DEFAULT_EXEDRA_ROOT)
    parser.add_argument("--cn-root", type=Path, default=DEFAULT_CN_ROOT)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="验证既有产物与重新生成的字节完全一致，不写文件",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        catalog = build_catalog(
            master_root=args.master_root,
            audio_root=args.audio_root,
            exedra_root=args.exedra_root,
            cn_root=args.cn_root,
            dictionary_path=args.dictionary,
        )
        data = catalog_bytes(catalog)
        if args.check:
            if not args.output.is_file() or args.output.read_bytes() != data:
                raise CatalogError(f"语音目录不是最新可复现产物: {args.output}")
            print(f"Exedra 语音目录可复现: {args.output}")
        else:
            write_catalog(args.output, catalog)
            print(f"已生成 Exedra 语音目录: {args.output}")
        summary = catalog["summary"]
        print(
            "groups={groups} sources={sources} uniqueAudioKeys={uniqueAudioKeys} "
            "bytes={localAudioBytes}".format(**summary)
        )
        return 0
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
