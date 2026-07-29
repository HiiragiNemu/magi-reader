#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, unquote

import requests
from bs4 import BeautifulSoup, Tag

FANDOM = "https://magireco.fandom.com"
FANDOM_API = f"{FANDOM}/api.php"
GITHUB_RAW = "https://raw.githubusercontent.com/HiiragiNemu/magiWiki/main/images"
CN_CDN = "https://cdn.mfjl.wiki"
VOICE_TOKEN_RE = re.compile(
    r"(Vo_(?:char|game)_[A-Za-z0-9_-]+)\.(?:ogg|oga|mp3)",
    re.I,
)
CHAR_RE = re.compile(r"^Vo_char_(\d+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)$", re.I)


def canonical_stem(value: str) -> str:
    value = value.replace(" ", "_")
    if value.lower().startswith("vo_"):
        value = "Vo_" + value[3:]
    return value


def canonical_mp3(stem: str) -> str:
    return f"{canonical_stem(stem)}.mp3"


def media_urls(mp3_name: str, fandom_url: str | None) -> list[dict[str, str]]:
    digest = hashlib.md5(mp3_name.encode("utf-8")).hexdigest()
    encoded = "/".join(quote(part, safe="()!$&'*,;=@~+-._") for part in mp3_name.split("/"))
    sources = [
        {
            "kind": "github",
            "type": "audio/mpeg",
            "url": f"{GITHUB_RAW}/{digest[0]}/{digest[:2]}/{encoded}",
        },
        {
            "kind": "cn-cdn",
            "type": "audio/mpeg",
            "url": f"{CN_CDN}/{digest[0]}/{digest[:2]}/{encoded}",
        },
    ]
    if fandom_url:
        sources.append({"kind": "fandom", "type": "audio/ogg", "url": fandom_url})
    return sources


