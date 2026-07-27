#!/usr/bin/env python3
"""Download Magia Record general voice scripts without GitHub Actions.

The immutable Cloudflare preview was built from:
HiiragiNemu/io.kamihama.totentanz/files/madomagi/resource/scenario/json/general
through MagiaExedraLive2DViewerPersonal commit
196f4bfcfa28c446539b4611e4cce7992b0c40d1.
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
SOURCE_COMMIT = "196f4bfcfa28c446539b4611e4cce7992b0c40d1"
MODEL_RE = re.compile(r"^\d{6}$")
MAX_BYTES = 2 * 1024 * 1024


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


def parse_json(data: bytes, label: str):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid UTF-8 JSON: {label}: {error}") from error


def clean(value, limit=20_000) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


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
                text = clean(chara.get("textHome")).replace("@", "／")
                if voice and voice not in voices:
                    voices.append(voice)
                if text:
                    texts.append(text)
        label = ", ".join(voices) or group_key
        body = " ".join(texts).strip() or f"语音资源：{label}"
        lines.append(f"{speaker}：【{label}｜{round(duration, 1):g}秒】{body}")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest_bytes = fetch("manifest.json")
    manifest = parse_json(manifest_bytes, "manifest.json")
    models = manifest.get("models") if isinstance(manifest, dict) else None
    if manifest.get("version") != 1 or not isinstance(models, list) or len(models) != 411:
        raise RuntimeError("unexpected general voice manifest version/count")
    if args.limit > 0:
        models = models[: args.limit]

    changed = 0
    provenance_models: list[dict] = []
    for index, model in enumerate(models, start=1):
        if not isinstance(model, dict) or not MODEL_RE.fullmatch(str(model.get("id") or "")):
            raise RuntimeError(f"invalid model at manifest index {index}")
        model_id = str(model["id"])
        if "cn" not in (model.get("langs") or {}):
            continue
        raw = fetch(f"cn/{model_id}.json")
        script = parse_json(raw, f"cn/{model_id}.json")
        encoded = json.dumps(script, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        txt = script_to_txt(script, model).encode("utf-8")
        changed += write_guarded(SOURCE_ROOT / model_id / f"{model_id}.json", encoded, check=args.check)
        changed += write_guarded(CN_ROOT / model_id / f"{model_id}.txt", txt, check=args.check)
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
        "modelCount": len(provenance_models),
        "models": provenance_models,
    }
    provenance_bytes = json.dumps(provenance, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    changed += write_guarded(SOURCE_ROOT / "general_voice_manifest.json", provenance_bytes, check=args.check)
    changed += write_guarded(CN_ROOT / "general_voice_manifest.json", provenance_bytes, check=args.check)
    print(f"general voice import complete: models={len(provenance_models)} changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
