#!/usr/bin/env python3
"""Import a reviewed Exedra Wiki translation without guessing its alignment.

The importer deliberately separates two concepts:

* the Wiki's original events, which are preserved one-per-line in the CN TXT;
* the reader-visible blocks, where adjacent lines from the same speaker are
  merged by ``website/lib/story-parser.ts``.

Validation is performed section-by-section on the second representation.  No
LCS, fuzzy matching, line insertion, or reordering is used.  A mismatch refuses
publication and is emitted as a JSON report on stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_API_URL = "https://exedra.wiki/w/api.php"
DEFAULT_JP_ROOT = (
    SCRIPT_DIR / "magiraexedra-source-master" / "Scenarios_full"
)
DEFAULT_CN_ROOT = (
    SCRIPT_DIR / "magiraexedra-translate-data-master" / "Scenarios_full"
)
DEFAULT_DICTIONARY = SCRIPT_DIR / "website" / "app" / "config" / "dictionary.ts"
DEFAULT_CATEGORY = "3_Character"
DEFAULT_GROUP_KEY = "character_rena"
DEFAULT_WIKI_PAGE = "Rena Minami/Story/Chinese"
REPORT_SUFFIX = "_cn.import-report.json"
REPORT_SCHEMA_VERSION = 1
USER_AGENT = "MagiReader-Exedra-Wiki-Importer/1.0"

SAFE_COMPONENT_RE = re.compile(r"^(?!.*\.$)[A-Za-z0-9_][A-Za-z0-9_.-]*$")
SECTION_RE = re.compile(
    r"^---\s*\[Section\s+(\d+)]\s*"
    r"\(Source:\s*([^\\/\r\n]+\.json)\)\s*---$",
    re.IGNORECASE,
)
EPISODE_RE = re.compile(
    r"^===\s*(?:Episode\s*|第\s*)(\d+)(?:\s*[话話])?\s*===\s*$",
    re.IGNORECASE,
)
COLOR_DIALOGUE_RE = re.compile(
    r"\{\{\s*Color\s+Dialogue\s*\|([^{}]*?)\}\}",
    re.IGNORECASE,
)
FULL_BOLD_RE = re.compile(r"^'''([\s\S]*?)'''$")
TS_PAIR_RE = re.compile(
    r'"((?:\\.|[^"\\])*)"\s*:\s*"((?:\\.|[^"\\])*)"'
)
SPEAKER_SPLIT_RE = re.compile(r"\s*[＆&]\s*")
WHITESPACE_RE = re.compile(r"\s+")
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
IGNORED_TEMPLATE_NAMES = frozenset(
    {
        "audio",
        "backgroundimage",
        "backgroundportrait",
        "bgmaudio",
        "charactertabs",
        "pagelanguage:zh",
    }
)

NARRATION_SPEAKERS = frozenset(
    {"Narration", "ナレーション", "旁白", "旁白（无角色）"}
)

# The site dictionary supplies established MagiReco names.  These additions
# cover Rena's story-specific roles that intentionally have no global entry.
# They are exact aliases, not inferred from event position.
BUILTIN_GROUP_SPEAKER_ALIASES: dict[str, dict[str, str]] = {
    "character_rena": {
        "たかね": "高岭",
        "たかねのメッセージ": "高岭的信息",
        "ソプラの歌": "索普拉的歌",
        "観客たち": "观众们",
    }
}


class ImporterError(RuntimeError):
    """Raised when input cannot be parsed or publication would be unsafe."""


def _is_link_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError as error:
        raise ImporterError(
            f"Cannot inspect path reparse state: {path}: {error}"
        ) from error


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_no_link_ancestors(path: Path, *, label: str) -> None:
    current = _absolute_lexical(path)
    while True:
        if _is_link_like(current):
            raise ImporterError(
                f"{label} contains a symbolic-link or junction ancestor: {current}"
            )
        if current.parent == current:
            break
        current = current.parent


def _plain_tree_entries(
    root: Path,
) -> list[tuple[Path, Path, bool]]:
    root = _absolute_lexical(root)
    _assert_no_link_ancestors(root, label="Tree root")
    if not root.is_dir():
        raise ImporterError(f"Tree root is not a directory: {root}")
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise ImporterError(f"Cannot resolve tree root {root}: {error}") from error

    result: list[tuple[Path, Path, bool]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                entries = sorted(scan, key=lambda item: item.name.casefold())
        except OSError as error:
            raise ImporterError(f"Cannot enumerate {current}: {error}") from error

        directories: list[Path] = []
        for entry in entries:
            path = Path(entry.path)
            if _is_link_like(path):
                raise ImporterError(
                    f"Tree contains a symbolic link or junction: {path}"
                )
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except ValueError as error:
                raise ImporterError(f"Tree entry escapes root: {path}") from error
            except OSError as error:
                raise ImporterError(
                    f"Cannot inspect tree entry {path}: {error}"
                ) from error
            if not is_directory and not is_file:
                raise ImporterError(f"Tree contains a special entry: {path}")
            relative = path.relative_to(root)
            result.append((path, relative, is_directory))
            if is_directory:
                directories.append(path)
        stack.extend(reversed(directories))
    return result


@dataclass(frozen=True)
class StoryEvent:
    speaker: str
    text: str
    kind: str
    source_line: int
    canonical_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class StorySection:
    number: int
    source_name: str
    header: str
    events: tuple[StoryEvent, ...]


@dataclass(frozen=True)
class WikiEpisode:
    number: int
    heading: str
    events: tuple[StoryEvent, ...]


@dataclass(frozen=True)
class WikiRevision:
    page: str
    revision_id: int | None
    timestamp: str | None
    author: str | None
    sha1: str | None
    content: str
    source: str


@dataclass(frozen=True)
class ReaderBlock:
    speaker: str
    kind: str
    first_event: int
    last_event: int
    event_count: int


@dataclass(frozen=True)
class ValidationBundle:
    report: dict[str, Any]
    rendered_text: str
    sections: tuple[StorySection, ...]
    episodes: tuple[WikiEpisode, ...]

    @property
    def passed(self) -> bool:
        return bool(self.report.get("validation", {}).get("passed"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_speaker(value: str) -> str:
    """Mirror the reader's removal of whitespace from speaker labels."""

    return WHITESPACE_RE.sub("", value.strip())


