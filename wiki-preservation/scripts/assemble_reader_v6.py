#!/usr/bin/env python3
"""Assemble the complete Reader v6 site from verified immutable artifacts.

Both pre-merge verification and production deployment call this script so the
validated output and the deployed output cannot silently diverge.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


STATIC_FILES = (
    "index.html",
    "app.js",
    "styles.css",
    "ui-v4-fixes.css",
    "ui-v4-runtime.js",
    "structured-ui.js",
    "structured-ui.css",
    "doppel-ui.js",
    "doppel-ui.css",
    "memoria-ui.js",
    "memoria-ui.css",
    "dense-reader.css",
    "dense-reader-compact.css",
    "sw.js",
)

VERSIONED_ASSETS = (
    "styles.css",
    "ui-v4-fixes.css",
    "structured-ui.css",
    "doppel-ui.css",
    "memoria-ui.css",
    "dense-reader.css",
    "dense-reader-compact.css",
    "ui-v4-runtime.js",
    "app.js",
    "structured-ui.js",
    "doppel-ui.js",
    "memoria-ui.js",
)

FORBIDDEN_VISITOR_COPY = (
    "把原 Wiki",
    "不会删减底层",
    "这里不是Wiki文章关键词筛选",
    "这里不是正文关键词筛选",
    "这里不是Wiki正文关键词筛选",
    "以保存快照中的普通记忆结晶目录为成员基准",
    "来源与保存说明",
    "本站用于研究",
    "兼容性开发",
)

NETWORK_FIRST_ASSETS = (
    "/app.js",
    "/ui-v4-runtime.js",
    "/structured-ui.js",
    "/doppel-ui.js",
    "/memoria-ui.js",
    "/styles.css",
    "/dense-reader.css",
    "/dense-reader-compact.css",
)


def run(script: Path, *args: str) -> None:
    command = [sys.executable, str(script), *map(str, args)]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def version_index(path: Path, revision: str) -> None:
    text = path.read_text(encoding="utf-8")
    for asset in VERSIONED_ASSETS:
        pattern = rf"/{re.escape(asset)}(?:\?[^\"'\s<]*)?"
        text, count = re.subn(pattern, f"/{asset}?v={revision}", text, count=1)
        if count != 1:
            raise RuntimeError(f"index does not reference {asset} exactly once: {count}")
    path.write_text(text, encoding="utf-8")


def assert_visitor_copy(root: Path) -> None:
    paths = [
        root / "index.html",
        root / "app.js",
        root / "structured-ui.js",
        root / "doppel-ui.js",
        root / "memoria-ui.js",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    found = [value for value in FORBIDDEN_VISITOR_COPY if value in text]
    if found:
        raise RuntimeError(f"internal/development copy leaked into visitor UI: {found}")


def update_health(root: Path, revision: str) -> dict:
    health_path = root / "health.json"
    health = load(health_path)
    structured_path = root / "data" / "structured" / "manifest.json"
    structured = load(structured_path)
    memoria = load(root / "data" / "structured" / "memoria-manifest.json")
    structured["memoria"] = memoria
    dump(structured_path, structured)

    health["uiVersion"] = 6
    health["uiRevision"] = revision
    health["portalClassification"] = "wiki-and-structured-catalogs"
    health["structured"] = structured
    health.setdefault("counts", {})["memoria"] = memoria["records"]
    health["uiFeatures"] = [
        "dense-wiki-desktop-layout",
        "restored-desktop-infobox-floats",
        "single-responsive-table-of-contents",
        "idle-chunked-article-enhancement",
        "root-only-runtime-observers",
        "structured-character-catalog",
        "native-audio-voice-player",
        "structured-doppel-catalog",
        "structured-memoria-catalog",
        "on-demand-memoria-detail-shards",
        "versioned-service-worker-file",
        "legacy-cache-eviction",
        "first-reload-cache-migration",
        "network-first-ui-assets",
        "offline-structured-indexes",
        "system-light-dark-eye-oled-themes",
        "font-and-content-width-controls",
    ]
    dump(health_path, health)
    dump(
        root / "ui-version.json",
        {
            "uiVersion": 6,
            "uiRevision": revision,
            "name": "dense-structured-magireco-database",
            "structured": structured,
        },
    )
    return health


def validate(root: Path, revision: str) -> dict:
    health = load(root / "health.json")
    manifest = load(root / "data" / "structured" / "manifest.json")
    characters = load(root / "data" / "structured" / "characters.json")
    voices = load(root / "data" / "structured" / "voice-index.json")
    doppels = load(root / "data" / "structured" / "doppel.json")
    memoria_manifest = load(root / "data" / "structured" / "memoria-manifest.json")
    memoria_index = load(root / "data" / "structured" / "memoria-index.json")

    if health["counts"]["pages"] != 500 or health["counts"]["images"] < 12000:
        raise RuntimeError(health)
    if health.get("uiVersion") != 6 or health.get("uiRevision") != revision:
        raise RuntimeError(health)
    if health["counts"].get("memoria") != 1042:
        raise RuntimeError(health)
    if manifest.get("characters", 0) < 235 or manifest.get("characterPages", 0) < 225:
        raise RuntimeError(manifest)
    if manifest.get("voiceCharacters", 0) < 220 or manifest.get("voiceLines", 0) < 16000 or manifest.get("voiceWithAudio", 0) < 16000:
        raise RuntimeError(manifest)
    if manifest.get("doppel") != 174 or manifest.get("doppelWithImage", 0) < 170:
        raise RuntimeError(manifest)
    if len(doppels) != 174 or len(voices) != manifest["voiceCharacters"]:
        raise RuntimeError("structured list size mismatch")
    if memoria_manifest.get("records") != 1042 or len(memoria_index) != 1042:
        raise RuntimeError(memoria_manifest)
    if memoria_manifest.get("withImage") != 1042 or memoria_manifest.get("withChineseName") != 1042:
        raise RuntimeError(memoria_manifest)
    if memoria_manifest.get("complete") != 1042 or memoria_manifest.get("partial") != 0:
        raise RuntimeError(memoria_manifest)
    if memoria_manifest.get("shards") != 16:
        raise RuntimeError(memoria_manifest)

    titles = {item["title"] for item in characters}
    doppel_characters = {item["character"] for item in doppels}
    if not {"七海八千代", "环伊吕波", "三穗野星罗", "千岁由麻"} <= titles:
        raise RuntimeError("known character missing")
    if not {"七海八千代", "环伊吕波", "千岁由麻"} <= doppel_characters:
        raise RuntimeError("known Doppel missing")
    if "Ablaze" in titles:
        raise RuntimeError("non-character page leaked into character catalog")

    yachiyo = next(item for item in characters if item["title"] == "七海八千代")
    voice_lines = load(root / "data" / "structured" / "voice" / f"{yachiyo['voiceKey']}.json")
    if not any(item.get("voiceId") == "Vo_char_1002_00_01" for item in voice_lines):
        raise RuntimeError("known voice line missing")
    memoria_titles = {item["nameJa"] for item in memoria_index}
    if not {"1000円未満の魔法", "1000年の眠りを超えて"} <= memoria_titles:
        raise RuntimeError("known Memoria missing")
    for shard in "0123456789abcdef":
        path = root / "data" / "structured" / "memoria" / f"{shard}.json"
        if not path.exists() or not isinstance(load(path), dict):
            raise RuntimeError(f"invalid Memoria shard: {path}")

    index = (root / "index.html").read_text(encoding="utf-8")
    for asset in VERSIONED_ASSETS:
        if f"/{asset}?v={revision}" not in index:
            raise RuntimeError(f"versioned asset missing: {asset}")
    if "reader-version-cache-bootstrap" not in index:
        raise RuntimeError("version-scoped cache bootstrap missing")
    if "--site-max: 1760px" not in (root / "dense-reader.css").read_text(encoding="utf-8"):
        raise RuntimeError("dense desktop layout missing")
    if "repeat(5, minmax(0, 1fr))" not in (root / "dense-reader-compact.css").read_text(encoding="utf-8"):
        raise RuntimeError("dense Memoria grid missing")
    if "requestIdleCallback" not in (root / "app.js").read_text(encoding="utf-8"):
        raise RuntimeError("idle article enhancement missing")
    for name in ("structured-ui.js", "doppel-ui.js", "memoria-ui.js"):
        if "subtree: false" not in (root / name).read_text(encoding="utf-8"):
            raise RuntimeError(f"root-only observer missing: {name}")
    worker = (root / f"sw-v{revision}.js").read_text(encoding="utf-8")
    if "NETWORK_FIRST_PATHS" not in worker:
        raise RuntimeError("network-first update policy missing")
    for path in NETWORK_FIRST_ASSETS:
        if path not in worker:
            raise RuntimeError(f"critical asset missing from network-first policy: {path}")
    assert_visitor_copy(root)
    return {
        "health": health,
        "structured": manifest,
        "memoria": memoria_manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--static", type=Path, required=True)
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--memoria", type=Path, required=True)
    parser.add_argument("--revision", default="6.2")
    args = parser.parse_args()

    root = args.snapshot.resolve()
    static = args.static.resolve()
    scripts = args.scripts.resolve()
    memoria = args.memoria.resolve()
    for name in STATIC_FILES:
        source = static / name
        if not source.exists():
            raise RuntimeError(f"missing static source: {source}")
        shutil.copy2(source, root / name)

    run(scripts / "patch_structured_runtime.py", root / "structured-ui.js")
    run(scripts / "reclassify_portals.py", root)
    run(scripts / "extract_structured_characters.py", root)
    run(scripts / "extract_structured_doppel.py", root)
    run(
        scripts / "prepare_memoria_runtime.py",
        "--source", memoria,
        "--output", root / "data" / "structured",
        "--archive-index", root / "data" / "archive-index.json",
    )
    run(scripts / "patch_dense_reader.py", root)
    version_index(root / "index.html", args.revision)
    update_health(root, args.revision)
    run(scripts / "patch_offline_runtime.py", root, "--revision", args.revision)
    run(scripts / "patch_update_bootstrap.py", root, "--revision", args.revision)
    result = validate(root, args.revision)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
