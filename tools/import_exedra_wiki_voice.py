#!/usr/bin/env python3
"""Import trusted Chinese Exedra reaction voices from Exedra Wiki.

Only main-namespace pages whose titles end in ``/Voice/zh`` are considered.
Each Wiki row must satisfy both of these independent identity checks:

* ``file_name`` exactly equals the manifest source basename plus ``.ogg``;
* normalized ``text_jp`` exactly equals all Japanese JSON text events joined
  in source order.

One audited source-id alias is allowed only after the target and alias manifest
groups prove an exact one-to-one source suffix, sheet/row, action, speaker, and
per-event Japanese match.  The Wiki ``file_name`` must still exactly match the
audited alias source.  This is an explicit source identity correction, not a
fuzzy text match.

The Chinese ``text_en`` is never translated or rewritten.  When a source JSON
contains several text events, it is split into the same number of non-empty
segments using Japanese length ratios and Chinese punctuation as deterministic
cut hints.  Joining the segments must preserve every non-whitespace Chinese
character from the Wiki field.

An entire logical group is rejected if any source cannot be proven.  Existing
Chinese output is never overwritten.  Japanese JSON remains the structural
template, then canonical TXT, an import report, and provenance are generated
transactionally.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import generate_story_index as pipeline  # noqa: E402
import import_exedra_official_tw as common  # noqa: E402

JP_ROOT = ROOT / "magiraexedra-source-master/Scenarios_full"
CN_ROOT = ROOT / "magiraexedra-translate-data-master/Scenarios_full"
MANIFEST = JP_ROOT / "exedra_manifest.json"
AUDIT_PATH = ROOT / "artifacts/exedra_wiki_voice_import_report.json"
CHARACTER_AUDIT_PATH = (
    ROOT / "artifacts/exedra_wiki_voice_character_match_report.json"
)
HUMAN_IMPORT_AUDIT = ROOT / "artifacts/exedra_human_text_import_report.json"
WIKI_API = "https://exedra.wiki/w/api.php"
WIKI_BASE = "https://exedra.wiki/wiki/"
USER_AGENT = "MagiReader-exedra-wiki-voice-import/1.0"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
VOICE_TITLE_SUFFIX = "/Voice/zh"
SAFE_AUDIO_RE = re.compile(r"^[A-Za-z0-9_]+\.ogg$")
UNRESOLVED_MARKUP_RE = re.compile(r"\{\{|\}\}|\[\[|\]\]|<[^>]*>")
STRONG_PUNCTUATION = frozenset("。！？!?；;…")
WEAK_PUNCTUATION = frozenset("，,、：:")

# Exedra ships these two reaction groups with byte-distinct source identities
# but the same ordered voice content.  Wiki publishes the audio names under
# cv_100805 only.  Runtime validation below re-proves the complete relationship
# from the checked-in JP manifest/JSON before this alias can ever be used.
STRICT_REACTION_GROUP_ALIASES = {
    "cv_100803": "cv_100805",
}


@dataclass(frozen=True)
class WikiVoice:
    page_title: str
    page_url: str
    page_sha256: str
    file_name: str
    text_jp: str
    text_cn: str


@dataclass(frozen=True)
class SelectedVoice:
    record: WikiVoice
    equivalent_pages: tuple[str, ...]


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_japanese(value: str) -> str:
    """Normalize presentation width and remove only Unicode whitespace."""

    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
    )


def chinese_signature(value: str) -> str:
    """Identity used only to prove that segmentation preserved source text."""

    return "".join(character for character in value if not character.isspace())


def clean_field(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = html.unescape(value).strip()
    if UNRESOLVED_MARKUP_RE.search(value):
        raise RuntimeError(f"Wiki 语音字段含未解析标记：{value[:120]!r}")
    return value


def iter_balanced_templates(raw: str, template_name: str) -> Iterable[str]:
    marker = "{{" + template_name
    cursor = 0
    while True:
        start = raw.find(marker, cursor)
        if start < 0:
            return
        depth = 0
        index = start
        while index < len(raw) - 1:
            pair = raw[index : index + 2]
            if pair == "{{":
                depth += 1
                index += 2
                continue
            if pair == "}}":
                depth -= 1
                index += 2
                if depth == 0:
                    yield raw[start:index]
                    cursor = index
                    break
                continue
            index += 1
        else:
            raise RuntimeError(f"Wiki 模板未闭合：{template_name}")


def parse_template_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, buffer
        if current:
            if current in fields:
                raise RuntimeError(f"Wiki 模板字段重复：{current}")
            fields[current] = "\n".join(buffer).strip()
        current = ""
        buffer = []

    for raw_line in block.splitlines()[1:]:
        if raw_line.strip() == "}}":
            break
        match = re.match(
            r"^\s*\|\s*([A-Za-z0-9_]+)\s*=\s*(.*)$",
            raw_line,
        )
        if match:
            flush()
            current = match.group(1)
            buffer = [match.group(2)]
        elif current:
            buffer.append(raw_line)
    flush()
    return fields


def page_url(title: str) -> str:
    return WIKI_BASE + urllib.parse.quote(
        title.replace(" ", "_"),
        safe="/:_-",
    )


def parse_voice_page(title: str, raw: str) -> list[WikiVoice]:
    if not title.endswith(VOICE_TITLE_SUFFIX):
        raise RuntimeError(f"不是中文语音页：{title}")
    digest = sha256_bytes(raw.encode("utf-8"))
    result: list[WikiVoice] = []
    for block in iter_balanced_templates(raw, "Character Voice Row"):
        fields = parse_template_fields(block)
        if not all(fields.get(name) for name in ("file_name", "text_jp", "text_en")):
            continue
        try:
            file_name = clean_field(fields["file_name"])
            text_jp = clean_field(fields["text_jp"])
            text_cn = clean_field(fields["text_en"])
        except RuntimeError:
            # Translation-extension fuzzy or unresolved markup is not a trusted
            # human source.  Reject this row without discarding valid rows on
            # the same /Voice/zh page.
            continue
        if not SAFE_AUDIO_RE.fullmatch(file_name):
            raise RuntimeError(f"Wiki 语音文件名非法：{title}: {file_name!r}")
        if not normalize_japanese(text_jp) or not chinese_signature(text_cn):
            raise RuntimeError(f"Wiki 语音正文为空：{title}: {file_name}")
        result.append(
            WikiVoice(
                page_title=title,
                page_url=page_url(title),
                page_sha256=digest,
                file_name=file_name,
                text_jp=text_jp,
                text_cn=text_cn,
            )
        )
    return result


def request_json(params: dict[str, str], *, attempts: int = 4) -> dict[str, Any]:
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Wiki API 响应超过 8 MiB")
            parsed = json.loads(payload.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError("Wiki API 响应顶层不是对象")
            if isinstance(parsed.get("error"), dict):
                raise RuntimeError(
                    "Wiki API 错误："
                    + str(parsed["error"].get("code") or "unknown")
                )
            return parsed
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"Wiki API 请求失败：{type(last_error).__name__}: {last_error}")


def discover_voice_titles() -> list[str]:
    continuation: dict[str, str] = {}
    titles: list[str] = []
    while True:
        payload = request_json(
            {
                "action": "query",
                "list": "allpages",
                "apnamespace": "0",
                "aplimit": "max",
                "format": "json",
                "formatversion": "2",
                **continuation,
            }
        )
        query = payload.get("query")
        pages = query.get("allpages") if isinstance(query, dict) else None
        if not isinstance(pages, list):
            raise RuntimeError("Wiki allpages 响应缺少 query.allpages")
        for item in pages:
            title = item.get("title") if isinstance(item, dict) else None
            if isinstance(title, str) and title.endswith(VOICE_TITLE_SUFFIX):
                titles.append(title)
        next_value = payload.get("continue")
        if not isinstance(next_value, dict):
            break
        continuation = {
            str(key): str(value)
            for key, value in next_value.items()
        }
    unique = sorted(set(titles), key=str.casefold)
    if len(unique) < 1:
        raise RuntimeError("Exedra Wiki 未发现任何 /Voice/zh 页面")
    return unique


def fetch_voice_page(title: str) -> tuple[str, str]:
    payload = request_json(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
        }
    )
    parsed = payload.get("parse")
    raw = parsed.get("wikitext") if isinstance(parsed, dict) else None
    if not isinstance(raw, str):
        raise RuntimeError(f"Wiki 页面缺少 wikitext：{title}")
    return title, raw


def fetch_all_voice_records(
    workers: int,
) -> tuple[list[WikiVoice], list[dict[str, Any]]]:
    titles = discover_voice_titles()
    pages: dict[str, str] = {}
    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(workers, 12))
    ) as executor:
        futures = {
            executor.submit(fetch_voice_page, title): title
            for title in titles
        }
        for future in concurrent.futures.as_completed(futures):
            title = futures[future]
            try:
                returned_title, raw = future.result()
                pages[returned_title] = raw
            except Exception as exc:
                errors.append(f"{title}: {exc}")
    if errors:
        raise RuntimeError(
            f"{len(errors)} 个 Wiki 中文语音页抓取失败：{errors[:5]}"
        )
    records: list[WikiVoice] = []
    page_inventory: list[dict[str, Any]] = []
    for title in titles:
        raw = pages[title]
        parsed = parse_voice_page(title, raw)
        records.extend(parsed)
        page_inventory.append(
            {
                "title": title,
                "url": page_url(title),
                "sha256": sha256_bytes(raw.encode("utf-8")),
                "rowCount": len(parsed),
            }
        )
    return records, page_inventory


def index_records(records: Iterable[WikiVoice]) -> dict[str, list[WikiVoice]]:
    result: dict[str, list[WikiVoice]] = {}
    for record in records:
        result.setdefault(record.file_name, []).append(record)
    return result


def select_voice(
    record_index: dict[str, list[WikiVoice]],
    source_basename: str,
    japanese_events: list[str],
) -> SelectedVoice:
    expected_name = source_basename + ".ogg"
    named = record_index.get(expected_name, [])
    if not named:
        raise FileNotFoundError(f"Wiki 缺少精确 file_name：{expected_name}")
    expected_japanese = normalize_japanese("".join(japanese_events))
    exact = [
        record
        for record in named
        if normalize_japanese(record.text_jp) == expected_japanese
    ]
    if not exact:
        raise RuntimeError(
            f"Wiki text_jp 与 JP JSON 拼接正文不同：{expected_name}"
        )
    by_chinese: dict[str, list[WikiVoice]] = {}
    for record in exact:
        by_chinese.setdefault(chinese_signature(record.text_cn), []).append(record)
    if len(by_chinese) != 1:
        raise RuntimeError(
            f"Wiki 精确候选的中文正文冲突：{expected_name}: "
            f"{sorted(record.page_title for record in exact)}"
        )
    equivalent = next(iter(by_chinese.values()))
    selected = sorted(equivalent, key=lambda item: item.page_title.casefold())[0]
    return SelectedVoice(
        record=selected,
        equivalent_pages=tuple(
            sorted({item.page_title for item in equivalent}, key=str.casefold)
        ),
    )


def validate_strict_reaction_group_alias(
    group: dict[str, Any],
    alias_group: dict[str, Any],
) -> dict[str, str]:
    """Prove an explicit source-id alias from the immutable JP inputs.

    The returned mapping is target source basename -> Wiki/alias basename.
    Any structural, order, event, or Japanese difference rejects the complete
    alias.  No Chinese text participates in this identity proof.
    """

    group_key = str(group.get("groupKey") or "")
    alias_key = str(alias_group.get("groupKey") or "")
    expected_alias = STRICT_REACTION_GROUP_ALIASES.get(group_key)
    if (
        group.get("category") != "6_Reaction"
        or alias_group.get("category") != "6_Reaction"
        or not group_key
        or alias_key != expected_alias
    ):
        raise RuntimeError(
            f"{group_key}: 未声明的 Wiki 语音来源别名：{alias_key}"
        )
    target_sources = group.get("sources")
    alias_sources = alias_group.get("sources")
    if (
        not isinstance(target_sources, list)
        or not isinstance(alias_sources, list)
        or len(target_sources) != len(alias_sources)
        or not target_sources
    ):
        raise RuntimeError(
            f"{group_key}: 来源别名 Section 数量不同："
            f"{len(target_sources or [])}/{len(alias_sources or [])}"
        )

    mapping: dict[str, str] = {}
    target_prefix = group_key + "_"
    alias_prefix = alias_key + "_"
    for target_raw, alias_raw in zip(target_sources, alias_sources):
        target_name = PurePosixPath(str(target_raw)).name
        alias_name = PurePosixPath(str(alias_raw)).name
        if not target_name.startswith(target_prefix):
            raise RuntimeError(
                f"{group_key}: 目标来源不属于该组：{target_name}"
            )
        expected_name = alias_prefix + target_name[len(target_prefix) :]
        if alias_name != expected_name:
            raise RuntimeError(
                f"{group_key}: 来源别名后缀或顺序不同："
                f"{target_name}/{alias_name}"
            )

        target_rows = common.extract_rows(group_jp_json(group, str(target_raw)))
        alias_rows = common.extract_rows(
            group_jp_json(alias_group, str(alias_raw))
        )
        if len(target_rows) != len(alias_rows):
            raise RuntimeError(
                f"{group_key}: 来源别名事件数量不同："
                f"{target_name}/{alias_name}: "
                f"{len(target_rows)}/{len(alias_rows)}"
            )
        for position, (target_row, alias_row) in enumerate(
            zip(target_rows, alias_rows),
            1,
        ):
            target_identity = (
                target_row.get("sheet_index"),
                target_row.get("row_number"),
                target_row.get("action"),
                target_row.get("speaker"),
                normalize_japanese(str(target_row.get("text") or "")),
            )
            alias_identity = (
                alias_row.get("sheet_index"),
                alias_row.get("row_number"),
                alias_row.get("action"),
                alias_row.get("speaker"),
                normalize_japanese(str(alias_row.get("text") or "")),
            )
            if target_identity != alias_identity:
                raise RuntimeError(
                    f"{group_key}: 来源别名第 {position} 个事件不同："
                    f"{target_name}/{alias_name}"
                )
        mapping[Path(target_name).stem] = Path(alias_name).stem
    return mapping


def _candidate_score(position: int, target: float, previous_character: str) -> float:
    if previous_character in STRONG_PUNCTUATION:
        punctuation_penalty = 0.0
    elif previous_character in WEAK_PUNCTUATION:
        punctuation_penalty = 1.5
    else:
        punctuation_penalty = 5.0
    return abs(position - target) + punctuation_penalty


def split_chinese_by_japanese(
    text_cn: str,
    japanese_events: list[str],
) -> list[str]:
    """Split one Wiki translation without changing or dropping its characters."""

    if not japanese_events or any(not normalize_japanese(value) for value in japanese_events):
        raise RuntimeError("JP JSON 包含空文本事件")
    source = text_cn.strip()
    if not chinese_signature(source):
        raise RuntimeError("Wiki 中文正文为空")
    if len(japanese_events) == 1:
        return [source]

    # At least one non-whitespace source character is required per event.
    meaningful_positions = [
        index + 1
        for index, character in enumerate(source)
        if not character.isspace()
    ]
    if len(meaningful_positions) < len(japanese_events):
        raise RuntimeError(
            f"Wiki 中文正文过短，无法分成 {len(japanese_events)} 个非空事件"
        )

    weights = [len(normalize_japanese(value)) for value in japanese_events]
    total_weight = sum(weights)
    cuts: list[int] = []
    previous = 0
    for boundary in range(1, len(japanese_events)):
        remaining_events = len(japanese_events) - boundary
        target = len(source) * sum(weights[:boundary]) / total_weight
        candidates = []
        for position in range(previous + 1, len(source)):
            left = source[previous:position]
            right = source[position:]
            if not left.strip():
                continue
            if len(chinese_signature(right)) < remaining_events:
                continue
            candidates.append(position)
        if not candidates:
            raise RuntimeError("无法生成全部非空中文事件分段")
        cut = min(
            candidates,
            key=lambda position: (
                _candidate_score(position, target, source[position - 1]),
                abs(position - target),
                position,
            ),
        )
        cuts.append(cut)
        previous = cut

    segments: list[str] = []
    start = 0
    for cut in [*cuts, len(source)]:
        segment = source[start:cut].strip()
        if not segment:
            raise RuntimeError("中文分段产生空事件")
        segments.append(segment)
        start = cut
    if len(segments) != len(japanese_events):
        raise RuntimeError("中文分段数量错误")
    if chinese_signature("".join(segments)) != chinese_signature(source):
        raise RuntimeError("中文分段未保留 Wiki 全部非空白字符")
    return segments


def group_jp_json(group: dict[str, Any], raw_source: str) -> Path:
    safe = PurePosixPath(raw_source)
    path = JP_ROOT / str(group["outputDir"]) / safe.name
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"JP JSON 不存在：{path}")
    return path


def import_group(
    group: dict[str, Any],
    record_index: dict[str, list[WikiVoice]],
    reaction_groups: dict[str, dict[str, Any]],
    *,
    write: bool,
) -> dict[str, Any]:
    category = str(group.get("category") or "")
    group_key = str(group.get("groupKey") or "")
    if category != "6_Reaction" or not group_key:
        raise RuntimeError(f"不是有效 Exedra 语音组：{group_key!r}")
    output_dir = CN_ROOT / category / group_key
    cn_path = output_dir / f"{group_key}_cn.txt"
    if cn_path.exists():
        sidecar_path = output_dir / f"{group_key}_cn.provenance.json"
        if sidecar_path.is_file() and not sidecar_path.is_symlink():
            sidecar = common.load_json(sidecar_path)
            if (
                isinstance(sidecar, dict)
                and sidecar.get("provenance")
                == "exedra_wiki_voice_human"
            ):
                if (
                    sidecar.get("sourceIdentity")
                    != str(group.get("id") or "")
                    or sidecar.get("machineTranslation") is not False
                ):
                    raise RuntimeError(
                        f"{group_key}: 现有 Wiki 语音来源侧车身份无效"
                    )
                return {
                    "groupKey": group_key,
                    "status": "existing_wiki",
                    "provenance": "exedra_wiki_voice_human",
                }
        return {"groupKey": group_key, "status": "existing_local"}

    source_aliases: dict[str, str] = {}
    alias_group_key = STRICT_REACTION_GROUP_ALIASES.get(group_key)
    if alias_group_key:
        alias_group = reaction_groups.get(alias_group_key)
        if not alias_group:
            raise RuntimeError(
                f"{group_key}: manifest 缺少来源别名组：{alias_group_key}"
            )
        source_aliases = validate_strict_reaction_group_alias(
            group,
            alias_group,
        )

    source_paths = group.get("sources")
    if not isinstance(source_paths, list):
        raise RuntimeError(f"{group_key}: manifest sources 无效")
    jp_path = JP_ROOT / str(group.get("textFile") or "")
    sections = common.parse_txt(jp_path)
    if len(sections) != len(source_paths):
        raise RuntimeError(
            f"{group_key}: manifest/Section 数量不同："
            f"{len(source_paths)}/{len(sections)}"
        )

    planned: list[
        tuple[common.Section, str, Path, list[str], SelectedVoice]
    ] = []
    rejected: list[dict[str, Any]] = []
    for section, raw_source_value in zip(sections, source_paths):
        raw_source = str(raw_source_value)
        source_name = PurePosixPath(raw_source).name
        if source_name != section.source:
            raise RuntimeError(
                f"{group_key}: manifest/Section 来源不同："
                f"{source_name}/{section.source}"
            )
        jp_json = group_jp_json(group, raw_source)
        rows = common.extract_rows(jp_json)
        japanese_events = [str(row.get("text") or "") for row in rows]
        try:
            source_basename = Path(source_name).stem
            try:
                selected = select_voice(
                    record_index,
                    source_basename,
                    japanese_events,
                )
            except FileNotFoundError:
                alias_basename = source_aliases.get(source_basename)
                if not alias_basename:
                    raise
                selected = select_voice(
                    record_index,
                    alias_basename,
                    japanese_events,
                )
            texts = split_chinese_by_japanese(
                selected.record.text_cn,
                japanese_events,
            )
            planned.append((section, raw_source, jp_json, texts, selected))
        except Exception as exc:
            rejected.append(
                {
                    "source": source_name,
                    "expectedFileName": Path(source_name).stem + ".ogg",
                    "eventCount": len(japanese_events),
                    "reason": str(exc),
                }
            )
    if rejected:
        return {
            "groupKey": group_key,
            "status": "rejected",
            "reasons": rejected,
        }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{group_key}-wiki-voice-",
        dir=output_dir.parent,
    ) as temporary:
        stage = Path(temporary)
        translated_sections: list[list[str]] = []
        json_meta: list[dict[str, Any]] = []
        for section, raw_source, jp_json, texts, selected in planned:
            destination = stage / section.source
            cn_json_sha = common.apply_translated_texts(
                jp_json,
                texts,
                destination,
            )
            # Re-open every generated JSON before it is eligible for commit.
            common.load_json(destination)
            translated_sections.append(texts)
            record = selected.record
            json_meta.append(
                {
                    "source": section.source,
                    "manifestSourcePath": raw_source,
                    "jpSha256": pipeline._sha256_file(jp_json),
                    "cnSha256": cn_json_sha,
                    "eventCount": len(texts),
                    "provenance": "exedra_wiki_voice_human",
                    "wikiFileName": record.file_name,
                    "targetFileName": Path(section.source).stem + ".ogg",
                    "sourceIdentityAlias": (
                        {
                            "targetGroupKey": group_key,
                            "wikiSourceGroupKey": alias_group_key,
                            "validation": (
                                "manifest_suffix_sheet_row_action_speaker_"
                                "and_per_event_japanese_exact"
                            ),
                        }
                        if alias_group_key
                        else None
                    ),
                    "wikiPage": record.page_title,
                    "wikiUrl": record.page_url,
                    "wikiPageSha256": record.page_sha256,
                    "equivalentWikiPages": list(selected.equivalent_pages),
                    "textJpNormalizedSha256": sha256_bytes(
                        normalize_japanese(record.text_jp).encode("utf-8")
                    ),
                    "textCnSha256": sha256_bytes(
                        record.text_cn.encode("utf-8")
                    ),
                    "segmentation": {
                        "method": "jp_length_ratio_with_cn_punctuation",
                        "preservedNonWhitespaceCharacters": True,
                    },
                }
            )

        staged_cn = stage / f"{group_key}_cn.txt"
        staged_cn.write_text(
            common.render_cn(sections, translated_sections),
            encoding="utf-8",
        )
        report = common.build_report(
            category,
            group_key,
            jp_path,
            staged_cn,
            "exedra-wiki-all-voice-zh",
            json_meta,
        )
        report["provenance"] = "exedra_wiki_voice_human"
        report["sourcePolicy"] = {
            "pageSuffix": VOICE_TITLE_SUFFIX,
            "fileNameMatch": "exact",
            "sourceIdentityAlias": (
                {
                    "targetGroupKey": group_key,
                    "wikiSourceGroupKey": alias_group_key,
                    "validation": (
                        "manifest_suffix_sheet_row_action_speaker_"
                        "and_per_event_japanese_exact"
                    ),
                }
                if alias_group_key
                else None
            ),
            "japaneseMatch": "normalized_exact_joined_text_events",
            "usesFuzzyMatching": False,
            "allowsReordering": False,
            "translationPerformed": False,
        }
        (stage / f"{group_key}{pipeline.EXEDRA_IMPORT_REPORT_SUFFIX}").write_bytes(
            json_bytes(report)
        )
        sidecar = {
            "version": 1,
            "sourceIdentity": str(group.get("id") or ""),
            "provenance": "exedra_wiki_voice_human",
            "machineTranslation": False,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "jpSha256": pipeline._sha256_utf8_text_file(jp_path),
            "cnSha256": pipeline._sha256_utf8_text_file(staged_cn),
            "sourceJson": json_meta,
        }
        (stage / f"{group_key}_cn.provenance.json").write_bytes(
            json_bytes(sidecar)
        )
        pipeline._validate_exedra_cn_import_report(
            group=pipeline.OrganizedExedraGroup(
                manifest_id=str(group.get("id") or ""),
                raw_category=category,
                category=pipeline.EXEDRA_CATEGORY_MAP[category],
                group_key=group_key,
                output_dir=Path(category, group_key),
                text_file=Path(str(group.get("textFile") or "")),
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
        "provenance": "exedra_wiki_voice_human",
        "sourceIdentityAlias": alias_group_key,
    }


def evaluate_rejected_character_sources(
    records: list[WikiVoice],
) -> dict[str, Any]:
    """Report only whole-source unique JP matches; never mutates character data."""

    if not HUMAN_IMPORT_AUDIT.is_file():
        return {
            "schemaVersion": 1,
            "status": "source-audit-missing",
            "matches": [],
        }
    audit = common.load_json(HUMAN_IMPORT_AUDIT)
    results = audit.get("results") if isinstance(audit, dict) else None
    rejected_groups = [
        item
        for item in results or []
        if isinstance(item, dict) and item.get("status") == "rejected"
    ]
    manifest = common.load_json(MANIFEST)
    by_key = {
        str(group.get("groupKey")): group
        for group in manifest.get("groups", [])
        if isinstance(group, dict) and group.get("category") == "3_Character"
    }
    by_japanese: dict[str, list[WikiVoice]] = {}
    for record in records:
        by_japanese.setdefault(
            normalize_japanese(record.text_jp),
            [],
        ).append(record)

    source_results: list[dict[str, Any]] = []
    for rejected in rejected_groups:
        key = str(rejected.get("groupKey") or "")
        group = by_key.get(key)
        if not group:
            continue
        reason_sources = {
            str(reason.get("source"))
            for reason in rejected.get("reasons", [])
            if isinstance(reason, dict)
        }
        for raw_source in group.get("sources", []):
            source_name = PurePosixPath(str(raw_source)).name
            if source_name not in reason_sources:
                continue
            jp_json = group_jp_json(group, str(raw_source))
            rows = common.extract_rows(jp_json)
            japanese_events = [str(row.get("text") or "") for row in rows]
            candidates = by_japanese.get(
                normalize_japanese("".join(japanese_events)),
                [],
            )
            chinese_values = {
                chinese_signature(item.text_cn)
                for item in candidates
            }
            exact_unique = bool(candidates) and len(chinese_values) == 1
            source_results.append(
                {
                    "groupKey": key,
                    "source": source_name,
                    "eventCount": len(japanese_events),
                    "exactWholeSourceMatch": exact_unique,
                    "candidateCount": len(candidates),
                    "candidatePages": sorted(
                        {item.page_title for item in candidates},
                        key=str.casefold,
                    ),
                    "safeForAutomaticUse": exact_unique,
                }
            )
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "policy": "whole_source_normalized_exact_japanese_only",
        "usesFuzzyMatching": False,
        "rejectedGroupCount": len(rejected_groups),
        "sourceCount": len(source_results),
        "safeMatchCount": sum(
            item["safeForAutomaticUse"] for item in source_results
        ),
        "matches": source_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--only-group", action="append", default=[])
    parser.add_argument("--wiki-workers", type=int, default=8)
    args = parser.parse_args()

    records, page_inventory = fetch_all_voice_records(args.wiki_workers)
    record_index = index_records(records)
    manifest = common.load_json(MANIFEST)
    selected_groups = {
        value
        for value in args.only_group
        if value
    }
    groups = [
        group
        for group in manifest.get("groups", [])
        if isinstance(group, dict)
        and group.get("category") == "6_Reaction"
        and (
            not selected_groups
            or str(group.get("groupKey")) in selected_groups
        )
    ]
    reaction_groups = {
        str(group.get("groupKey")): group
        for group in manifest.get("groups", [])
        if isinstance(group, dict)
        and group.get("category") == "6_Reaction"
        and group.get("groupKey")
    }

    results: list[dict[str, Any]] = []
    for group in groups:
        try:
            results.append(
                import_group(
                    group,
                    record_index,
                    reaction_groups,
                    write=args.write,
                )
            )
        except Exception as exc:
            results.append(
                {
                    "groupKey": str(group.get("groupKey") or ""),
                    "status": "failed",
                    "error": str(exc),
                }
            )

    counts: dict[str, int] = {}
    for item in results:
        status = str(item["status"])
        counts[status] = counts.get(status, 0) + 1
    audit = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "writeMode": args.write,
        "policy": {
            "sourcePages": "all_main_namespace_pages_ending_/Voice/zh",
            "fileNameMatch": "exact",
            "sourceIdentityAliases": STRICT_REACTION_GROUP_ALIASES,
            "sourceIdentityAliasValidation": (
                "manifest_suffix_sheet_row_action_speaker_"
                "and_per_event_japanese_exact"
            ),
            "japaneseMatch": "NFKC_then_remove_whitespace_exact",
            "groupAtomic": True,
            "overwriteExistingChinese": False,
            "usesFuzzyMatching": False,
            "translationPerformed": False,
        },
        "machineTranslation": False,
        "wiki": {
            "api": WIKI_API,
            "pageCount": len(page_inventory),
            "rowCount": len(records),
            "uniqueFileNameCount": len(record_index),
            "pages": page_inventory,
        },
        "counts": counts,
        "results": results,
    }
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_bytes(json_bytes(audit))

    character_audit = evaluate_rejected_character_sources(records)
    CHARACTER_AUDIT_PATH.write_bytes(json_bytes(character_audit))

    print(
        json.dumps(
            {
                "wikiPages": len(page_inventory),
                "wikiRows": len(records),
                "reactionGroups": len(groups),
                "counts": counts,
                "characterExactSafeMatches": character_audit.get(
                    "safeMatchCount",
                    0,
                ),
            },
            ensure_ascii=False,
        )
    )
    return 2 if counts.get("failed", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
