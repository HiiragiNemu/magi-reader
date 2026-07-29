#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: patch target not found")
    return text.replace(old, new, 1)


def localize_character_index(root: Path, destination: Path) -> dict[str, int]:
    audio_path = destination / "character-index.json"
    structured_path = root / "data" / "structured" / "voice-index.json"
    audio_index = load(audio_path)
    structured = load(structured_path) if structured_path.exists() else []
    by_chara: dict[str, dict] = {}
    for item in structured:
        for chara_id in item.get("charaIds") or []:
            key = str(chara_id)
            current = by_chara.get(key)
            if current is None or int(item.get("lineCount") or 0) > int(current.get("lineCount") or 0):
                by_chara[key] = item

    localized = 0
    for item in audio_index:
        matched = by_chara.get(str(item.get("charaId")))
        if not matched:
            continue
        original_name = item.get("name") or ""
        item["englishName"] = original_name
        item["name"] = matched.get("title") or original_name
        item["baseName"] = matched.get("baseName") or item["name"]
        item["voiceActor"] = matched.get("voiceActor") or ""
        item["imageUrl"] = matched.get("imageUrl")
        item["structuredId"] = matched.get("id")
        localized += 1
    audio_index.sort(key=lambda item: (
        str(item.get("baseName") or item.get("name") or "").casefold(),
        str(item.get("name") or "").casefold(),
        str(item.get("charaId") or ""),
    ))
    dump(audio_path, audio_index)
    return {
        "records": len(audio_index),
        "localized": localized,
        "unmatched": len(audio_index) - localized,
    }


def integrate(root: Path, voice_source: Path, static: Path, revision: str) -> dict:
    destination = root / "data" / "voice-audio"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(voice_source, destination)
    localization = localize_character_index(root, destination)
    for name in ("audio-ui.js", "audio-ui.css"):
        shutil.copy2(static / name, root / name)

    # Reuse the existing visible Voice navigation rather than showing two
    # competing "语音" entries. The dedicated application owns #/audio.
    runtime_path = root / "audio-ui.js"
    runtime = runtime_path.read_text(encoding="utf-8")
    runtime = patch_once(
        runtime,
        "let button = nav.querySelector('[data-audio-nav]');",
        "let button = nav.querySelector('[data-audio-nav]') || nav.querySelector('[data-route=\"voice\"]');\n"
        "  if (button && !button.dataset.audioNav) { button.removeAttribute('data-route'); button.dataset.audioNav = 'true'; }",
        "voice navigation bridge",
    )
    runtime_path.write_text(runtime, encoding="utf-8")

    index_path = root / "index.html"
    index = index_path.read_text(encoding="utf-8")
    if "/audio-ui.css" not in index:
        index = patch_once(
            index,
            "</head>",
            f'  <link rel="stylesheet" href="/audio-ui.css?v={revision}">\n</head>',
            "audio stylesheet",
        )
    if "/audio-ui.js" not in index:
        index = patch_once(
            index,
            "</body>",
            f'  <script src="/audio-ui.js?v={revision}" defer></script>\n</body>',
            "audio runtime",
        )
    index_path.write_text(index, encoding="utf-8")

    manifest = load(destination / "manifest.json")
    manifest["localization"] = localization
    dump(destination / "manifest.json", manifest)
    health_path = root / "health.json"
    health = load(health_path)
    health.setdefault("counts", {})["audio"] = manifest["voiceFiles"]
    health["counts"]["voiceAudio"] = manifest["characterVoiceFiles"]
    health["counts"]["voiceAudioCharacters"] = manifest["characters"]
    health["voiceAudio"] = {
        "schemaVersion": manifest["schemaVersion"],
        "quotePages": manifest["quotePagesProcessed"],
        "files": manifest["voiceFiles"],
        "characters": manifest["characters"],
        "localizedCharacters": localization["localized"],
        "fandomFallbacks": manifest["fandomUrls"],
        "sourceOrder": ["github", "cn-cdn", "fandom"],
        "r2": False,
    }
    features = health.setdefault("uiFeatures", [])
    for value in (
        "full-character-voice-audio-index",
        "chinese-character-name-merge",
        "github-cdn-fandom-audio-fallback",
        "costume-and-line-audio-search",
        "single-active-audio-playback",
        "no-r2-audio-storage",
    ):
        if value not in features:
            features.append(value)
    dump(health_path, health)

    runtime_manifest_path = root / "data" / "runtime-manifest.json"
    if runtime_manifest_path.exists():
        runtime_manifest = load(runtime_manifest_path)
        runtime_manifest.setdefault("counts", {})["audio"] = manifest["voiceFiles"]
        runtime_manifest["counts"]["voiceAudioCharacters"] = manifest["characters"]
        runtime_manifest["voiceAudio"] = health["voiceAudio"]
        dump(runtime_manifest_path, runtime_manifest)

    # Versioned service worker already applies stale-while-revalidate to all
    # same-origin /data/*.json and JS/CSS, so no media binary enters Pages/R2.
    worker_path = root / f"sw-v{revision}.js"
    if worker_path.exists():
        worker = worker_path.read_text(encoding="utf-8")
        if "/audio-ui.js" not in worker and "const NETWORK_FIRST_PATHS = [" in worker:
            worker = worker.replace(
                "const NETWORK_FIRST_PATHS = [",
                "const NETWORK_FIRST_PATHS = [\n  '/audio-ui.js',\n  '/audio-ui.css',",
                1,
            )
            worker_path.write_text(worker, encoding="utf-8")

    return {"health": health, "voiceAudio": manifest, "localization": localization}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--voice-source", type=Path, required=True)
    parser.add_argument("--static", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    result = integrate(
        args.root.resolve(),
        args.voice_source.resolve(),
        args.static.resolve(),
        args.revision,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
