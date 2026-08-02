#!/usr/bin/env python3
"""Download Magia Record general voice scripts without GitHub Actions.

The immutable Cloudflare preview was built from:
HiiragiNemu/io.kamihama.totentanz/files/madomagi/resource/scenario/json/general
through MagiaExedraLive2DViewerPersonal commit
6d921b630f41341a1c5aba66ec355ef9017e778d.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "magireco-voice-source-master/Scenarios_full/general_voice"
CN_ROOT = ROOT / "magireco-voice-translate-data-master/Scenarios_full/general_voice"
UPSTREAMS = (
    "https://566b00b8.magiaexedralive2dviewer.pages.dev/story/general",
    "https://feature-story-playback-local.magiaexedralive2dviewer.pages.dev/story/general",
)
SOURCE_COMMIT = "6d921b630f41341a1c5aba66ec355ef9017e778d"
MODEL_RE = re.compile(r"^\d{6}$")
WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
MAX_BYTES = 2 * 1024 * 1024
EXPECTED_PLAYABLE_MODELS = 410
MIGRATION_REPORT = ROOT / "reports/general_voice_cn_json_migration.json"


def fetch(relative: str, retries: int = 4) -> bytes:
    last: Exception | None = None
    for base in UPSTREAMS:
        for attempt in range(retries):
            try:
                request = urllib.request.Request(
                    f"{base}/{relative}",
                    headers={"Accept": "application/json", "User-Agent": "MagiReader-voice-import/1"},
                )
                with urllib.request.urlopen(request, timeout=60) as response:
                    declared = int(response.headers.get("Content-Length") or 0)
                    if declared > MAX_BYTES:
                        raise RuntimeError(f"upstream object too large: {relative}")
                    data = response.read(MAX_BYTES + 1)
                    if len(data) > MAX_BYTES:
                        raise RuntimeError(f"upstream object too large: {relative}")
                    return data
            except (OSError, urllib.error.URLError, RuntimeError) as error:
                last = error
                time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"cannot download {relative}: {last}")


def read_local(root: Path, relative: str) -> bytes:
    candidate = root.joinpath(*relative.split("/"))
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"local source escaped its root: {relative}") from error
    if not candidate.is_file() or candidate.is_symlink():
        raise RuntimeError(f"missing regular local source: {candidate}")
    data = candidate.read_bytes()
    if len(data) > MAX_BYTES:
        raise RuntimeError(f"local source object too large: {relative}")
    return data


def parse_json(data: bytes, label: str):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid UTF-8 JSON: {label}: {error}") from error


def clean(value, limit=20_000) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def safe_folder_component(value: object, *, limit: int) -> str:
    text = clean(value, limit * 2)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")[:limit].rstrip(" .")
    if not text or text.casefold() in WINDOWS_RESERVED_NAMES:
        raise RuntimeError(f"unsafe empty/reserved folder component: {value!r}")
    return text


def _localized_name(entry: dict, field: str, language: str) -> str:
    value = entry.get(field)
    if not isinstance(value, dict):
        return ""
    return clean(value.get(language), 160)


def build_hierarchy_metadata(models: list[dict]) -> dict[str, dict]:
    """Build deterministic readable repository paths and combo aliases."""

    by_family: dict[str, list[dict]] = {}
    for model in models:
        model_id = str(model.get("id") or "")
        if not MODEL_RE.fullmatch(model_id):
            raise RuntimeError(f"invalid model id in hierarchy: {model_id!r}")
        by_family.setdefault(model_id[:4], []).append(model)

    result: dict[str, dict] = {}
    for family_id, members in sorted(by_family.items()):
        members = sorted(members, key=lambda item: str(item["id"]))
        cn_names: list[str] = []
        jp_names: list[str] = []
        for model in members:
            cn = _localized_name(model, "char", "cn")
            jp = _localized_name(model, "char", "jp")
            if cn and cn not in cn_names:
                cn_names.append(cn)
            if jp and jp not in jp_names:
                jp_names.append(jp)
        family_cn = "＆".join(cn_names) or family_id
        family_jp = "＆".join(jp_names)
        family_label = f"{family_id} - {family_cn}"
        if family_jp:
            family_label += f"（{family_jp}）"
        family_folder = safe_folder_component(family_label, limit=64)

        base_id = f"{family_id}00"
        base = next((model for model in members if model["id"] == base_id), None)
        is_combo_family = bool(
            len(members) > 1
            and base
            and isinstance(base.get("rawVoiceReferences"), int)
            and isinstance(base.get("voiceGroups"), int)
            and base["rawVoiceReferences"] > base["voiceGroups"]
        )
        component_ids = (
            [str(model["id"]) for model in members if model["id"] != base_id]
            if is_combo_family else []
        )
        for model in members:
            model_id = str(model["id"])
            costume_cn = _localized_name(model, "costume", "cn")
            costume_jp = _localized_name(model, "costume", "jp")
            model_cn = costume_cn or _localized_name(model, "char", "cn") or model_id
            model_label = f"{model_id} - {model_cn}"
            if costume_jp and costume_jp != model_cn:
                model_label += f"（{costume_jp}）"
            if is_combo_family and model_id == base_id:
                model_label += " - 组合看板"
            model_folder = safe_folder_component(model_label, limit=84)
            relative_dir = Path(family_folder, model_folder).as_posix()
            canonical_id = base_id if is_combo_family else model_id
            result[model_id] = {
                "familyId": family_id,
                "familyFolder": family_folder,
                "modelFolder": model_folder,
                "repositoryRelativeDir": relative_dir,
                "sourceRelativePath": f"{relative_dir}/{model_id}.json",
                "cnJsonRelativePath": f"{relative_dir}/{model_id}_cn.json",
                "cnTxtRelativePath": f"{relative_dir}/{model_id}_cn.txt",
                "publishedModel": model_id == canonical_id,
                "canonicalModelId": canonical_id,
                "componentModelIds": component_ids if model_id == canonical_id else [],
            }
    return result


def _existing_model_path(
    root: Path,
    *,
    model: dict,
    field: str,
    target_relative: str,
    legacy_relative: str,
) -> Path:
    candidates: list[Path] = []
    for relative in (model.get(field), target_relative, legacy_relative):
        if not isinstance(relative, str) or not relative:
            continue
        candidate = root.joinpath(*Path(relative).parts)
        if candidate not in candidates and candidate.is_file() and not candidate.is_symlink():
            candidates.append(candidate)
    if not candidates:
        raise RuntimeError(f"missing model file: {model.get('id')} {field}")
    preferred = root.joinpath(*Path(target_relative).parts)
    if preferred in candidates:
        reference = preferred.read_bytes()
        if any(candidate.read_bytes() != reference for candidate in candidates):
            raise RuntimeError(f"conflicting legacy/target copies: {model.get('id')} {field}")
        return preferred
    if len(candidates) > 1:
        reference = candidates[0].read_bytes()
        if any(candidate.read_bytes() != reference for candidate in candidates[1:]):
            raise RuntimeError(f"ambiguous existing copies: {model.get('id')} {field}")
    return candidates[0]


def normalize_script(script: dict, model_id: str) -> dict:
    story = script.get("story")
    if not isinstance(story, dict) or not story:
        raise RuntimeError(f"{model_id}: missing story")
    normalized: dict[str, object] = {}
    for raw_key, turns in story.items():
        typo = re.fullmatch(r"gropu_(\d+)", str(raw_key))
        key = f"group_{typo.group(1)}" if typo else str(raw_key)
        if (
            not re.fullmatch(r"group_\d+", key)
            or key in normalized
            or not isinstance(turns, list)
        ):
            raise RuntimeError(f"{model_id}: invalid group {raw_key}")
        normalized[key] = turns
    return {**script, "story": normalized}


def ordered_groups(script: dict, model_id: str) -> list[tuple[str, list]]:
    story = script.get("story")
    if not isinstance(story, dict) or not story:
        raise RuntimeError(f"{model_id}: missing story")
    groups: list[tuple[str, list]] = []
    for key in sorted(
        story,
        key=lambda value: int(str(value).removeprefix("group_"))
        if re.fullmatch(r"group_\d+", str(value))
        else -1,
    ):
        turns = story[key]
        if not re.fullmatch(r"group_\d+", key) or not isinstance(turns, list):
            raise RuntimeError(f"{model_id}: invalid group {key}")
        groups.append((key, turns))
    return groups


def first_voice_character(turns: list) -> dict | None:
    """Return the first playback event carrying a voice resource.

    Some duo/card scripts repeat one voice resource on two character objects so
    both Live2D models lip-sync.  Those duplicates are one subtitle unit, not
    two translations.  Coverage therefore follows the first voice-bearing
    character in each group, which is also where the game reads ``textHome``.
    """

    for turn in turns:
        if not isinstance(turn, dict):
            continue
        charas = turn.get("chara")
        if not isinstance(charas, list):
            continue
        for chara in charas:
            if (
                isinstance(chara, dict)
                and isinstance(chara.get("voice"), str)
                and chara["voice"].strip()
            ):
                return chara
    return None


def voice_translation_stats(script: dict, model_id: str) -> dict[str, int]:
    total = 0
    translated = 0
    raw_voice_references = 0
    groups_without_voice = 0
    for _group_key, turns in ordered_groups(script, model_id):
        first = first_voice_character(turns)
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("chara"), list):
                continue
            raw_voice_references += sum(
                1
                for chara in turn["chara"]
                if isinstance(chara, dict)
                and isinstance(chara.get("voice"), str)
                and chara["voice"].strip()
            )
        if first is None:
            groups_without_voice += 1
            continue
        total += 1
        if isinstance(first.get("textHome"), str) and first["textHome"].strip():
            translated += 1
    return {
        "voiceGroups": total,
        "translatedVoiceGroups": translated,
        "untranslatedVoiceGroups": total - translated,
        "rawVoiceReferences": raw_voice_references,
        "groupsWithoutVoice": groups_without_voice,
        "translationPercent": round(translated * 100 / total) if total else 0,
    }


def logical_text_home_values(turns: list, model_id: str, group_key: str) -> list[str]:
    """Return distinct subtitle segments while validating duplicated voices.

    Duo/ensemble cards repeat the same voice and textHome on multiple Live2D
    characters for lip sync.  Those mirrors are one editable subtitle.  Later
    textHome-only turns remain independent segments in playback order.
    """

    voice_characters: list[dict] = []
    voice_ids: list[str] = []
    continuation_values: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        for chara in turn.get("chara") or []:
            if not isinstance(chara, dict):
                continue
            voice = clean(chara.get("voice"), 256)
            text = clean(chara.get("textHome"))
            if voice:
                voice_characters.append(chara)
                if voice not in voice_ids:
                    voice_ids.append(voice)
            elif text and text not in continuation_values:
                continuation_values.append(text)
    if len(voice_ids) > 1:
        raise RuntimeError(
            f"{model_id}/{group_key}: multiple unique voice resources: {voice_ids}"
        )
    voice_texts: list[str] = []
    for chara in voice_characters:
        text = clean(chara.get("textHome"))
        if text and text not in voice_texts:
            voice_texts.append(text)
    if len(voice_texts) > 1:
        raise RuntimeError(
            f"{model_id}/{group_key}: duplicated voice textHome conflict"
        )
    logical_values: list[str] = []
    if voice_characters:
        # A voice-bearing group always owns one editable subtitle row.  The
        # empty string is deliberate: it renders the immutable resource label
        # with an empty body and lets proofreading add textHome later.
        logical_values.append(voice_texts[0] if voice_texts else "")
    logical_values.extend(continuation_values)
    return logical_values


def script_to_txt(script: dict, model: dict) -> str:
    character = model.get("char") or {}
    costume = model.get("costume") or {}
    speaker = clean(character.get("cn") or costume.get("cn") or f"模型{model['id']}", 160)
    lines: list[str] = []
    groups = ordered_groups(script, str(model["id"]))
    for section, (group_key, turns) in enumerate(groups, start=1):
        lines.append(f"--- [Section {section}] (Source: {model['id']}.json) ---")
        voices: list[str] = []
        texts = logical_text_home_values(turns, str(model["id"]), group_key)
        duration = 0.0
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            first = turn.get("autoTurnFirst")
            last = turn.get("autoTurnLast")
            duration += float(first if isinstance(first, (int, float)) else last if isinstance(last, (int, float)) else 0)
            for chara in turn.get("chara") or []:
                if not isinstance(chara, dict):
                    continue
                voice = clean(chara.get("voice"), 256)
                if voice and voice not in voices:
                    voices.append(voice)
        texts = [
            text.replace("\r\n", "@").replace("\r", "@").replace("\n", "@").replace("@", "／")
            for text in texts
        ]
        label = ", ".join(voices) or group_key
        duration_label = f"{round(duration, 1):g}秒"
        if not texts:
            lines.append(
                f"{speaker}：【{label}｜{duration_label}】语音资源：{label}"
            )
        elif len(texts) == 1:
            lines.append(
                f"{speaker}：【{label}｜{duration_label}】{texts[0]}"
            )
        else:
            for position, text in enumerate(texts, 1):
                lines.append(
                    f"{speaker}：【{label}｜{duration_label}｜"
                    f"文本 {position}/{len(texts)}】{text}"
                )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_guarded(path: Path, data: bytes, *, check: bool) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    if check:
        raise RuntimeError(f"generated file is stale or missing: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def rebuild_existing(*, check: bool) -> int:
    """Rebuild canonical TXT and both manifests from audited local JSON."""

    source_manifest_path = SOURCE_ROOT / "general_voice_manifest.json"
    cn_manifest_path = CN_ROOT / "general_voice_manifest.json"
    source_manifest_bytes = source_manifest_path.read_bytes()
    cn_manifest_bytes = cn_manifest_path.read_bytes()
    if source_manifest_bytes != cn_manifest_bytes:
        raise RuntimeError("source/translation general voice manifests differ")
    manifest = parse_json(
        source_manifest_bytes,
        "general_voice_manifest.json",
    )
    models = manifest.get("models") if isinstance(manifest, dict) else None
    if (
        manifest.get("version") != 1
        or manifest.get("modelCount") != EXPECTED_PLAYABLE_MODELS
        or not isinstance(models, list)
        or len(models) != EXPECTED_PLAYABLE_MODELS
    ):
        raise RuntimeError("unexpected existing general voice manifest")

    generated: list[tuple[Path, bytes]] = []
    moves: list[tuple[Path, Path]] = []
    rebuilt_models: list[dict] = []
    seen: set[str] = set()
    hierarchy = build_hierarchy_metadata(models)
    for index, model in enumerate(models, 1):
        if (
            not isinstance(model, dict)
            or not MODEL_RE.fullmatch(str(model.get("id") or ""))
        ):
            raise RuntimeError(f"invalid existing model at index {index}")
        model_id = str(model["id"])
        if model_id in seen:
            raise RuntimeError(f"duplicate existing model: {model_id}")
        seen.add(model_id)
        metadata = hierarchy[model_id]
        source_target = SOURCE_ROOT.joinpath(*Path(metadata["sourceRelativePath"]).parts)
        cn_json_target = CN_ROOT.joinpath(*Path(metadata["cnJsonRelativePath"]).parts)
        cn_txt_target = CN_ROOT.joinpath(*Path(metadata["cnTxtRelativePath"]).parts)
        source_path = _existing_model_path(
            SOURCE_ROOT,
            model=model,
            field="sourceRelativePath",
            target_relative=metadata["sourceRelativePath"],
            legacy_relative=f"{model_id}/{model_id}.json",
        )
        cn_json_path = _existing_model_path(
            CN_ROOT,
            model=model,
            field="cnJsonRelativePath",
            target_relative=metadata["cnJsonRelativePath"],
            legacy_relative=f"{model_id}/{model_id}_cn.json",
        )
        cn_txt_path = _existing_model_path(
            CN_ROOT,
            model=model,
            field="cnTxtRelativePath",
            target_relative=metadata["cnTxtRelativePath"],
            legacy_relative=f"{model_id}/{model_id}_cn.txt",
        )
        source_raw = source_path.read_bytes()
        if hashlib.sha256(source_raw).hexdigest() != model.get("jsonSha256"):
            raise RuntimeError(f"existing JSON hash mismatch: {model_id}")
        cn_raw = cn_json_path.read_bytes()
        expected_cn_hash = model.get("cnJsonSha256")
        if expected_cn_hash and hashlib.sha256(cn_raw).hexdigest() != expected_cn_hash:
            raise RuntimeError(f"existing CN JSON hash mismatch: {model_id}")
        script = normalize_script(
            parse_json(cn_raw, f"{model_id}_cn.json"),
            model_id,
        )
        if len(script["story"]) != int(model.get("groups") or -1):
            raise RuntimeError(f"existing group count mismatch: {model_id}")
        txt = script_to_txt(script, model).encode("utf-8")
        stats = voice_translation_stats(script, model_id)
        generated.append((cn_txt_target, txt))
        generated.append((cn_json_target, cn_raw))
        for current, target in (
            (source_path, source_target),
            (cn_json_path, cn_json_target),
            (cn_txt_path, cn_txt_target),
        ):
            if current != target:
                moves.append((current, target))
        rebuilt_models.append(
            {
                **model,
                **metadata,
                "jsonSha256": hashlib.sha256(source_raw).hexdigest(),
                "sourceJsonSha256": hashlib.sha256(source_raw).hexdigest(),
                "cnJsonSha256": hashlib.sha256(cn_raw).hexdigest(),
                "txtSha256": hashlib.sha256(txt).hexdigest(),
                **stats,
            }
        )

    rebuilt_manifest = {
        **manifest,
        "modelCount": len(rebuilt_models),
        "models": rebuilt_models,
    }
    rebuilt_manifest_bytes = (
        json.dumps(rebuilt_manifest, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
    generated.extend(
        (
            (source_manifest_path, rebuilt_manifest_bytes),
            (cn_manifest_path, rebuilt_manifest_bytes),
        )
    )
    if moves and check:
        raise RuntimeError(
            f"general voice hierarchy is stale: {moves[0][0]} -> {moves[0][1]}"
        )
    for source, target in moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise RuntimeError(f"refusing to overwrite different target: {target}")
            source.unlink()
        else:
            os.replace(source, target)

    changed = len(moves) + sum(
        write_guarded(path, data, check=check)
        for path, data in generated
    )
    for root in (SOURCE_ROOT, CN_ROOT):
        for candidate in root.iterdir():
            if candidate.is_dir() and MODEL_RE.fullmatch(candidate.name):
                try:
                    candidate.rmdir()
                except OSError:
                    pass
    print(
        "general voice local rebuild complete: "
        f"models={len(rebuilt_models)} changed={changed} "
        f"translated={sum(item['translatedVoiceGroups'] for item in rebuilt_models)}/"
        f"{sum(item['voiceGroups'] for item in rebuilt_models)}"
    )
    report = {
        "schemaVersion": 1,
        "operation": "general_voice_cn_json_and_readable_hierarchy_migration",
        "playableModels": len(rebuilt_models),
        "upstreamJsonFiles": len(rebuilt_models) + 1,
        "rejected": [
            {
                "id": "xxxx",
                "reason": "non_numeric_placeholder_not_a_playable_model",
            }
        ],
        "voiceGroups": sum(item["voiceGroups"] for item in rebuilt_models),
        "translatedVoiceGroups": sum(
            item["translatedVoiceGroups"] for item in rebuilt_models
        ),
        "untranslatedVoiceGroups": sum(
            item["untranslatedVoiceGroups"] for item in rebuilt_models
        ),
        "groupsWithoutVoice": sum(
            item["groupsWithoutVoice"] for item in rebuilt_models
        ),
        "rawVoiceReferences": sum(
            item["rawVoiceReferences"] for item in rebuilt_models
        ),
        "models": [
            {
                key: item[key]
                for key in (
                    "id",
                    "voiceGroups",
                    "translatedVoiceGroups",
                    "untranslatedVoiceGroups",
                    "groupsWithoutVoice",
                    "rawVoiceReferences",
                    "translationPercent",
                    "sourceJsonSha256",
                    "cnJsonSha256",
                    "txtSha256",
                    "familyId",
                    "familyFolder",
                    "modelFolder",
                    "sourceRelativePath",
                    "cnJsonRelativePath",
                    "cnTxtRelativePath",
                    "publishedModel",
                    "canonicalModelId",
                    "componentModelIds",
                )
            }
            for item in rebuilt_models
        ],
    }
    report_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    write_guarded(MIGRATION_REPORT, report_bytes, check=check)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--rebuild-existing",
        action="store_true",
        help=(
            "从已审计本地 JSON 重建规范 TXT 与两份哈希清单，"
            "不访问网络"
        ),
    )
    parser.add_argument(
        "--local-root",
        type=Path,
        help=(
            "读取已生成的 story/general 目录（含 manifest.json 与 cn/），"
            "不访问网络"
        ),
    )
    args = parser.parse_args()

    if args.rebuild_existing:
        if args.local_root is not None or args.limit:
            raise RuntimeError(
                "--rebuild-existing cannot be combined with --local-root/--limit"
            )
        return rebuild_existing(check=args.check)

    local_root = args.local_root.resolve() if args.local_root else None
    if local_root is not None and (
        not local_root.is_dir() or local_root.is_symlink()
    ):
        raise RuntimeError(f"invalid local story/general root: {local_root}")
    load = (
        (lambda relative: read_local(local_root, relative))
        if local_root is not None
        else fetch
    )

    manifest_bytes = load("manifest.json")
    manifest = parse_json(manifest_bytes, "manifest.json")
    models = manifest.get("models") if isinstance(manifest, dict) else None
    if (
        manifest.get("version") != 1
        or not isinstance(models, list)
        or len(models) != EXPECTED_PLAYABLE_MODELS
    ):
        raise RuntimeError("unexpected general voice manifest version/count")
    if args.limit > 0:
        models = models[: args.limit]

    generated: list[tuple[Path, bytes]] = []
    provenance_models: list[dict] = []
    for index, model in enumerate(models, start=1):
        if not isinstance(model, dict) or not MODEL_RE.fullmatch(str(model.get("id") or "")):
            raise RuntimeError(f"invalid model at manifest index {index}")
        model_id = str(model["id"])
        if "cn" not in (model.get("langs") or {}):
            continue
        raw = load(f"cn/{model_id}.json")
        script = normalize_script(
            parse_json(raw, f"cn/{model_id}.json"),
            model_id,
        )
        encoded = json.dumps(script, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        txt = script_to_txt(script, model).encode("utf-8")
        stats = voice_translation_stats(script, model_id)
        generated.extend((
            (SOURCE_ROOT / model_id / f"{model_id}.json", encoded),
            (CN_ROOT / model_id / f"{model_id}_cn.json", encoded),
            (CN_ROOT / model_id / f"{model_id}_cn.txt", txt),
        ))
        provenance_models.append({
            "id": model_id,
            "charId": model.get("charId"),
            "char": model.get("char"),
            "costume": model.get("costume"),
            "groups": model["langs"]["cn"]["groups"],
            "voices": model["langs"]["cn"]["voices"],
            "jsonSha256": hashlib.sha256(encoded).hexdigest(),
            "sourceJsonSha256": hashlib.sha256(encoded).hexdigest(),
            "cnJsonSha256": hashlib.sha256(encoded).hexdigest(),
            "txtSha256": hashlib.sha256(txt).hexdigest(),
            **stats,
        })
        if index % 25 == 0:
            print(f"imported {index}/{len(models)}")

    provenance = {
        "version": 1,
        "sourceCommit": SOURCE_COMMIT,
        "upstreams": list(UPSTREAMS),
        "inputMode": "local" if local_root is not None else "network",
        "modelCount": len(provenance_models),
        "models": provenance_models,
    }
    provenance_bytes = json.dumps(provenance, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    generated.extend((
        (SOURCE_ROOT / "general_voice_manifest.json", provenance_bytes),
        (CN_ROOT / "general_voice_manifest.json", provenance_bytes),
    ))
    changed = sum(
        write_guarded(path, data, check=args.check)
        for path, data in generated
    )
    print(f"general voice import complete: models={len(provenance_models)} changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