def api(session: requests.Session, **params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    response = session.get(FANDOM_API, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload


def list_quote_pages(session: requests.Session) -> list[str]:
    titles: list[str] = []
    cont: dict[str, str] = {}
    while True:
        payload = api(session, action="query", list="allpages", apnamespace=0, aplimit="max", **cont)
        for page in payload.get("query", {}).get("allpages", []):
            title = page.get("title", "")
            if title.endswith("/Quotes"):
                titles.append(title)
        if "continue" not in payload:
            break
        cont = payload["continue"]
    return sorted(set(titles))


def list_page_media_titles(session: requests.Session, page_title: str) -> list[str]:
    titles: list[str] = []
    cont: dict[str, str] = {}
    while True:
        payload = api(
            session,
            action="query",
            prop="images",
            titles=page_title,
            imlimit="max",
            **cont,
        )
        for page in payload.get("query", {}).get("pages", []):
            titles.extend(
                item.get("title", "")
                for item in page.get("images", [])
                if item.get("title")
            )
        if "continue" not in payload:
            break
        cont = payload["continue"]
    return titles


def decoded_markup(value: str) -> str:
    previous = value
    for _ in range(3):
        current = unquote(html_lib.unescape(previous))
        if current == previous:
            break
        previous = current
    return previous.replace("\/", "/")


def clean_label(node: Tag | None, filename: str) -> str:
    if node is None:
        return filename
    text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
    text = VOICE_TOKEN_RE.sub("", text)
    return text[:1600] or filename


def html_labels(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    labels: dict[str, str] = {}
    for row in soup.select("tr, li"):
        serialized = decoded_markup(str(row))
        for match in VOICE_TOKEN_RE.finditer(serialized):
            stem = canonical_stem(match.group(1))
            labels.setdefault(stem.casefold(), clean_label(row, f"{stem}.ogg"))
    return labels


def extract_file_records(session: requests.Session, page_title: str) -> list[dict]:
    parse_payload = api(session, action="parse", page=page_title, prop="text|displaytitle")
    html = parse_payload.get("parse", {}).get("text", "")
    labels = html_labels(html)
    actual_titles = list_page_media_titles(session, page_title)
    records: list[dict] = []
    seen: set[str] = set()

    # MediaWiki's page image list supplies canonical File titles. This is more
    # reliable than reconstructing them from Fandom player attributes.
    for title in actual_titles:
        bare = title.split(":", 1)[-1].replace(" ", "_")
        match = VOICE_TOKEN_RE.search(decoded_markup(bare))
        if not match:
            continue
        stem = canonical_stem(match.group(1))
        mp3_name = canonical_mp3(stem)
        if mp3_name in seen:
            continue
        seen.add(mp3_name)
        records.append({
            "pageTitle": page_title,
            "characterName": page_title.removesuffix("/Quotes").replace("_", " "),
            "fandomFileTitle": title,
            "mp3Filename": mp3_name,
            "label": labels.get(stem.casefold(), mp3_name),
        })

    # Fallback for audio player references omitted from prop=images.
    decoded = decoded_markup(html)
    for match in VOICE_TOKEN_RE.finditer(decoded):
        stem = canonical_stem(match.group(1))
        mp3_name = canonical_mp3(stem)
        if mp3_name in seen:
            continue
        seen.add(mp3_name)
        records.append({
            "pageTitle": page_title,
            "characterName": page_title.removesuffix("/Quotes").replace("_", " "),
            "fandomFileTitle": f"File:{stem}.ogg",
            "mp3Filename": mp3_name,
            "label": labels.get(stem.casefold(), mp3_name),
        })
    return records


def enrich_fandom_urls(session: requests.Session, records: list[dict]) -> None:
    by_title = {record["fandomFileTitle"]: record for record in records}
    titles = list(by_title)
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]
        payload = api(
            session,
            action="query",
            prop="imageinfo",
            iiprop="url|mime|size",
            titles="|".join(batch),
        )
        for page in payload.get("query", {}).get("pages", []):
            title = page.get("title")
            info = (page.get("imageinfo") or [{}])[0]
            record = by_title.get(title)
            if not record:
                continue
            record["fandomUrl"] = info.get("url")
            record["fandomMime"] = info.get("mime")
            record["fandomSize"] = info.get("size")
        time.sleep(0.12)


def build(output: Path, max_pages: int | None) -> dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "MagirecoChinesePreservationReader/6.1 (+https://github.com/HiiragiNemu/magi-reader)",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7,ja;q=0.5",
    })
    discovered_pages = list_quote_pages(session)
    pages = discovered_pages[:max_pages] if max_pages else discovered_pages
    all_records: list[dict] = []
    failures: list[dict] = []
    for index, title in enumerate(pages, 1):
        try:
            records = extract_file_records(session, title)
            all_records.extend(records)
            print(f"{index}/{len(pages)} {title}: {len(records)} voice files", flush=True)
        except Exception as exc:
            failures.append({"page": title, "error": repr(exc)})
        time.sleep(0.18)
    enrich_fandom_urls(session, all_records)

    unique: dict[str, dict] = {}
    for record in all_records:
        unique.setdefault(record["mp3Filename"], record)
    records = list(unique.values())
    by_character: dict[str, list[dict]] = defaultdict(list)
    game_records: list[dict] = []
    for record in records:
        stem = record["mp3Filename"][:-4]
        match = CHAR_RE.match(stem)
        record["sources"] = media_urls(record["mp3Filename"], record.get("fandomUrl"))
        if match:
            record["charaId"], record["costumeId"], record["slot"] = match.groups()
            by_character[record["charaId"]].append(record)
        else:
            record["kind"] = "game"
            game_records.append(record)

    output.mkdir(parents=True, exist_ok=True)
    character_index = []
    for chara_id, items in sorted(by_character.items()):
        items.sort(key=lambda item: (
            item.get("costumeId", ""),
            item.get("slot", ""),
            item["mp3Filename"],
        ))
        names = [item["characterName"] for item in items if item.get("characterName")]
        name = max(set(names), key=names.count) if names else f"角色 {chara_id}"
        costumes = sorted({item.get("costumeId", "") for item in items})
        character_index.append({
            "charaId": chara_id,
            "name": name,
            "total": len(items),
            "costumes": costumes,
        })
        (output / "characters").mkdir(exist_ok=True)
        (output / "characters" / f"{chara_id}.json").write_text(
            json.dumps(items, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    (output / "character-index.json").write_text(
        json.dumps(character_index, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (output / "game-audio.json").write_text(
        json.dumps(game_records, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "quotePagesDiscovered": len(discovered_pages),
        "quotePagesProcessed": len(pages),
        "voiceFiles": len(records),
        "characterVoiceFiles": sum(len(items) for items in by_character.values()),
        "gameVoiceFiles": len(game_records),
        "characters": len(character_index),
        "fandomUrls": sum(bool(item.get("fandomUrl")) for item in records),
        "failures": failures,
        "primaryMediaPolicy": "github-raw-then-cn-cdn-then-fandom",
        "githubRepositoryVisibilityRequired": "public",
        "githubBucketLayout": "images/<md5-first>/<md5-first-two>/<filename>",
    }
    (output / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int)
    args = parser.parse_args()
    summary = build(args.output, args.max_pages)
    if summary["voiceFiles"] == 0:
        raise SystemExit("No voice files were extracted")


if __name__ == "__main__":
    main()
