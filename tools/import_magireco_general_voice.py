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
import re
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
MAX_BYTES = 2 * 1024 * 1024
EXPECTED_PLAYABLE_MODELS = 410


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


def script_to_txt(script: dict, model: dict) -> str:
    story = script.get("story")
    if not isinstance(story, dict) or not story:
        raise RuntimeError(f"{model['id']}: missing story")
    character = model.get("char") or {}
    costume = model.get("costume") or {}
    speaker = clean(character.get("cn") or costume.get("cn") or f"模型{model['id']}", 160)
    lines: list[str] = []
    groups = sorted(story.items(), key=lambda item: int(item[0].removeprefix("group_")))
    for section, (group_key, turns) in enumerate(groups, start=1):
        if not re.fullmatch(r"group_\d+", group_key) or not isinstance(turns, list):
            raise RuntimeError(f"{model['id']}: invalid group {group_key}")
        lines.append(f"--- [Section {section}] (Source: {model['id']}.json) ---")
        voices: list[str] = []
        texts: list[str] = []
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
                text = (
                    clean(chara.get("textHome"))
                    .replace("\r\n", "@")
                    .replace("\r", "@")
                    .replace("\n", "@")
                    .replace("@", "／")
                )
                if voice and voice not in voices:
                    voices.append(voice)
                if text:
                    texts.append(text)
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
    path.write_bytes(data)
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
    rebuilt_models: list[dict] = []
    seen: set[str] = set()
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
        source_path = SOURCE_ROOT / model_id / f"{model_id}.json"
        raw = source_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != model.get("jsonSha256"):
            raise RuntimeError(f"existing JSON hash mismatch: {model_id}")
        script = normalize_script(
            parse_json(raw, f"{model_id}.json"),
            model_id,
        )
        if len(script["story"]) != int(model.get("groups") or -1):
            raise RuntimeError(f"existing group count mismatch: {model_id}")
        txt = script_to_txt(script, model).encode("utf-8")
        generated.append(
            (CN_ROOT / model_id / f"{model_id}_cn.txt", txt)
        )
        rebuilt_models.append(
            {
                **model,
                "jsonSha256": hashlib.sha256(raw).hexdigest(),
                "txtSha256": hashlib.sha256(txt).hexdigest(),
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
    changed = sum(
        write_guarded(path, data, check=check)
        for path, data in generated
    )
    print(
        "general voice local rebuild complete: "
        f"models={len(rebuilt_models)} changed={changed}"
    )
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
        generated.extend((
            (SOURCE_ROOT / model_id / f"{model_id}.json", encoded),
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
            "txtSha256": hashlib.sha256(txt).hexdigest(),
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