def escape_output_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\n")


def _decode_ts_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError as error:
        raise ImporterError(f"Invalid quoted string in dictionary.ts: {value}") from error


def load_name_translation_map(path: Path) -> tuple[dict[str, str], str]:
    """Read only NAME_TRANSLATE_MAP from the existing TypeScript dictionary."""

    try:
        raw = path.read_bytes()
        source = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise ImporterError(f"Cannot read speaker dictionary {path}: {error}") from error

    marker = "export const NAME_TRANSLATE_MAP"
    start = source.find(marker)
    if start < 0:
        raise ImporterError(f"NAME_TRANSLATE_MAP is missing from {path}")
    end = source.find("\n};", start)
    if end < 0:
        raise ImporterError(f"NAME_TRANSLATE_MAP is not terminated in {path}")

    result: dict[str, str] = {}
    for match in TS_PAIR_RE.finditer(source[start:end]):
        key = normalize_speaker(_decode_ts_string(match.group(1)))
        value = normalize_speaker(_decode_ts_string(match.group(2)))
        if key:
            result[key] = value
    if not result:
        raise ImporterError(f"No speaker aliases were parsed from {path}")
    return result, sha256_bytes(raw)


def load_extra_speaker_map(path: Path | None) -> tuple[dict[str, str], str | None]:
    if path is None:
        return {}, None
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImporterError(f"Cannot read extra speaker map {path}: {error}") from error
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in value.items()
    ):
        raise ImporterError("Extra speaker map must be a JSON object of string pairs")
    return (
        {
            normalize_speaker(key): normalize_speaker(item)
            for key, item in value.items()
            if normalize_speaker(key)
        },
        sha256_bytes(raw),
    )


