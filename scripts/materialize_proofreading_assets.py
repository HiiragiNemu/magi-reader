#!/usr/bin/env python3
"""Turn one reviewed TXT into playable scenario JSON and canonical TXT.

The reviewed TXT is an input document, not the source of scenario structure.
For every ``Source: *.json`` header this tool loads the corresponding Chinese
JSON from the target branch, or the Japanese JSON when Chinese JSON does not
yet exist.  It changes only player-visible text/name cells, regenerates the TXT
from those JSON documents, proves the round trip, and then commits all outputs
as one rollback-capable filesystem transaction.

When ``--base-ref`` is provided, structural templates are read with
``git show <base-ref>:<path>``.  This prevents a pull request from smuggling
unreviewed non-text JSON changes into the generated files.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
MAGIRECO_CN_REL = PurePosixPath(
    "magireco-translate-data-master/Scenarios_full"
)
MAGIRECO_JP_REL = PurePosixPath("magireco-source-master/Scenarios_full")
MAGIRECO_VOICE_CN_REL = PurePosixPath(
    "magireco-voice-translate-data-master/Scenarios_full/general_voice"
)
MAGIRECO_VOICE_JSON_REL = PurePosixPath(
    "magireco-voice-source-master/Scenarios_full/general_voice"
)
GENERAL_VOICE_MANIFEST_NAME = "general_voice_manifest.json"
EXEDRA_CN_REL = PurePosixPath(
    "magiraexedra-translate-data-master/Scenarios_full"
)
EXEDRA_JP_REL = PurePosixPath("magiraexedra-source-master/Scenarios_full")
EXEDRA_MANIFEST_REL = EXEDRA_JP_REL / "exedra_manifest.json"

HEADER_RE = re.compile(
    r"^---\s*\[Section\s+(\d+)"
    r"(?:\s+-\s+Branch\s+(\d+))?\]\s*"
    r"\(Source:\s*([^()\r\n]+\.json)\s*\)\s*---$",
    re.I,
)
CHOICE_RE = re.compile(
    r"^(?:选项|選択肢|Choice)\s*[:：]\s*"
    r"【(.*)】\s*(?:→|->)\s*(group_\d+)\s*$",
    re.I,
)
INTERVIEW_LINE_RE = re.compile(r"^―+\s*取材记录\s*―+$")
INTERVIEW_MARKERS = ("取材記録", "采访记录", "取材记录", "取材録")
EXEDRA_TEXT_ACTIONS = {"talk", "narration", "charactertalk", "onlytext"}
NARRATION_SPEAKERS = {"旁白", "Narration", "ナレーション", ""}
COLOR_TAGS = {
    "red": "Red",
    "blue": "Blue",
    "yellow": "Yellow",
    "black": "Black",
}
CONTROL_RE = re.compile(
    r"\[(?!text(?:Red|Blue|Yellow|Black):|br\])[^][\r\n]*\]",
    re.I,
)


class MaterializeError(RuntimeError):
    """Fail-closed materialization error."""


@dataclass(frozen=True)
class ReviewedLine:
    kind: str
    speaker: str
    text: str
    choice_group: str = ""
    command: str = ""
    position: str = ""
    scene0_kind: str = ""


@dataclass(frozen=True)
class ReviewedSection:
    number: int
    branch: int | None
    source: str
    lines: tuple[ReviewedLine, ...]

    @property
    def signature(self) -> tuple[int, int | None, str]:
        return (self.number, self.branch, self.source)


@dataclass(frozen=True)
class JsonTemplate:
    document: dict[str, Any]
    source_path: str
    source_sha256: str
    formatting_source: bytes


def normalize_text(value: str) -> str:
    return (
        value.removeprefix("\ufeff")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\0", "")
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(normalize_text(value).encode("utf-8"))


def safe_repo_path(value: str | PurePosixPath) -> PurePosixPath:
    raw = str(value)
    if not raw or "\\" in raw or "\0" in raw:
        raise MaterializeError(f"仓库路径不安全：{raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MaterializeError(f"仓库路径不安全：{raw!r}")
    return path


def safe_source_name(value: str) -> str:
    if (
        PurePosixPath(value).name != value
        or "\\" in value
        or "\0" in value
        or not value.casefold().endswith(".json")
    ):
        raise MaterializeError(f"Source 文件名不安全：{value!r}")
    return value


class BlobReader:
    """Read immutable templates from a git ref or the local filesystem."""

    def __init__(self, repo_root: Path, base_ref: str | None) -> None:
        self.repo_root = repo_root.resolve()
        self.base_ref = base_ref

    def read(self, relative: str | PurePosixPath) -> bytes | None:
        path = safe_repo_path(relative)
        if self.base_ref:
            completed = subprocess.run(
                [
                    "git",
                    "show",
                    f"{self.base_ref}:{path.as_posix()}",
                ],
                cwd=self.repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if completed.returncode == 0:
                return completed.stdout
            return None
        local = self.repo_root.joinpath(*path.parts)
        if not local.is_file() or local.is_symlink():
            return None
        return local.read_bytes()


def load_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterializeError(f"JSON 模板无效：{label}: {exc}") from exc
    if not isinstance(value, dict):
        raise MaterializeError(f"JSON 顶层不是对象：{label}")
    return value


def json_bytes_like(document: Mapping[str, Any], template: bytes) -> bytes:
    """Serialize without mechanically reformatting the entire source file."""

    decoded = template.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in decoded else "\n"
    indentation = re.search(r"\r?\n([ \t]+)\"", decoded)
    body = decoded.rstrip("\r\n")
    if "\n" not in body and "\r" not in body:
        rendered = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    else:
        indent: int | str = indentation.group(1) if indentation else 2
        rendered = json.dumps(document, ensure_ascii=False, indent=indent)
    if newline != "\n":
        rendered = rendered.replace("\n", newline)
    suffix = newline if decoded.endswith(("\n", "\r")) else ""
    prefix = b"\xef\xbb\xbf" if template.startswith(b"\xef\xbb\xbf") else b""
    return prefix + (rendered + suffix).encode("utf-8")


def update_general_voice_manifests(
    *,
    reader: BlobReader,
    model_id: str,
    source_json_rel: PurePosixPath,
    cn_json_rel: PurePosixPath,
    cn_json_payload: bytes,
    cn_txt_rel: PurePosixPath,
    cn_txt_payload: bytes,
) -> dict[str, bytes]:
    """Update the two byte-identical integrity manifests transactionally."""

    source_manifest_rel = (
        MAGIRECO_VOICE_JSON_REL / GENERAL_VOICE_MANIFEST_NAME
    )
    cn_manifest_rel = (
        MAGIRECO_VOICE_CN_REL / GENERAL_VOICE_MANIFEST_NAME
    )
    source_raw = reader.read(source_manifest_rel)
    cn_raw = reader.read(cn_manifest_rel)
    if source_raw is None or cn_raw is None:
        raise MaterializeError("魔法纪录语音缺少来源/中文完整性清单")
    if source_raw != cn_raw:
        raise MaterializeError("魔法纪录语音来源/中文完整性清单不一致")

    manifest = load_json_bytes(source_raw, str(source_manifest_rel))
    models = manifest.get("models")
    model_count = manifest.get("modelCount")
    if (
        manifest.get("version") != 1
        or not isinstance(models, list)
        or not isinstance(model_count, int)
        or model_count != len(models)
        or model_count < 1
    ):
        raise MaterializeError("魔法纪录语音完整性清单版本或数量无效")
    matches = [
        item
        for item in models
        if isinstance(item, dict) and str(item.get("id") or "") == model_id
    ]
    if len(matches) != 1:
        raise MaterializeError(
            f"魔法纪录语音完整性清单模型不唯一：{model_id}"
        )
    model = matches[0]
    base_source_json = reader.read(source_json_rel)
    base_cn_json = reader.read(cn_json_rel)
    base_txt = reader.read(cn_txt_rel)
    if base_source_json is None or base_cn_json is None or base_txt is None:
        raise MaterializeError(
            f"目标分支缺少魔法纪录语音 JSON/TXT：{model_id}"
        )
    if (
        model.get("jsonSha256") != sha256_bytes(base_source_json)
        or model.get("sourceJsonSha256", model.get("jsonSha256"))
        != sha256_bytes(base_source_json)
        or model.get("cnJsonSha256") != sha256_bytes(base_cn_json)
        or model.get("txtSha256") != sha256_bytes(base_txt)
    ):
        raise MaterializeError(
            f"目标分支魔法纪录语音清单哈希失配：{model_id}"
        )

    output_document = load_json_bytes(cn_json_payload, str(cn_json_rel))
    translated, total, raw_references, without_voice = (
        _general_voice_translation_stats(output_document)
    )
    model["cnJsonSha256"] = sha256_bytes(cn_json_payload)
    model["txtSha256"] = sha256_bytes(cn_txt_payload)
    model["voiceGroups"] = total
    model["translatedVoiceGroups"] = translated
    model["untranslatedVoiceGroups"] = total - translated
    model["rawVoiceReferences"] = raw_references
    model["groupsWithoutVoice"] = without_voice
    model["translationPercent"] = round(translated * 100 / total) if total else 0
    encoded = json_bytes_like(manifest, source_raw)
    return {
        source_manifest_rel.as_posix(): encoded,
        cn_manifest_rel.as_posix(): encoded,
    }


def general_voice_model_paths_for_txt(
    *,
    reader: BlobReader,
    relative_txt: PurePosixPath,
) -> tuple[str, PurePosixPath, PurePosixPath]:
    source_manifest_rel = MAGIRECO_VOICE_JSON_REL / GENERAL_VOICE_MANIFEST_NAME
    cn_manifest_rel = MAGIRECO_VOICE_CN_REL / GENERAL_VOICE_MANIFEST_NAME
    source_raw = reader.read(source_manifest_rel)
    cn_raw = reader.read(cn_manifest_rel)
    if source_raw is None or cn_raw is None or source_raw != cn_raw:
        raise MaterializeError("魔法纪录语音来源/中文完整性清单缺失或不一致")
    manifest = load_json_bytes(source_raw, str(source_manifest_rel))
    models = manifest.get("models")
    try:
        txt_relative = relative_txt.relative_to(MAGIRECO_VOICE_CN_REL).as_posix()
    except ValueError as exc:
        raise MaterializeError("魔法纪录语音 TXT 不在中文语音根目录") from exc
    matches = [
        model
        for model in models if isinstance(models, list) and isinstance(model, dict)
        if model.get("cnTxtRelativePath") == txt_relative
    ] if isinstance(models, list) else []
    if len(matches) != 1:
        raise MaterializeError("魔法纪录语音 TXT 未唯一匹配完整性清单")
    model = matches[0]
    model_id = str(model.get("id") or "")
    if not re.fullmatch(r"\d{6}", model_id):
        raise MaterializeError("魔法纪录语音模型 ID 无效")
    source_relative = safe_repo_path(str(model.get("sourceRelativePath") or ""))
    cn_relative = safe_repo_path(str(model.get("cnJsonRelativePath") or ""))
    source_json_rel = MAGIRECO_VOICE_JSON_REL / source_relative
    cn_json_rel = MAGIRECO_VOICE_CN_REL / cn_relative
    if (
        source_json_rel.name != f"{model_id}.json"
        or cn_json_rel.name != f"{model_id}_cn.json"
        or source_relative.parent != cn_relative.parent
        or relative_txt.parent != cn_json_rel.parent
    ):
        raise MaterializeError("魔法纪录语音来源/中文 JSON/TXT 层级不一致")
    return model_id, source_json_rel, cn_json_rel


def split_dialogue(value: str) -> tuple[str, str]:
    indices = [
        index
        for index in (value.find(":"), value.find("："))
        if index > 0
    ]
    if not indices:
        return "旁白", value.strip()
    index = min(indices)
    return value[:index].strip(), value[index + 1 :].strip()


def parse_reviewed_text(value: str, label: str) -> tuple[ReviewedSection, ...]:
    sections: list[ReviewedSection] = []
    current: tuple[int, int | None, str] | None = None
    body: list[ReviewedLine] = []

    def flush() -> None:
        nonlocal current, body
        if current is not None:
            if not body:
                raise MaterializeError(f"Section 没有正文：{label}: {current}")
            sections.append(ReviewedSection(*current, tuple(body)))
        current = None
        body = []

    for line_number, raw in enumerate(normalize_text(value).split("\n"), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("---"):
            match = HEADER_RE.fullmatch(line)
            if not match:
                raise MaterializeError(
                    f"无法识别的 Section 标题：{label}:{line_number}"
                )
            flush()
            current = (
                int(match.group(1)),
                int(match.group(2)) if match.group(2) else None,
                safe_source_name(match.group(3)),
            )
            continue
        if current is None:
            raise MaterializeError(
                f"首个 Section 前存在正文：{label}:{line_number}"
            )
        if line.startswith("@S0\t"):
            try:
                payload = json.loads(line[4:])
            except json.JSONDecodeError as exc:
                raise MaterializeError(
                    f"Scene0 扩展行不是有效 JSON：{label}:{line_number}"
                ) from exc
            if not isinstance(payload, dict):
                raise MaterializeError(
                    f"Scene0 扩展行必须是对象：{label}:{line_number}"
                )
            kind = payload.get("kind")
            speaker = payload.get("speaker")
            text = payload.get("text")
            command = payload.get("command")
            position = payload.get("position", "")
            if (
                kind not in {"dialogue", "narration", "fnarration"}
                or not isinstance(speaker, str)
                or not speaker
                or not isinstance(text, str)
                or not text
                or not isinstance(command, str)
                or not command
                or not isinstance(position, str)
            ):
                raise MaterializeError(
                    f"Scene0 扩展行字段无效：{label}:{line_number}"
                )
            body.append(
                ReviewedLine(
                    "s0",
                    speaker,
                    text,
                    command=command,
                    position=position,
                    scene0_kind=kind,
                )
            )
            continue
        choice = CHOICE_RE.fullmatch(line)
        if choice:
            body.append(
                ReviewedLine("choice", "选项", choice.group(1), choice.group(2))
            )
            continue
        if INTERVIEW_LINE_RE.fullmatch(line):
            body.append(ReviewedLine("interview_marker", "旁白", "取材记录"))
            continue
        speaker, text = split_dialogue(line)
        if not speaker or not text:
            raise MaterializeError(
                f"空说话人或正文：{label}:{line_number}"
            )
        if len(speaker) > 128 or len(text) > 100_000:
            raise MaterializeError(
                f"说话人或正文过长：{label}:{line_number}"
            )
        body.append(ReviewedLine("text", speaker, text))
    flush()
    if not sections:
        raise MaterializeError(f"校对 TXT 不含 Section：{label}")
    signatures = [section.signature for section in sections]
    if len(signatures) != len(set(signatures)):
        raise MaterializeError(f"校对 TXT 含重复 Section/Branch：{label}")
    return tuple(sections)


def parse_reviewed_txt(path: Path) -> tuple[ReviewedSection, ...]:
    try:
        value = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise MaterializeError(f"校对 TXT 不是有效 UTF-8：{path}: {exc}") from exc
    return parse_reviewed_text(value, str(path))


def clean_magireco_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.replace("@", "\\n").replace("[br]", "\\n")
    text = text.replace("「textBlack:", "[textBlack:").replace(
        "『textBlack:", "[textBlack:"
    )
    for tag, source in COLOR_TAGS.items():
        text = re.sub(
            rf"\[text{source}:(.*?)\]",
            rf"<{tag}>\1</{tag}>",
            text,
            flags=re.DOTALL,
        )
    text = re.sub(r"\[.*?\]", "", text)
    return text.strip()


def _encode_color_tags(value: str) -> str:
    result = value
    for tag, source in COLOR_TAGS.items():
        pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.I | re.DOTALL)
        while pattern.search(result):
            result = pattern.sub(rf"[text{source}:\1]", result)
    if re.search(r"</?[A-Za-z][^>]*>", result):
        raise MaterializeError("校对正文含不支持的 HTML/XML 标签")
    return result


def merge_magireco_visible(original: str, reviewed: str) -> str:
    """Encode visible text while retaining all original playback commands."""

    desired = reviewed.strip()
    if "@" in desired or "\r" in desired or "\0" in desired:
        raise MaterializeError("校对正文不得直接包含 @、回车或 NUL")
    if clean_magireco_text(original) == desired:
        return original

    original_visible = clean_magireco_text(original)
    original_segments = original_visible.split("\\n")
    desired_segments = desired.split("\\n")
    commands_by_segment: list[list[str]] = [
        [] for _ in range(max(1, len(desired_segments)))
    ]
    for match in CONTROL_RE.finditer(original):
        prefix = clean_magireco_text(original[: match.start()])
        source_segment = prefix.count("\\n")
        if len(original_segments) <= 1:
            target_segment = 0
        else:
            target_segment = round(
                source_segment
                * (len(desired_segments) - 1)
                / (len(original_segments) - 1)
            )
        commands_by_segment[min(target_segment, len(commands_by_segment) - 1)].append(
            match.group(0)
        )

    encoded_segments: list[str] = []
    for index, segment in enumerate(desired_segments):
        encoded = _encode_color_tags(segment)
        encoded_segments.append("".join(commands_by_segment[index]) + encoded)
    result = "@".join(encoded_segments)
    if clean_magireco_text(result) != desired:
        raise MaterializeError("Magia Record 正文编码后无法无损回生")
    original_commands = CONTROL_RE.findall(original)
    output_commands = CONTROL_RE.findall(result)
    if original_commands != output_commands:
        raise MaterializeError("Magia Record 播放控制指令发生变化")
    return result


def _interview_parts(value: str) -> tuple[list[str], list[str], list[int]]:
    pieces = re.split(r"(@|\[br\])", value)
    segments = pieces[::2]
    separators = pieces[1::2]
    names: list[int] = []
    for index, segment in enumerate(segments):
        cleaned = clean_magireco_text(segment)
        plain = re.sub(r"<black>(.*?)</black>", r"\1", cleaned).strip()
        if (
            plain
            and "记录" not in plain
            and "記録" not in plain
            and "―" not in plain
        ):
            names.append(index)
    return segments, separators, names


class MagirecoEvent:
    def __init__(
        self,
        *,
        kind: str,
        container: dict[str, Any],
        text_key: str,
        name_key: str = "",
        choice_group: str = "",
    ) -> None:
        self.kind = kind
        self.container = container
        self.text_key = text_key
        self.name_key = name_key
        self.choice_group = choice_group
        self.extended = False

    @property
    def output_count(self) -> int:
        if self.kind != "interview":
            return 1
        _, _, names = _interview_parts(str(self.container[self.text_key]))
        return 1 + len(names)

    def apply(self, lines: Sequence[ReviewedLine]) -> None:
        if len(lines) != self.output_count:
            raise MaterializeError("Magia Record 事件输出行数发生变化")
        if self.kind == "choice":
            line = lines[0]
            if line.kind != "choice" or line.choice_group != self.choice_group:
                raise MaterializeError(
                    "选项目标分支发生变化，拒绝写入 JSON"
                )
            self.container[self.text_key] = merge_magireco_visible(
                str(self.container[self.text_key]), line.text
            )
            return
        if self.kind == "interview":
            if lines[0].kind != "interview_marker":
                raise MaterializeError("取材记录结构标记被删除或改写")
            segments, separators, name_indices = _interview_parts(
                str(self.container[self.text_key])
            )
            reviewed_names = lines[1:]
            if (
                len(reviewed_names) != len(name_indices)
                or any(
                    line.kind not in {"text", "s0"}
                    or line.speaker not in NARRATION_SPEAKERS
                    for line in reviewed_names
                )
            ):
                raise MaterializeError("取材记录姓名块结构发生变化")
            self.extended = bool(reviewed_names) and all(
                line.kind == "s0" for line in reviewed_names
            )
            if any(line.kind == "s0" for line in reviewed_names) and not self.extended:
                raise MaterializeError("取材记录不得混用普通与 Scene0 扩展行")
            if self.extended and any(
                line.command != "interviewMarker"
                or line.scene0_kind != "narration"
                for line in reviewed_names
            ):
                raise MaterializeError("取材记录 Scene0 命令结构发生变化")
            for index, line in zip(name_indices, reviewed_names):
                segments[index] = merge_magireco_visible(
                    segments[index], line.text
                )
            rebuilt: list[str] = []
            for index, segment in enumerate(segments):
                rebuilt.append(segment)
                if index < len(separators):
                    rebuilt.append(separators[index])
            self.container[self.text_key] = "".join(rebuilt)
            return

        line = lines[0]
        if line.kind not in {"text", "s0"}:
            raise MaterializeError("文本事件类型被改为选项或结构标记")
        self.extended = line.kind == "s0"
        if self.extended:
            expected_kind = (
                "fnarration"
                if self.kind == "fnarration"
                else "narration"
                if self.kind == "narration"
                else "dialogue"
            )
            expected_position = ""
            if self.kind == "dialogue":
                expected_position = next(
                    (
                        position.casefold()
                        for position in ("Left", "Right", "Center")
                        if position in self.text_key
                    ),
                    "",
                )
            if (
                line.command != self.text_key
                or line.scene0_kind != expected_kind
                or line.position.casefold() != expected_position
            ):
                raise MaterializeError(
                    "Scene0 command/kind/position 结构发生变化"
                )
        original = str(self.container[self.text_key])
        self.container[self.text_key] = merge_magireco_visible(
            original, line.text
        )
        if self.name_key:
            if self.kind in {"narration", "fnarration"}:
                self.container[self.name_key] = (
                    "" if line.speaker in NARRATION_SPEAKERS else line.speaker
                )
            else:
                self.container[self.name_key] = line.speaker

    def render(self) -> tuple[ReviewedLine, ...]:
        raw = str(self.container[self.text_key])
        if self.kind == "choice":
            return (
                ReviewedLine(
                    "choice",
                    "选项",
                    clean_magireco_text(raw),
                    self.choice_group,
                ),
            )
        if self.kind == "interview":
            segments, _, indices = _interview_parts(raw)
            return (
                ReviewedLine("interview_marker", "旁白", "取材记录"),
                *(
                    ReviewedLine(
                        "s0" if self.extended else "text",
                        "旁白",
                        clean_magireco_text(segments[index]),
                        command="interviewMarker" if self.extended else "",
                        scene0_kind="narration" if self.extended else "",
                    )
                    for index in indices
                ),
            )
        speaker = (
            str(self.container.get(self.name_key) or "旁白")
            if self.name_key
            else "旁白"
        )
        if self.extended:
            scene0_kind = (
                "fnarration"
                if self.kind == "fnarration"
                else "narration"
                if self.kind == "narration"
                else "dialogue"
            )
            position = next(
                (
                    value.casefold()
                    for value in ("Left", "Right", "Center")
                    if value in self.text_key
                ),
                "",
            )
            return (
                ReviewedLine(
                    "s0",
                    speaker,
                    clean_magireco_text(raw),
                    command=self.text_key,
                    position=position,
                    scene0_kind=scene0_kind,
                ),
            )
        return (ReviewedLine("text", speaker, clean_magireco_text(raw)),)


def magireco_events(group: list[Any]) -> list[MagirecoEvent]:
    events: list[MagirecoEvent] = []
    for item in group:
        if not isinstance(item, dict):
            continue
        selections = item.get("select")
        if isinstance(selections, list):
            for option in selections:
                if not isinstance(option, dict):
                    continue
                text = option.get("textSelect")
                if not isinstance(text, str) or not text.strip():
                    continue
                target = str(option.get("group") or "")
                if re.fullmatch(r"group_\d+", target) is None:
                    raise MaterializeError(
                        f"JSON 选项目标分支无效：{target!r}"
                    )
                events.append(
                    MagirecoEvent(
                        kind="choice",
                        container=option,
                        text_key="textSelect",
                        choice_group=target,
                    )
                )
            continue

        narration = item.get("narration")
        if isinstance(narration, str) and any(
            marker in narration for marker in INTERVIEW_MARKERS
        ):
            events.append(
                MagirecoEvent(
                    kind="interview",
                    container=item,
                    text_key="narration",
                )
            )
            continue

        key = next(
            (
                candidate
                for candidate in ("Fnarration", "progressFnarration")
                if isinstance(item.get(candidate), str)
                and str(item[candidate]).strip()
            ),
            "",
        )
        if key:
            events.append(
                MagirecoEvent(
                    kind="fnarration",
                    container=item,
                    text_key=key,
                    name_key="nameFnarration",
                )
            )
            continue

        key = next(
            (
                candidate
                for candidate in ("narration", "progressNarration")
                if isinstance(item.get(candidate), str)
                and str(item[candidate]).strip()
            ),
            "",
        )
        if key:
            events.append(
                MagirecoEvent(
                    kind="narration",
                    container=item,
                    text_key=key,
                    name_key="nameNarration",
                )
            )
            continue

        for position in ("Left", "Right", "Center"):
            text_key = next(
                (
                    candidate
                    for candidate in (f"textAv{position}", f"text{position}")
                    if isinstance(item.get(candidate), str)
                    and str(item[candidate]).strip()
                ),
                "",
            )
            if not text_key:
                continue
            name_key = (
                f"nameAv{position}"
                if text_key.startswith("textAv")
                else f"name{position}"
            )
            events.append(
                MagirecoEvent(
                    kind="dialogue",
                    container=item,
                    text_key=text_key,
                    name_key=name_key,
                )
            )
            break
    return events


VOICE_LINE_RE = re.compile(r"^(【[^】\r\n]{1,512}】)(.*)$")


def _voice_text_home_references(
    group: list[Any],
    *,
    label: str,
) -> list[list[dict[str, Any]]]:
    """Return one reference group for each logical subtitle row.

    Ensemble cards intentionally repeat one voice resource on multiple Live2D
    characters so every model can lip-sync.  Those mirrors are one subtitle,
    and proofreading must keep their ``textHome`` values synchronized.  A
    textHome-only continuation remains a separate logical row.
    """

    voice_references: list[dict[str, Any]] = []
    voice_ids: list[str] = []
    voice_texts: list[str] = []
    continuation_references: dict[str, list[dict[str, Any]]] = {}
    for turn in group:
        if not isinstance(turn, dict):
            continue
        charas = turn.get("chara")
        if not isinstance(charas, list):
            continue
        for chara in charas:
            if not isinstance(chara, dict):
                continue
            voice = (
                str(chara.get("voice")).strip()
                if isinstance(chara.get("voice"), str)
                else ""
            )
            text_home = (
                str(chara.get("textHome")).strip()
                if isinstance(chara.get("textHome"), str)
                else ""
            )
            if voice:
                voice_references.append(chara)
                if voice not in voice_ids:
                    voice_ids.append(voice)
                if text_home and text_home not in voice_texts:
                    voice_texts.append(text_home)
            elif text_home:
                continuation_references.setdefault(text_home, []).append(chara)

    if len(voice_ids) > 1:
        raise MaterializeError(
            f"{label} 同一语音组含多个不同语音资源：{voice_ids}"
        )
    if len(voice_texts) > 1:
        raise MaterializeError(
            f"{label} 重复语音角色的 textHome 内容冲突"
        )

    references: list[list[dict[str, Any]]] = []
    if voice_references:
        # Keep a logical row even when textHome is absent so proofreading can
        # insert the subtitle into every duplicated voice-bearing character.
        references.append(voice_references)
    references.extend(continuation_references.values())
    return references


def _voice_line_parts(
    line: ReviewedLine,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, str]:
    if line.kind != "text":
        raise MaterializeError(f"{label} 语音行类型被改写")
    match = VOICE_LINE_RE.fullmatch(line.text)
    if not match or (not allow_empty and not match.group(2).strip()):
        raise MaterializeError(f"{label} 语音资源标签或正文无效")
    return match.group(1), match.group(2).strip()


def apply_general_voice_section(
    *,
    group: list[Any],
    reviewed: ReviewedSection,
    immutable: ReviewedSection,
    label: str,
) -> tuple[ReviewedLine, ...]:
    if reviewed.branch is not None:
        raise MaterializeError(f"{label} 语音 Section 结构发生变化")
    references = _voice_text_home_references(group, label=label)
    if not references:
        if reviewed.lines != immutable.lines:
            raise MaterializeError(
                f"{label} 没有 textHome，语音资源占位行不得改写"
            )
        return immutable.lines
    if (
        len(reviewed.lines) != len(references)
        or len(immutable.lines) != len(references)
    ):
        raise MaterializeError(
            f"{label} 的 textHome/TXT 行数不同："
            f"{len(references)}/{len(reviewed.lines)}/"
            f"{len(immutable.lines)}"
        )

    rendered: list[ReviewedLine] = []
    for position, (reference_group, reviewed_line, immutable_line) in enumerate(
        zip(references, reviewed.lines, immutable.lines),
        1,
    ):
        reviewed_prefix, reviewed_body = _voice_line_parts(
            reviewed_line,
            f"{label}/textHome[{position}]",
        )
        immutable_prefix, _ = _voice_line_parts(
            immutable_line,
            f"{label}/textHome[{position}]",
            allow_empty=True,
        )
        if (
            reviewed_line.speaker != immutable_line.speaker
            or reviewed_prefix != immutable_prefix
        ):
            raise MaterializeError(
                f"{label} 的角色名、语音资源或时长标签不得改写"
            )
        # Playable JSON uses @ as an in-game line separator while canonical
        # TXT renders it as ／.  Only the proven textHome cell is assigned.
        encoded_body = reviewed_body.replace("／", "@")
        for chara in reference_group:
            chara["textHome"] = encoded_body
        rendered_body = encoded_body.replace("@", "／").strip()
        if not rendered_body:
            raise MaterializeError(
                f"{label} 第 {position} 个校对正文为空"
            )
        rendered.append(
            ReviewedLine(
                "text",
                immutable_line.speaker,
                f"{immutable_prefix}{rendered_body}",
            )
        )
    return tuple(rendered)


def _general_voice_translation_stats(
    document: Mapping[str, Any],
) -> tuple[int, int, int, int]:
    story = document.get("story")
    if not isinstance(story, dict) or not story:
        raise MaterializeError("魔法纪录语音 JSON 缺少 story")
    translated = 0
    total = 0
    raw_references = 0
    without_voice = 0
    for turns in story.values():
        if not isinstance(turns, list):
            raise MaterializeError("魔法纪录语音 JSON 分组不是数组")
        first: dict[str, Any] | None = None
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("chara"), list):
                continue
            for chara in turn["chara"]:
                if (
                    isinstance(chara, dict)
                    and isinstance(chara.get("voice"), str)
                    and chara["voice"].strip()
                ):
                    raw_references += 1
                    if first is None:
                        first = chara
        if first is None:
            without_voice += 1
            continue
        total += 1
        if isinstance(first.get("textHome"), str) and first["textHome"].strip():
            translated += 1
    return translated, total, raw_references, without_voice


class ExedraEvent:
    def __init__(
        self,
        *,
        action: str,
        speaker: str,
        references: list[tuple[list[Any], int]],
    ) -> None:
        self.action = action
        self.speaker = speaker
        self.references = references

    def apply(
        self,
        line: ReviewedLine,
        *,
        immutable_speaker: str | None = None,
    ) -> None:
        if line.kind != "text":
            raise MaterializeError("Exedra 文本事件类型被改写")
        source_speaker = (
            immutable_speaker
            if immutable_speaker is not None
            else self.speaker
        )
        submitted_speaker = (
            "Narration" if line.speaker in NARRATION_SPEAKERS else line.speaker
        )
        expected_speaker = (
            "Narration"
            if source_speaker in NARRATION_SPEAKERS
            else source_speaker
        )
        if submitted_speaker != expected_speaker:
            raise MaterializeError(
                "Exedra 说话人身份不可在正文校对中修改："
                f"基准={source_speaker!r} TXT={line.speaker!r}"
            )
        text = line.text.strip()
        if not text:
            raise MaterializeError("Exedra 校对正文不得为空")
        for cells, comment_index in self.references:
            cells[comment_index] = text

    def render(self, *, speaker: str | None = None) -> ReviewedLine:
        cells, comment_index = self.references[0]
        return ReviewedLine(
            "text",
            speaker if speaker is not None else self.speaker or "Narration",
            str(cells[comment_index]).strip(),
        )


def exedra_events(document: dict[str, Any]) -> list[ExedraEvent]:
    sheets = document.get("sheetList")
    if not isinstance(sheets, list):
        raise MaterializeError("Exedra JSON 缺少 sheetList")
    unique: list[tuple[str, list[ExedraEvent]]] = []
    by_fingerprint: dict[str, int] = {}
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        header = sheet.get("headerRow")
        rows = sheet.get("contentRowList")
        cells = header.get("cellList") if isinstance(header, dict) else None
        if not isinstance(cells, list) or not isinstance(rows, list):
            continue
        headers = [str(item or "").strip().casefold() for item in cells]
        try:
            action_index = headers.index("actiontype")
            comment_index = headers.index("comment")
        except ValueError:
            continue
        name_index = headers.index("name") if "name" in headers else -1
        events: list[ExedraEvent] = []
        fingerprint_rows: list[tuple[str, str, str]] = []
        for row in rows:
            row_cells = row.get("cellList") if isinstance(row, dict) else None
            if not isinstance(row_cells, list):
                continue
            action = str(
                row_cells[action_index]
                if action_index < len(row_cells)
                else ""
            ).strip()
            text = (
                row_cells[comment_index]
                if comment_index < len(row_cells)
                else ""
            )
            if (
                action.casefold() not in EXEDRA_TEXT_ACTIONS
                or not isinstance(text, str)
                or not text.strip()
            ):
                continue
            speaker = str(
                row_cells[name_index]
                if name_index >= 0 and name_index < len(row_cells)
                else ""
            ).strip()
            events.append(
                ExedraEvent(
                    action=action,
                    speaker=speaker or "Narration",
                    references=[(row_cells, comment_index)],
                )
            )
            fingerprint_rows.append((action, speaker, text.strip()))
        if not events:
            continue
        fingerprint = json.dumps(
            fingerprint_rows, ensure_ascii=False, separators=(",", ":")
        )
        duplicate = by_fingerprint.get(fingerprint)
        if duplicate is None:
            by_fingerprint[fingerprint] = len(unique)
            unique.append((fingerprint, events))
            continue
        primary = unique[duplicate][1]
        if len(primary) != len(events):
            raise MaterializeError("Exedra 重复工作表事件数量不同")
        for target, duplicate_event in zip(primary, events):
            target.references.extend(duplicate_event.references)
    return [
        event
        for _fingerprint, sheet_events in unique
        for event in sheet_events
    ]


def apply_event_lines(
    events: Sequence[MagirecoEvent],
    reviewed: Sequence[ReviewedLine],
    label: str,
) -> tuple[ReviewedLine, ...]:
    offset = 0
    for event in events:
        end = offset + event.output_count
        if end > len(reviewed):
            raise MaterializeError(
                f"{label} 文本事件数不同：JSON 至少 {end}，TXT={len(reviewed)}"
            )
        event.apply(reviewed[offset:end])
        offset = end
    if offset != len(reviewed):
        raise MaterializeError(
            f"{label} 文本事件数不同：JSON={offset}，TXT={len(reviewed)}"
        )
    return tuple(line for event in events for line in event.render())


def canonical_section(section: ReviewedSection) -> str:
    branch = (
        f" - Branch {section.branch}" if section.branch is not None else ""
    )
    output = [
        f"--- [Section {section.number}{branch}] "
        f"(Source: {section.source}) ---"
    ]
    for line in section.lines:
        if line.kind == "choice":
            output.append(
                f"选项: 【{line.text.strip()}】→ {line.choice_group}"
            )
        elif line.kind == "interview_marker":
            output.append("―― 取材记录 ――")
        elif line.kind == "s0":
            payload = {
                "kind": line.scene0_kind,
                "speaker": line.speaker,
                "text": line.text.strip(),
                "command": line.command,
            }
            if line.position:
                payload["position"] = line.position
            output.append(
                "@S0\t"
                + json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        else:
            output.append(f"{line.speaker}：{line.text.strip()}")
    return "\n".join(output)


def canonical_txt(sections: Sequence[ReviewedSection]) -> str:
    return "\n\n".join(canonical_section(section) for section in sections) + "\n"


def _load_template(
    *,
    reader: BlobReader,
    cn_relative: PurePosixPath,
    jp_relative: PurePosixPath,
) -> JsonTemplate:
    raw = reader.read(cn_relative)
    source = cn_relative
    if raw is None:
        raw = reader.read(jp_relative)
        source = jp_relative
    if raw is None:
        raise MaterializeError(
            "缺少可播放 JSON 结构模板："
            f"{cn_relative.as_posix()} / {jp_relative.as_posix()}"
        )
    document = load_json_bytes(raw, source.as_posix())
    return JsonTemplate(
        document=copy.deepcopy(document),
        source_path=source.as_posix(),
        source_sha256=sha256_bytes(raw),
        formatting_source=raw,
    )


def _load_exedra_group(
    repo_root: Path,
    category: str,
    group_key: str,
) -> dict[str, Any]:
    manifest_path = repo_root.joinpath(*EXEDRA_MANIFEST_REL.parts)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterializeError(f"Exedra manifest 无法读取：{exc}") from exc
    groups = manifest.get("groups") if isinstance(manifest, dict) else None
    if not isinstance(groups, list):
        raise MaterializeError("Exedra manifest 缺少 groups")
    matches = [
        item
        for item in groups
        if isinstance(item, dict)
        and item.get("category") == category
        and item.get("groupKey") == group_key
    ]
    if len(matches) != 1:
        raise MaterializeError(
            f"Exedra manifest 逻辑组应唯一：{category}/{group_key}"
        )
    return matches[0]


def _episode_number(source: str, fallback: int) -> int:
    match = re.search(r"_(\d+)\.json$", source, re.I)
    return int(match.group(1)) if match else fallback


def _build_exedra_import_report(
    *,
    repo_root: Path,
    category: str,
    group_key: str,
    jp_txt: Path,
    cn_payload: bytes,
    json_meta: list[dict[str, Any]],
) -> dict[str, Any]:
    sys.path.insert(0, str(repo_root))
    import generate_story_index as pipeline  # noqa: PLC0415

    with tempfile.TemporaryDirectory(
        prefix="proofreading-exedra-"
    ) as temporary:
        cn_txt = Path(temporary) / f"{group_key}_cn.txt"
        cn_txt.write_bytes(cn_payload)
        jp_sections = pipeline._exedra_alignment_sections(jp_txt)
        cn_sections = pipeline._exedra_alignment_sections(cn_txt)
    if len(jp_sections) != len(cn_sections):
        raise MaterializeError("Exedra 中日 Section 数量不同")
    sections: list[dict[str, Any]] = []
    for index, (jp, cn) in enumerate(zip(jp_sections, cn_sections), 1):
        if (
            jp.number != cn.number
            or jp.source_name != cn.source_name
            or jp.reader_block_count != cn.reader_block_count
            or jp.speaker_sequence_sha256 != cn.speaker_sequence_sha256
        ):
            raise MaterializeError(
                f"Exedra JSON→TXT 结构证明失败：Section {index}"
            )
        sections.append(
            {
                "section": index,
                "source": jp.source_name,
                "wikiEpisode": _episode_number(jp.source_name, index - 1),
                "readerNormalizedBlocks": {
                    "jp": jp.reader_block_count,
                    "cn": cn.reader_block_count,
                    "matches": True,
                },
                "speakerSequenceSha256": {
                    "jp": jp.speaker_sequence_sha256,
                    "cn": cn.speaker_sequence_sha256,
                },
            }
        )
    jp_sha = pipeline._sha256_utf8_text_file(jp_txt)
    cn_sha = sha256_text(cn_payload.decode("utf-8"))
    return {
        "schemaVersion": 1,
        "status": "validated",
        "provenance": "community_proofread_human",
        "sourceRoot": "community-proofreading",
        "group": {"category": category, "groupKey": group_key},
        "validation": {
            "passed": True,
            "mismatchCount": 0,
            "usesLcs": False,
            "usesFuzzyMatching": False,
            "allowsReordering": False,
        },
        "mismatches": [],
        "jp": {
            "contentSha256": jp_sha,
            "sectionCount": len(jp_sections),
            "readerNormalizedBlockCount": sum(
                item.reader_block_count for item in jp_sections
            ),
        },
        "cn": {
            "renderedSha256": cn_sha,
            "sectionCount": len(cn_sections),
            "readerNormalizedBlockCount": sum(
                item.reader_block_count for item in cn_sections
            ),
        },
        "sections": sections,
        "sourceJson": json_meta,
    }


def _build_exedra_provenance(
    *,
    existing: bytes | None,
    source_identity: str,
    jp_sha256: str,
    cn_sha256: str,
    json_payloads: Mapping[str, bytes],
    json_meta: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    if existing is not None:
        try:
            decoded = json.loads(existing.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MaterializeError(
                f"Exedra 来源侧车无效：{source_identity}: {exc}"
            ) from exc
        if not isinstance(decoded, dict):
            raise MaterializeError("Exedra 来源侧车顶层不是对象")
        value = copy.deepcopy(decoded)
    value.update(
        {
            "version": 1,
            "sourceIdentity": source_identity,
            "provenance": "community_proofread_human",
            "machineTranslation": False,
            "jpSha256": jp_sha256,
            "cnSha256": cn_sha256,
        }
    )
    previous_episodes = {
        str(item.get("source")): item
        for item in value.get("episodes", [])
        if isinstance(item, dict) and isinstance(item.get("source"), str)
    }
    episodes: list[dict[str, Any]] = []
    for meta in json_meta:
        source = str(meta["source"])
        episode = copy.deepcopy(previous_episodes.get(source, {}))
        episode.update(
            {
                "source": source,
                "cnSha256": sha256_bytes(json_payloads[source]),
                "provenance": "community_proofread_human",
                "eventCount": int(meta["eventCount"]),
            }
        )
        episodes.append(episode)
    value["episodes"] = episodes
    value["proofreading"] = {
        "status": "validated",
        "jsonCount": len(json_payloads),
        "jsonToTxtRoundTrip": True,
    }
    return value


def _working_bytes(repo_root: Path, relative: str) -> bytes | None:
    path = repo_root.joinpath(*safe_repo_path(relative).parts)
    if not path.is_file() or path.is_symlink():
        return None
    return path.read_bytes()


def transactional_write(repo_root: Path, payloads: Mapping[str, bytes]) -> None:
    """Replace all outputs, rolling back every prior replacement on failure."""

    token = uuid.uuid4().hex
    prepared: list[tuple[Path, Path, Path | None, bool]] = []
    for relative, payload in sorted(payloads.items()):
        destination = repo_root.joinpath(*safe_repo_path(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{token}.tmp")
        backup = destination.with_name(f".{destination.name}.{token}.bak")
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        prepared.append(
            (destination, temporary, backup if destination.exists() else None, False)
        )

    completed: list[tuple[Path, Path | None]] = []
    try:
        for destination, temporary, backup, _ in prepared:
            if backup is not None:
                os.replace(destination, backup)
            try:
                os.replace(temporary, destination)
            except Exception:
                if backup is not None and backup.exists():
                    os.replace(backup, destination)
                raise
            completed.append((destination, backup))
    except Exception:
        for destination, backup in reversed(completed):
            try:
                if destination.exists():
                    destination.unlink()
                if backup is not None and backup.exists():
                    os.replace(backup, destination)
            except OSError:
                pass
        raise
    finally:
        for _destination, temporary, backup, _ in prepared:
            try:
                temporary.unlink(missing_ok=True)
                if backup is not None:
                    backup.unlink(missing_ok=True)
            except OSError:
                pass


def materialize(
    txt_path: Path,
    *,
    repo_root: Path = ROOT,
    write: bool,
    base_ref: str | None = None,
    reviewed_text: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    txt_path = txt_path.resolve(strict=True)
    if txt_path.is_symlink():
        raise MaterializeError("校对 TXT 不得为符号链接")
    try:
        relative_txt_path = txt_path.relative_to(repo_root)
    except ValueError as exc:
        raise MaterializeError("校对 TXT 不在仓库中") from exc
    relative_txt = safe_repo_path(relative_txt_path.as_posix())
    if relative_txt.is_relative_to(MAGIRECO_CN_REL):
        game = "magireco"
        cn_root_rel = MAGIRECO_CN_REL
        jp_root_rel = MAGIRECO_JP_REL
    elif relative_txt.is_relative_to(MAGIRECO_VOICE_CN_REL):
        game = "magireco_voice"
        cn_root_rel = MAGIRECO_VOICE_CN_REL
        jp_root_rel = MAGIRECO_VOICE_JSON_REL
    elif relative_txt.is_relative_to(EXEDRA_CN_REL):
        game = "exedra"
        cn_root_rel = EXEDRA_CN_REL
        jp_root_rel = EXEDRA_JP_REL
    else:
        raise MaterializeError("校对 TXT 不在允许的中文剧情目录")

    reader = BlobReader(repo_root, base_ref)
    reviewed_sections = (
        parse_reviewed_text(reviewed_text, f"approved:{relative_txt}")
        if reviewed_text is not None
        else parse_reviewed_txt(txt_path)
    )
    base_txt = reader.read(relative_txt)
    if base_ref and base_txt is None:
        raise MaterializeError("目标分支中不存在被校对的中文 TXT")
    base_sections: tuple[ReviewedSection, ...] | None = None
    if base_txt is not None:
        base_sections = parse_reviewed_text(
            base_txt.decode("utf-8-sig"), f"{base_ref or 'working'}:{relative_txt}"
        )
        if [item.signature for item in reviewed_sections] != [
            item.signature for item in base_sections
        ]:
            raise MaterializeError(
                "Section/Branch/Source 顺序与目标分支不同"
            )

    under_cn = relative_txt.relative_to(cn_root_rel)
    folder = under_cn.parent
    group_key = folder.name
    category = folder.parent.as_posix() if game == "exedra" else ""
    exedra_group: dict[str, Any] | None = None
    exedra_sources: list[str] = []
    voice_model_paths: tuple[str, PurePosixPath, PurePosixPath] | None = None
    if game == "magireco_voice":
        voice_model_paths = general_voice_model_paths_for_txt(
            reader=reader,
            relative_txt=relative_txt,
        )
    if game == "exedra":
        if len(folder.parts) != 2:
            raise MaterializeError("Exedra 中文 TXT 必须位于分类/逻辑组目录")
        exedra_group = _load_exedra_group(repo_root, category, group_key)
        raw_sources = exedra_group.get("sources")
        if not isinstance(raw_sources, list):
            raise MaterializeError("Exedra manifest 逻辑组缺少 sources")
        exedra_sources = [
            safe_source_name(PurePosixPath(str(item)).name)
            for item in raw_sources
        ]
        if [item.source for item in reviewed_sections] != exedra_sources:
            raise MaterializeError(
                "Exedra Section 来源顺序与 organizer manifest 不同"
            )
        if any(item.branch is not None for item in reviewed_sections):
            raise MaterializeError("Exedra Section 不允许 Branch")

    sections_by_source: dict[str, list[tuple[int, ReviewedSection]]] = {}
    for index, section in enumerate(reviewed_sections):
        sections_by_source.setdefault(section.source, []).append((index, section))

    output_sections: list[ReviewedSection | None] = [
        None for _ in reviewed_sections
    ]
    payloads: dict[str, bytes] = {}
    json_payloads_by_name: dict[str, bytes] = {}
    json_meta: list[dict[str, Any]] = []
    for source, indexed_sections in sections_by_source.items():
        if game == "magireco_voice":
            assert voice_model_paths is not None
            model_id, jp_json_rel, cn_json_rel = voice_model_paths
            if source != f"{model_id}.json":
                raise MaterializeError("魔法纪录语音 Source 与模型 ID 不一致")
        else:
            cn_json_rel = cn_root_rel / folder / source
            jp_json_rel = jp_root_rel / folder / source
        template = _load_template(
            reader=reader,
            cn_relative=cn_json_rel,
            jp_relative=jp_json_rel,
        )
        document = template.document

        if game == "magireco":
            story = document.get("story")
            if not isinstance(story, dict):
                raise MaterializeError(
                    f"Magia Record JSON 缺少 story：{source}"
                )
            event_count = 0
            for output_index, section in indexed_sections:
                group_name = f"group_{section.branch or 1}"
                group = story.get(group_name)
                if not isinstance(group, list):
                    raise MaterializeError(
                        f"{source} 缺少 {group_name}"
                    )
                events = magireco_events(group)
                rendered_lines = apply_event_lines(
                    events,
                    section.lines,
                    f"{source}/{group_name}",
                )
                event_count += len(rendered_lines)
                output_sections[output_index] = ReviewedSection(
                    section.number,
                    section.branch,
                    section.source,
                    rendered_lines,
                )
        elif game == "magireco_voice":
            story = document.get("story")
            if not isinstance(story, dict) or not story:
                raise MaterializeError(
                    f"魔法纪录语音 JSON 缺少 story：{source}"
                )
            ordered_groups = sorted(
                story,
                key=lambda value: int(str(value).removeprefix("group_"))
                if re.fullmatch(r"group_\d+", str(value))
                else -1,
            )
            if (
                any(
                    re.fullmatch(r"group_\d+", str(value)) is None
                    for value in ordered_groups
                )
                or len(indexed_sections) != len(ordered_groups)
            ):
                raise MaterializeError(
                    f"{source} 语音 JSON/Section 分组数量不同"
                )
            expected_sections = list(range(1, len(ordered_groups) + 1))
            actual_sections = [
                section.number for _index, section in indexed_sections
            ]
            if actual_sections != expected_sections:
                raise MaterializeError(
                    f"{source} 语音 Section 编号或顺序发生变化"
                )
            if base_sections is None:
                raise MaterializeError(
                    f"{source} 缺少目标分支语音 TXT 结构模板"
                )
            event_count = 0
            for (output_index, section), group_name in zip(
                indexed_sections,
                ordered_groups,
            ):
                group = story.get(group_name)
                if not isinstance(group, list):
                    raise MaterializeError(
                        f"{source} 语音分组无效：{group_name}"
                    )
                rendered_lines = apply_general_voice_section(
                    group=group,
                    reviewed=section,
                    immutable=base_sections[output_index],
                    label=f"{source}/{group_name}",
                )
                output_sections[output_index] = ReviewedSection(
                    section.number,
                    None,
                    section.source,
                    rendered_lines,
                )
                event_count += len(rendered_lines)
        else:
            if len(indexed_sections) != 1:
                raise MaterializeError(
                    f"Exedra Source 必须只对应一个 Section：{source}"
                )
            output_index, section = indexed_sections[0]
            events = exedra_events(document)
            if len(events) != len(section.lines):
                raise MaterializeError(
                    f"{source} 文本事件数不同："
                    f"JSON={len(events)} TXT={len(section.lines)}"
                )
            immutable_lines = (
                base_sections[output_index].lines
                if base_sections is not None
                else section.lines
            )
            if (
                len(immutable_lines) != len(events)
                or any(line.kind != "text" for line in immutable_lines)
            ):
                raise MaterializeError(
                    f"{source} 的目标分支说话人结构与 JSON 事件数不同"
                )
            for event, line, immutable in zip(
                events, section.lines, immutable_lines
            ):
                event.apply(
                    line,
                    immutable_speaker=immutable.speaker,
                )
            rendered_lines = tuple(
                event.render(speaker=immutable.speaker)
                for event, immutable in zip(events, immutable_lines)
            )
            event_count = len(events)
            output_sections[output_index] = ReviewedSection(
                section.number,
                None,
                section.source,
                rendered_lines,
            )

        encoded = json_bytes_like(document, template.formatting_source)
        payloads[cn_json_rel.as_posix()] = encoded
        json_payloads_by_name[source] = encoded
        json_meta.append(
            {
                "source": source,
                "template": template.source_path,
                "templateSha256": template.source_sha256,
                "output": cn_json_rel.as_posix(),
                "outputSha256": sha256_bytes(encoded),
                "eventCount": event_count,
            }
        )

    if any(item is None for item in output_sections):
        raise MaterializeError("内部错误：存在未回生的 Section")
    canonical_sections = tuple(
        item for item in output_sections if item is not None
    )
    canonical = canonical_txt(canonical_sections)
    reparsed = parse_reviewed_text(canonical, "JSON round trip")
    if reparsed != canonical_sections:
        raise MaterializeError("由 JSON 回生的 TXT 无法再次无损解析")
    canonical_payload = canonical.encode("utf-8")
    payloads[relative_txt.as_posix()] = canonical_payload

    voice_pair_paths: tuple[str, str] | None = None
    if game == "magireco_voice":
        assert voice_model_paths is not None
        model_id, expected_source_json_rel, expected_cn_json_rel = voice_model_paths
        expected_source = f"{model_id}.json"
        if (
            not re.fullmatch(r"\d{6}", model_id)
            or relative_txt.name != f"{model_id}_cn.txt"
            or len(json_meta) != 1
            or json_meta[0].get("source") != expected_source
            or json_meta[0].get("output") != expected_cn_json_rel.as_posix()
        ):
            raise MaterializeError("魔法纪录语音 JSON/TXT 配对路径无效")
        cn_json_payload = payloads.get(expected_cn_json_rel.as_posix())
        if cn_json_payload is None:
            raise MaterializeError("魔法纪录语音缺少配对的可播放 JSON")
        payloads.update(
            update_general_voice_manifests(
                reader=reader,
                model_id=model_id,
                source_json_rel=expected_source_json_rel,
                cn_json_rel=expected_cn_json_rel,
                cn_json_payload=cn_json_payload,
                cn_txt_rel=relative_txt,
                cn_txt_payload=canonical_payload,
            )
        )
        voice_pair_paths = (
            expected_cn_json_rel.as_posix(),
            relative_txt.as_posix(),
        )

    source_report_rel = relative_txt.with_suffix(
        ".proofreading-report.json"
    )
    extra_outputs: list[str] = []
    if game == "exedra":
        jp_txt = repo_root.joinpath(
            *(jp_root_rel / folder / f"{group_key}_jp.txt").parts
        )
        if not jp_txt.is_file() or jp_txt.is_symlink():
            raise MaterializeError(f"缺少 Exedra 日文聚合 TXT：{jp_txt}")
        import_report = _build_exedra_import_report(
            repo_root=repo_root,
            category=category,
            group_key=group_key,
            jp_txt=jp_txt,
            cn_payload=canonical_payload,
            json_meta=json_meta,
        )
        import_report_rel = (
            cn_root_rel
            / folder
            / f"{group_key}_cn.import-report.json"
        )
        payloads[import_report_rel.as_posix()] = (
            json.dumps(import_report, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        provenance_rel = (
            cn_root_rel / folder / f"{group_key}_cn.provenance.json"
        )
        existing_provenance = reader.read(provenance_rel)
        provenance = _build_exedra_provenance(
            existing=existing_provenance,
            source_identity=f"exedra:{category}:{group_key}",
            jp_sha256=import_report["jp"]["contentSha256"],
            cn_sha256=import_report["cn"]["renderedSha256"],
            json_payloads=json_payloads_by_name,
            json_meta=json_meta,
        )
        payloads[provenance_rel.as_posix()] = (
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        extra_outputs.extend(
            [import_report_rel.as_posix(), provenance_rel.as_posix()]
        )

    candidate_paths = sorted(
        {
            *payloads,
            source_report_rel.as_posix(),
        }
    )
    changed_paths = sorted(
        path
        for path, payload in payloads.items()
        if reader.read(path) != payload
    )
    if voice_pair_paths is not None and any(
        path not in changed_paths for path in voice_pair_paths
    ):
        raise MaterializeError(
            "魔法纪录语音校对必须同时产生配对 JSON/TXT 变更"
        )
    # The proof file binds all other outputs and is required for every PR.
    if source_report_rel.as_posix() not in changed_paths:
        changed_paths.append(source_report_rel.as_posix())
        changed_paths.sort()
    report = {
        "schemaVersion": 1,
        "status": "validated",
        "game": game,
        "baseRef": base_ref or "",
        "reviewedTxt": relative_txt.as_posix(),
        "reviewedTxtSha256": sha256_text(canonical),
        "jsonCount": len(json_meta),
        "sectionCount": len(canonical_sections),
        "sources": sorted(json_meta, key=lambda item: str(item["source"])),
        "materializedPaths": candidate_paths,
        "changedPaths": changed_paths,
        "validation": {
            "templateComesFromTargetBranch": bool(base_ref),
            "jsonParsed": True,
            "eventCountsMatch": True,
            "sectionAndBranchOrderMatch": True,
            "jsonToTxtRoundTripMatch": True,
            "preservesNonTextTemplate": True,
            "transactionalWrite": True,
            "generalVoiceManifestHashesUpdated": (
                game == "magireco_voice"
            ),
        },
    }
    report_payload = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    payloads[source_report_rel.as_posix()] = report_payload
    if reader.read(source_report_rel) == report_payload:
        report["changedPaths"] = [
            path
            for path in report["changedPaths"]
            if path != source_report_rel.as_posix()
        ]
        report_payload = (
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        payloads[source_report_rel.as_posix()] = report_payload

    if write:
        transactional_write(repo_root, payloads)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--txt", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--base-ref")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = materialize(
            args.txt,
            repo_root=args.repo_root,
            write=args.write,
            base_ref=args.base_ref,
        )
    except (
        MaterializeError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