def build_speaker_map(
    dictionary: dict[str, str],
    group_key: str,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    result = {
        normalize_speaker(key): normalize_speaker(value)
        for key, value in dictionary.items()
    }
    result.update(
        {
            normalize_speaker(key): normalize_speaker(value)
            for key, value in BUILTIN_GROUP_SPEAKER_ALIASES.get(
                group_key, {}
            ).items()
        }
    )
    if extra:
        result.update(
            {
                normalize_speaker(key): normalize_speaker(value)
                for key, value in extra.items()
            }
        )
    return result


def parse_section_text(raw: str) -> tuple[StorySection, ...]:
    """Parse the organizer's JP TXT without changing any event boundary."""

    sections: list[StorySection] = []
    current_number: int | None = None
    current_source = ""
    current_header = ""
    current_events: list[StoryEvent] = []

    def flush() -> None:
        nonlocal current_number, current_source, current_header, current_events
        if current_number is None:
            return
        sections.append(
            StorySection(
                number=current_number,
                source_name=current_source,
                header=current_header,
                events=tuple(current_events),
            )
        )
        current_number = None
        current_source = ""
        current_header = ""
        current_events = []

    normalized = raw.removeprefix("\ufeff").replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    for line_number, raw_line in enumerate(normalized.split("\n"), start=1):
        line = raw_line.strip()
        if not line:
            continue
        section_match = SECTION_RE.fullmatch(line)
        if section_match:
            flush()
            number = int(section_match.group(1))
            expected = len(sections) + 1
            if number != expected:
                raise ImporterError(
                    f"JP Section sequence is not contiguous at line {line_number}: "
                    f"expected {expected}, found {number}"
                )
            current_number = number
            current_source = section_match.group(2)
            current_header = line
            continue
        if line.startswith("---"):
            raise ImporterError(
                f"Malformed JP Section header at line {line_number}: {line}"
            )
        if current_number is None:
            raise ImporterError(
                f"JP content appears before the first Section at line {line_number}"
            )

        separator = line.find(":")
        fullwidth_separator = line.find("：")
        if separator < 0 or (
            fullwidth_separator >= 0 and fullwidth_separator < separator
        ):
            separator = fullwidth_separator
        if separator > 0:
            speaker = normalize_speaker(line[:separator])
            text = line[separator + 1 :].strip()
        else:
            speaker = "旁白"
            text = line
        if not speaker or not text:
            raise ImporterError(f"Invalid JP event at line {line_number}: {line}")
        kind = "narration" if speaker in NARRATION_SPEAKERS else "dialogue"
        current_events.append(
            StoryEvent(
                speaker=speaker,
                text=text,
                kind=kind,
                source_line=line_number,
            )
        )

    flush()
    if not sections:
        raise ImporterError("JP TXT contains no Section headers")
    return tuple(sections)


def _replace_wiki_links(value: str) -> str:
    link_re = re.compile(r"\[\[([^\[\]]+?)]]")

    def replace(match: re.Match[str]) -> str:
        body = match.group(1)
        return body.rsplit("|", 1)[-1]

    previous = ""
    while previous != value:
        previous = value
        value = link_re.sub(replace, value)
    return value


def clean_wiki_text(value: str) -> str:
    """Convert supported inline MediaWiki markup to reader-visible text."""

    text = value.strip()
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r"<br\s*/?>", r"\\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"<rp\b[^>]*>[\s\S]*?</rp>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<ruby\b[^>]*>([\s\S]*?)<rt\b[^>]*>[\s\S]*?</rt>"
        r"([\s\S]*?)</ruby>",
        r"\1\2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</?(?:span|nowiki|ruby|rp)\b[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<ref\b[^>]*>[\s\S]*?</ref>|<ref\b[^>]*/>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = _replace_wiki_links(text)
    text = re.sub(
        r"\[(?:https?://\S+)(?:\s+([^\]]+))?]",
        lambda match: match.group(1) or "",
        text,
    )
    text = text.replace("'''''", "").replace("'''", "").replace("''", "")
    text = html.unescape(text).strip()
    if "{{" in text or "}}" in text:
        raise ImporterError(f"Unsupported template remains in translated text: {value}")
    if re.search(r"</?[A-Za-z][^>]*>", text):
        raise ImporterError(f"Unsupported HTML remains in translated text: {value}")
    if "\n" in text or "\r" in text:
        text = escape_output_text(text)
    if not text:
        raise ImporterError("A Wiki story event became empty after markup cleanup")
    return text


def _strip_simple_templates(value: str) -> str:
    previous = ""
    while previous != value:
        previous = value
        value = TEMPLATE_RE.sub("", value)
    return value.strip()


def _only_ignored_templates(value: str) -> bool:
    templates = list(TEMPLATE_RE.finditer(value))
    if not templates or _strip_simple_templates(value):
        return False
    for match in templates:
        body = match.group(0)[2:-2].strip()
        name = body.split("|", 1)[0].strip().casefold().replace(" ", "")
        if name not in IGNORED_TEMPLATE_NAMES:
            return False
    return True


def _known_non_story_line(line: str) -> bool:
    if not line:
        return True
    if line.startswith("<!--") and line.endswith("-->"):
        return True
    if re.fullmatch(r"={2,6}[\s\S]*?={2,6}", line):
        return True
    if _only_ignored_templates(line):
        return True
    if re.fullmatch(
        r"(?:(?:记忆|記憶|心之器).{0,80}(?:解锁|解鎖|解放)"
        r"|Unlocked\b.{0,160})",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if line.startswith("[[Category:"):
        return True
    return False


def _parse_dialogue_line(line: str, line_number: int) -> StoryEvent | None:
    matches = list(COLOR_DIALOGUE_RE.finditer(line))
    if not matches:
        return None

    prefix = line[: matches[0].start()]
    if prefix.strip() and not _only_ignored_templates(prefix):
        raise ImporterError(
            f"Unexpected text before Color Dialogue at Wiki line {line_number}"
        )

    speakers: list[str] = []
    canonical_hints: list[str] = []
    for index, match in enumerate(matches):
        if index:
            between = line[matches[index - 1].end() : match.start()]
            if not re.fullmatch(r"\s*[＆&]\s*", between):
                raise ImporterError(
                    f"Unsupported multi-speaker separator at Wiki line {line_number}"
                )
        arguments = [item.strip() for item in match.group(1).split("|")]
        speaker = normalize_speaker(arguments[0] if arguments else "")
        if not speaker:
            raise ImporterError(
                f"Color Dialogue has no speaker at Wiki line {line_number}"
            )
        speakers.append(speaker)
        canonical_hints.append(arguments[1] if len(arguments) > 1 else "")

    tail = line[matches[-1].end() :]
    text_match = re.match(r"^\s*[:：]\s*([\s\S]+?)\s*$", tail)
    if not text_match:
        raise ImporterError(
            f"Color Dialogue has no translated text at Wiki line {line_number}"
        )
    return StoryEvent(
        speaker="＆".join(speakers),
        text=clean_wiki_text(text_match.group(1)),
        kind="dialogue",
        source_line=line_number,
        canonical_hints=tuple(canonical_hints),
    )


def parse_wikitext(raw: str) -> tuple[WikiEpisode, ...]:
    """Parse explicit Color Dialogue lines and contiguous bold narration."""

    episodes: list[WikiEpisode] = []
    current_number: int | None = None
    current_heading = ""
    current_events: list[StoryEvent] = []
    narration_lines: list[tuple[int, str]] = []

    def flush_narration() -> None:
        nonlocal narration_lines
        if not narration_lines:
            return
        current_events.append(
            StoryEvent(
                speaker="旁白",
                text=r"\n".join(
                    clean_wiki_text(value) for _, value in narration_lines
                ),
                kind="narration",
                source_line=narration_lines[0][0],
            )
        )
        narration_lines = []

    def flush_episode() -> None:
        nonlocal current_number, current_heading, current_events
        flush_narration()
        if current_number is None:
            return
        episodes.append(
            WikiEpisode(
                number=current_number,
                heading=current_heading,
                events=tuple(current_events),
            )
        )
        current_number = None
        current_heading = ""
        current_events = []

    normalized = raw.removeprefix("\ufeff").replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    for line_number, raw_line in enumerate(normalized.split("\n"), start=1):
        line = raw_line.strip()
        episode_match = EPISODE_RE.fullmatch(line)
        if episode_match:
            flush_episode()
            current_number = int(episode_match.group(1))
            current_heading = line
            continue
        if re.match(
            r"^===.*(?:Episode|第\s*\d+).*(?:===)$",
            line,
            flags=re.IGNORECASE,
        ):
            raise ImporterError(
                f"Malformed Wiki Episode heading at line {line_number}: {line}"
            )

        if current_number is None:
            continue

        bold_match = FULL_BOLD_RE.fullmatch(line)
        if bold_match:
            narration_lines.append((line_number, bold_match.group(1)))
            continue

        flush_narration()
        event = _parse_dialogue_line(line, line_number)
        if event is not None:
            current_events.append(event)
            continue
        if not _known_non_story_line(line):
            raise ImporterError(
                f"Unrecognized non-empty Wiki line {line_number}: {line}"
            )

    flush_episode()
    if not episodes:
        raise ImporterError("Wiki page contains no Episode headings")

    expected = episodes[0].number
    for episode in episodes:
        if episode.number != expected:
            raise ImporterError(
                "Wiki Episode sequence is not contiguous: "
                f"expected {expected}, found {episode.number}"
            )
        if not episode.events:
            raise ImporterError(f"Wiki Episode {episode.number} has no story events")
        expected += 1
    return tuple(episodes)


def merge_reader_blocks(events: Sequence[StoryEvent]) -> tuple[ReaderBlock, ...]:
    """Apply the exact adjacent-identical-speaker boundary used by the reader."""

    blocks: list[ReaderBlock] = []
    for index, event in enumerate(events, start=1):
        speaker = normalize_speaker(event.speaker)
        if blocks and blocks[-1].speaker == speaker:
            previous = blocks[-1]
            kind = previous.kind if previous.kind == event.kind else "mixed"
            blocks[-1] = ReaderBlock(
                speaker=speaker,
                kind=kind,
                first_event=previous.first_event,
                last_event=index,
                event_count=previous.event_count + 1,
            )
        else:
            blocks.append(
                ReaderBlock(
                    speaker=speaker,
                    kind=event.kind,
                    first_event=index,
                    last_event=index,
                    event_count=1,
                )
            )
    return tuple(blocks)


def _speaker_parts(value: str) -> tuple[str, ...]:
    normalized = normalize_speaker(value)
    if normalized in NARRATION_SPEAKERS:
        return ("@narration",)
    return tuple(
        part for part in SPEAKER_SPLIT_RE.split(normalized) if part
    )


def jp_speaker_identity(
    speaker: str, speaker_map: dict[str, str]
) -> tuple[tuple[str, ...] | None, tuple[str, ...]]:
    parts = _speaker_parts(speaker)
    if parts == ("@narration",):
        return parts, ()
    translated: list[str] = []
    missing: list[str] = []
    for part in parts:
        mapped = speaker_map.get(part)
        if mapped is None:
            missing.append(part)
        else:
            translated.append(normalize_speaker(mapped))
    if missing:
        return None, tuple(missing)
    return tuple(translated), ()


def cn_speaker_identity(speaker: str) -> tuple[str, ...]:
    return _speaker_parts(speaker)


def sequence_hash(items: Iterable[tuple[str, tuple[str, ...] | None]]) -> str:
    serializable = [
        {"kind": kind, "speaker": list(speaker) if speaker is not None else None}
        for kind, speaker in items
    ]
    return sha256_text(
        json.dumps(serializable, ensure_ascii=False, separators=(",", ":"))
    )


def render_translation(
    sections: Sequence[StorySection], episodes: Sequence[WikiEpisode]
) -> str:
    if len(sections) != len(episodes):
        raise ImporterError("Cannot render translation with unmatched Section count")
    rendered_sections: list[str] = []
    for section, episode in zip(sections, episodes):
        lines = [section.header]
        for event in episode.events:
            lines.append(
                f"{normalize_speaker(event.speaker)}: "
                f"{escape_output_text(event.text)}"
            )
        rendered_sections.append("\n".join(lines))
    return "\n\n".join(rendered_sections).rstrip() + "\n"


def _source_episode_number(source_name: str) -> int | None:
    match = re.search(r"_(\d+)\.json$", source_name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def validate_translation(
    *,
    sections: Sequence[StorySection],
    episodes: Sequence[WikiEpisode],
    speaker_map: dict[str, str],
    wiki_revision: WikiRevision,
    jp_path: Path | None,
    dictionary_path: Path | None,
    dictionary_sha256: str | None,
    group_key: str,
    category: str,
    target_path: Path,
    jp_content_sha256: str | None = None,
    extra_map_path: Path | None = None,
    extra_map_sha256: str | None = None,
    generated_at: str | None = None,
) -> ValidationBundle:
    """Strictly compare Section-local reader blocks at the same indices."""

    mismatches: list[dict[str, Any]] = []
    section_reports: list[dict[str, Any]] = []
    unmapped: set[str] = set()

    if len(sections) != len(episodes):
        mismatches.append(
            {
                "type": "section-count",
                "jp": len(sections),
                "cn": len(episodes),
            }
        )

    compared = min(len(sections), len(episodes))
    for index in range(compared):
        section = sections[index]
        episode = episodes[index]
        source_episode = _source_episode_number(section.source_name)
        if source_episode is not None and source_episode != episode.number:
            mismatches.append(
                {
                    "type": "source-episode-anchor",
                    "section": section.number,
                    "source": section.source_name,
                    "sourceEpisode": source_episode,
                    "wikiEpisode": episode.number,
                }
            )

        jp_blocks = merge_reader_blocks(section.events)
        cn_blocks = merge_reader_blocks(episode.events)
        jp_signatures: list[tuple[str, tuple[str, ...] | None]] = []
        cn_signatures: list[tuple[str, tuple[str, ...]]] = []
        for block in jp_blocks:
            identity, missing = jp_speaker_identity(block.speaker, speaker_map)
            unmapped.update(missing)
            jp_signatures.append((block.kind, identity))
        for block in cn_blocks:
            cn_signatures.append(
                (block.kind, cn_speaker_identity(block.speaker))
            )

        if any(block.kind == "mixed" for block in (*jp_blocks, *cn_blocks)):
            mismatches.append(
                {
                    "type": "mixed-narration-dialogue-run",
                    "section": section.number,
                }
            )

        if len(jp_blocks) != len(cn_blocks):
            mismatches.append(
                {
                    "type": "reader-block-count",
                    "section": section.number,
                    "wikiEpisode": episode.number,
                    "jp": len(jp_blocks),
                    "cn": len(cn_blocks),
                }
            )
        else:
            for block_index, (jp_signature, cn_signature) in enumerate(
                zip(jp_signatures, cn_signatures), start=1
            ):
                if jp_signature != cn_signature:
                    mismatches.append(
                        {
                            "type": "speaker-or-kind",
                            "section": section.number,
                            "wikiEpisode": episode.number,
                            "block": block_index,
                            "jpKind": jp_signature[0],
                            "cnKind": cn_signature[0],
                            "jpSpeaker": (
                                list(jp_signature[1])
                                if jp_signature[1] is not None
                                else None
                            ),
                            "cnSpeaker": list(cn_signature[1]),
                        }
                    )

        section_reports.append(
            {
                "section": section.number,
                "wikiEpisode": episode.number,
                "source": section.source_name,
                "rawEvents": {
                    "jp": len(section.events),
                    "cn": len(episode.events),
                    "difference": len(section.events) - len(episode.events),
                },
                "readerNormalizedBlocks": {
                    "jp": len(jp_blocks),
                    "cn": len(cn_blocks),
                    "matches": (
                        len(jp_blocks) == len(cn_blocks)
                        and jp_signatures == cn_signatures
                    ),
                },
                "adjacentEventsMerged": {
                    "reason": (
                        "reader merges adjacent events with the exact same "
                        "whitespace-normalized speaker inside one Section"
                    ),
                    "jp": len(section.events) - len(jp_blocks),
                    "cn": len(episode.events) - len(cn_blocks),
                    "jpMergeRuns": sum(
                        block.event_count > 1 for block in jp_blocks
                    ),
                    "cnMergeRuns": sum(
                        block.event_count > 1 for block in cn_blocks
                    ),
                },
                "speakerSequenceSha256": {
                    "jp": sequence_hash(jp_signatures),
                    "cn": sequence_hash(cn_signatures),
                },
            }
        )

    if unmapped:
        mismatches.append(
            {
                "type": "unmapped-jp-speaker",
                "speakers": sorted(unmapped),
            }
        )

    jp_raw_total = sum(len(section.events) for section in sections)
    cn_raw_total = sum(len(episode.events) for episode in episodes)
    jp_block_total = sum(
        len(merge_reader_blocks(section.events)) for section in sections
    )
    cn_block_total = sum(
        len(merge_reader_blocks(episode.events)) for episode in episodes
    )
    rendered = (
        render_translation(sections, episodes)
        if len(sections) == len(episodes)
        else ""
    )
    passed = not mismatches
    report: dict[str, Any] = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "status": "validated" if passed else "refused",
        "generatedAt": generated_at or utc_now(),
        "group": {
            "category": category,
            "groupKey": group_key,
        },
        "wiki": {
            "page": wiki_revision.page,
            "revisionId": wiki_revision.revision_id,
            "timestamp": wiki_revision.timestamp,
            "author": wiki_revision.author,
            "sha1": wiki_revision.sha1,
            "contentSha256": sha256_text(wiki_revision.content),
            "source": wiki_revision.source,
        },
        "jp": {
            "path": str(jp_path.resolve()) if jp_path is not None else None,
            "contentSha256": jp_content_sha256,
            "sectionCount": len(sections),
            "rawEventCount": jp_raw_total,
            "readerNormalizedBlockCount": jp_block_total,
        },
        "cn": {
            "target": str(target_path.resolve()),
            "sectionCount": len(episodes),
            "rawEventCount": cn_raw_total,
            "readerNormalizedBlockCount": cn_block_total,
            "renderedSha256": sha256_text(rendered) if rendered else None,
        },
        "speakerMapping": {
            "dictionaryPath": (
                str(dictionary_path.resolve())
                if dictionary_path is not None
                else None
            ),
            "dictionarySha256": dictionary_sha256,
            "builtInAliasGroup": (
                group_key
                if group_key in BUILTIN_GROUP_SPEAKER_ALIASES
                else None
            ),
            "builtInAliases": BUILTIN_GROUP_SPEAKER_ALIASES.get(
                group_key, {}
            ),
            "extraMapPath": (
                str(extra_map_path.resolve())
                if extra_map_path is not None
                else None
            ),
            "extraMapSha256": extra_map_sha256,
            "unmappedJapaneseSpeakers": sorted(unmapped),
        },
        "validation": {
            "passed": passed,
            "policy": (
                "same Section index, same reader-normalized block count, "
                "same exact mapped speaker and narration/dialogue kind at "
                "every block index"
            ),
            "preservesWikiRawEvents": True,
            "usesLcs": False,
            "usesFuzzyMatching": False,
            "allowsReordering": False,
            "mismatchCount": len(mismatches),
        },
        "sections": section_reports,
        "mismatches": mismatches,
    }
    return ValidationBundle(
        report=report,
        rendered_text=rendered,
        sections=tuple(sections),
        episodes=tuple(episodes),
    )


def fetch_wiki_revision(
    page: str, api_url: str = DEFAULT_API_URL, timeout: float = 30.0
) -> WikiRevision:
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "ids|timestamp|user|sha1|content",
            "rvslots": "main",
            "titles": page,
            "format": "json",
            "formatversion": "2",
        }
    )
    request = urllib.request.Request(
        f"{api_url}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise ImporterError(f"Public MediaWiki API request failed: {error}") from error

    pages = payload.get("query", {}).get("pages", [])
    if not isinstance(pages, list) or len(pages) != 1:
        raise ImporterError("MediaWiki API returned an unexpected page list")
    page_data = pages[0]
    if page_data.get("missing"):
        raise ImporterError(f"Wiki page does not exist: {page}")
    revisions = page_data.get("revisions", [])
    if not isinstance(revisions, list) or not revisions:
        raise ImporterError(f"Wiki page has no readable revision: {page}")
    revision = revisions[0]
    content = revision.get("slots", {}).get("main", {}).get("content")
    if not isinstance(content, str):
        raise ImporterError(f"Wiki revision has no main-slot content: {page}")
    return WikiRevision(
        page=str(page_data.get("title") or page),
        revision_id=(
            int(revision["revid"]) if revision.get("revid") is not None else None
        ),
        timestamp=revision.get("timestamp"),
        author=revision.get("user"),
        sha1=revision.get("sha1"),
        content=content,
        source=api_url,
    )


def revision_from_fixture(path: Path, page: str) -> WikiRevision:
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise ImporterError(f"Cannot read Wiki fixture {path}: {error}") from error
    return WikiRevision(
        page=page,
        revision_id=None,
        timestamp=None,
        author=None,
        sha1=None,
        content=content,
        source=str(path.resolve()),
    )


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _assert_safe_publish_paths(output_root: Path, jp_path: Path) -> None:
    if output_root.name.casefold() != "scenarios_full":
        raise ImporterError(
            "For safety, the publish root directory must be named Scenarios_full"
        )
    output_root = _absolute_lexical(output_root)
    jp_path = _absolute_lexical(jp_path)
    _assert_no_link_ancestors(output_root, label="CN output root")
    _assert_no_link_ancestors(jp_path, label="JP input")
    output = output_root.resolve()
    source = jp_path.resolve()
    if output == source or _is_relative_to(output, source) or _is_relative_to(
        source, output
    ):
        raise ImporterError(
            "CN output root must not overlap the organizer JP input path"
        )
    if output_root.exists() and not output_root.is_dir():
        raise ImporterError(f"CN output root is not a directory: {output_root}")


def _snapshot_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path, relative, is_directory in _plain_tree_entries(root):
        if not is_directory:
            snapshot[relative.as_posix()] = sha256_bytes(path.read_bytes())
    return snapshot


def _unique_sibling(base: Path) -> Path:
    if not base.exists():
        return base
    for index in range(1, 10_000):
        candidate = base.with_name(f"{base.name}-{index}")
        if not candidate.exists():
            return candidate
    raise ImporterError(f"Could not allocate a unique backup path near {base}")


def _validate_stage(
    *,
    stage: Path,
    prior_snapshot: dict[str, str],
    target_relative: Path,
    report_relative: Path,
    expected_text: str,
    expected_report: dict[str, Any],
    expected_sections: Sequence[StorySection],
    expected_episodes: Sequence[WikiEpisode],
) -> None:
    staged_snapshot = _snapshot_tree(stage)
    mutable = {
        target_relative.as_posix(),
        report_relative.as_posix(),
    }
    for relative, digest in prior_snapshot.items():
        if relative in mutable:
            continue
        if staged_snapshot.get(relative) != digest:
            raise ImporterError(
                f"Staging changed an unrelated existing file: {relative}"
            )
    expected_files = set(prior_snapshot) | mutable
    if set(staged_snapshot) != expected_files:
        extra = sorted(set(staged_snapshot) - expected_files)
        missing = sorted(expected_files - set(staged_snapshot))
        raise ImporterError(
            f"Staging file ownership mismatch; extra={extra}, missing={missing}"
        )

    target = stage / target_relative
    if target.read_text("utf-8") != expected_text:
        raise ImporterError("Staged CN TXT bytes do not match the validated candidate")
    parsed = parse_section_text(target.read_text("utf-8"))
    if [section.header for section in parsed] != [
        section.header for section in expected_sections
    ]:
        raise ImporterError("Staged CN TXT does not preserve JP Section headers")
    if [len(section.events) for section in parsed] != [
        len(episode.events) for episode in expected_episodes
    ]:
        raise ImporterError("Staged CN TXT event counts changed during serialization")

    report_value = json.loads((stage / report_relative).read_text("utf-8"))
    if report_value != expected_report:
        raise ImporterError("Staged import report differs from validation report")


def publish_translation(
    *,
    bundle: ValidationBundle,
    output_root: Path,
    jp_path: Path,
    category: str,
    group_key: str,
) -> tuple[Path, Path | None, Path]:
    """Publish a fully validated staged tree and retain the prior tree."""

    if not bundle.passed:
        raise ImporterError("Refusing to publish a failed validation bundle")
    if not SAFE_COMPONENT_RE.fullmatch(category) or not SAFE_COMPONENT_RE.fullmatch(
        group_key
    ):
        raise ImporterError("Category and group key must be safe path components")
    _assert_safe_publish_paths(output_root, jp_path)

    output_root = _absolute_lexical(output_root)
    expected_target = (
        output_root / category / group_key / f"{group_key}_cn.txt"
    ).resolve()
    report_group = bundle.report.get("group", {})
    report_target = bundle.report.get("cn", {}).get("target")
    if (
        report_group.get("category") != category
        or report_group.get("groupKey") != group_key
        or not isinstance(report_target, str)
        or Path(report_target).resolve() != expected_target
    ):
        raise ImporterError(
            "Validated report scope does not match the requested publish target"
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    prior_snapshot = _snapshot_tree(output_root)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.staging-",
            dir=output_root.parent,
        )
    )
    target_relative = Path(category) / group_key / f"{group_key}_cn.txt"
    report_relative = (
        Path(category) / group_key / f"{group_key}{REPORT_SUFFIX}"
    )
    report_bytes = (
        json.dumps(bundle.report, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    backup: Path | None = None
    try:
        if output_root.exists():
            shutil.copytree(
                output_root,
                stage,
                dirs_exist_ok=True,
                copy_function=shutil.copy2,
                symlinks=True,
            )
        target = stage / target_relative
        report_target = stage / report_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bundle.rendered_text.encode("utf-8"))
        report_target.write_bytes(report_bytes)
        _validate_stage(
            stage=stage,
            prior_snapshot=prior_snapshot,
            target_relative=target_relative,
            report_relative=report_relative,
            expected_text=bundle.rendered_text,
            expected_report=bundle.report,
            expected_sections=bundle.sections,
            expected_episodes=bundle.episodes,
        )

        if output_root.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = _unique_sibling(
                output_root.with_name(f"{output_root.name}.backup-{timestamp}")
            )
            output_root.rename(backup)
        try:
            stage.rename(output_root)
        except Exception:
            if backup is not None and backup.exists() and not output_root.exists():
                backup.rename(output_root)
            raise

        try:
            _validate_stage(
                stage=output_root,
                prior_snapshot=prior_snapshot,
                target_relative=target_relative,
                report_relative=report_relative,
                expected_text=bundle.rendered_text,
                expected_report=bundle.report,
                expected_sections=bundle.sections,
                expected_episodes=bundle.episodes,
            )
        except Exception:
            failed = _unique_sibling(
                output_root.with_name(f"{output_root.name}.failed")
            )
            output_root.rename(failed)
            if backup is not None and backup.exists():
                backup.rename(output_root)
            raise
        return output_root / target_relative, backup, output_root / report_relative
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _minimal_error_report(error: Exception) -> dict[str, Any]:
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "status": "refused",
        "generatedAt": utc_now(),
        "validation": {
            "passed": False,
            "usesLcs": False,
            "usesFuzzyMatching": False,
            "allowsReordering": False,
        },
        "mismatches": [{"type": "input-or-operation-error", "message": str(error)}],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Strictly import an Exedra Wiki translation. The default mode is "
            "read-only dry-run; only --publish writes files."
        )
    )
    parser.add_argument("--category", default=DEFAULT_CATEGORY)
    parser.add_argument("--group-key", default=DEFAULT_GROUP_KEY)
    parser.add_argument("--wiki-page", default=DEFAULT_WIKI_PAGE)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--jp-root",
        type=Path,
        default=DEFAULT_JP_ROOT,
        help="Organizer Scenarios_full root.",
    )
    parser.add_argument(
        "--jp-file",
        type=Path,
        help="Explicit organizer JP TXT; overrides --jp-root.",
    )
    parser.add_argument(
        "--cn-root",
        type=Path,
        default=DEFAULT_CN_ROOT,
        help="Translation Scenarios_full root.",
    )
    parser.add_argument(
        "--dictionary",
        type=Path,
        default=DEFAULT_DICTIONARY,
    )
    parser.add_argument(
        "--speaker-map",
        type=Path,
        help="Optional exact Japanese-to-Chinese alias JSON object.",
    )
    parser.add_argument(
        "--wiki-fixture",
        type=Path,
        help="Offline wikitext fixture; disables the API request.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish through a validated staging tree and retain a backup.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    jp_path = (
        args.jp_file
        if args.jp_file is not None
        else args.jp_root
        / args.category
        / args.group_key
        / f"{args.group_key}_jp.txt"
    )
    target_path = (
        args.cn_root
        / args.category
        / args.group_key
        / f"{args.group_key}_cn.txt"
    )

    try:
        if not SAFE_COMPONENT_RE.fullmatch(
            args.category
        ) or not SAFE_COMPONENT_RE.fullmatch(args.group_key):
            raise ImporterError("Category and group key must be safe path components")
        jp_path = _absolute_lexical(jp_path)
        _assert_no_link_ancestors(jp_path, label="Organizer JP TXT")
        try:
            jp_raw = jp_path.read_text("utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            raise ImporterError(f"Cannot read organizer JP TXT {jp_path}: {error}") from error

        dictionary, dictionary_sha = load_name_translation_map(args.dictionary)
        extra, extra_sha = load_extra_speaker_map(args.speaker_map)
        speaker_map = build_speaker_map(dictionary, args.group_key, extra)
        revision = (
            revision_from_fixture(args.wiki_fixture, args.wiki_page)
            if args.wiki_fixture is not None
            else fetch_wiki_revision(args.wiki_page, args.api_url, args.timeout)
        )
        sections = parse_section_text(jp_raw)
        episodes = parse_wikitext(revision.content)
        bundle = validate_translation(
            sections=sections,
            episodes=episodes,
            speaker_map=speaker_map,
            wiki_revision=revision,
            jp_path=jp_path,
            dictionary_path=args.dictionary,
            dictionary_sha256=dictionary_sha,
            group_key=args.group_key,
            category=args.category,
            target_path=target_path,
            jp_content_sha256=sha256_text(jp_raw),
            extra_map_path=args.speaker_map,
            extra_map_sha256=extra_sha,
        )
        result = dict(bundle.report)
        result["mode"] = "publish" if args.publish else "dry-run"

        if not bundle.passed:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2
        if args.publish:
            published, backup, report_path = publish_translation(
                bundle=bundle,
                output_root=args.cn_root,
                jp_path=jp_path,
                category=args.category,
                group_key=args.group_key,
            )
            result["publication"] = {
                "published": str(published.resolve()),
                "report": str(report_path.resolve()),
                "backup": str(backup.resolve()) if backup is not None else None,
            }
        else:
            result["publication"] = {
                "published": None,
                "report": "stdout-only",
                "backup": None,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ImporterError, OSError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(_minimal_error_report(error), ensure_ascii=False, indent=2)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
