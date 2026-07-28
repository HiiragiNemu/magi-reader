#!/usr/bin/env python3
"""Build structured character and voice datasets from preserved rendered HTML.

The 500-page preservation snapshot already contains every page carrying the
Wiki's ``人物信息`` infobox and almost every ``角色语音`` section.  The former
UI treated those pages as generic search results and the sanitizer removed the
MediaWiki component ``data-bind`` attributes that contain MP3 URLs.  This
script recovers both structures from the unmodified ``rawHtml`` fidelity layer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

BASE = "https://magireco.moe"
ORG_CATEGORY = "魔法少女组织"
ORG_TITLES = {
    "Magius之翼",
    "Neo-Magius",
    "PROMISED BLOOD",
    "Puella Care",
    "午夜0时的民间传说",
    "时女一族",
    "神滨魔法联盟",
}
VOICE_FILE_RE = re.compile(r"Vo_char_(\d+)_(\d+)_(\d+)", re.I)
VARIANT_RE = re.compile(r"[（(][^）)]*(?:ver\.|Ver\.|版本|装|动画|历史|童话|七夕|scene0)[^）)]*[）)]$")


def dump_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            sort_keys=pretty,
        )
        + "\n",
        encoding="utf-8",
    )


def text(node: Tag | None, separator: str = " ") -> str:
    return node.get_text(separator, strip=True) if node else ""


def absolute_url(value: str | None) -> str | None:
    if not value:
        return None
    return urljoin(BASE, value)


def load_snapshot(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    index_path = root / "data" / "archive-index.json"
    if not index_path.exists():
        raise FileNotFoundError(index_path)
    index = {item["id"]: item for item in json.loads(index_path.read_text(encoding="utf-8-sig"))}
    records: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "data" / "archive").glob("*.json")):
        records.update(json.loads(path.read_text(encoding="utf-8-sig")))
    return records, index


def direct_rows(table: Tag) -> list[Tag]:
    body = table.find("tbody", recursive=False)
    if not body:
        return []
    return [row for row in body.find_all("tr", recursive=False)]


def find_infobox(soup: BeautifulSoup) -> Tag | None:
    for table in soup.select("table.infobox"):
        if "人物信息" in text(table):
            return table
    for table in soup.select("table"):
        if "人物信息" in text(table):
            return table
    return None


def parse_infobox(table: Tag) -> tuple[dict[str, str], str | None, str]:
    fields: dict[str, str] = {}
    image_url: str | None = None
    caption = ""
    for image in table.select("img"):
        source = image.get("src") or image.get("data-src")
        if source:
            image_url = absolute_url(str(source))
            break
    for row in direct_rows(table):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) == 2:
            key = text(cells[0], "\n").strip().rstrip("：:")
            value = text(cells[1], "\n").strip()
            if key and value and key != "人物信息":
                fields[key] = value
        elif len(cells) == 1:
            value = text(cells[0], "\n").strip()
            if value and value != "人物信息" and not caption:
                caption = value
    return fields, image_url, caption


def find_section(soup: BeautifulSoup, title: str) -> tuple[Tag | None, list[Tag]]:
    heading = next(
        (node for node in soup.select("h2,h3,h4") if title in text(node)),
        None,
    )
    if heading is None:
        return None, []
    nodes: list[Tag] = []
    level = int(heading.name[1])
    node = heading.next_sibling
    while node:
        name = getattr(node, "name", None)
        if name and re.fullmatch(r"h[1-6]", name) and int(name[1]) <= level:
            break
        if isinstance(node, Tag):
            nodes.append(node)
        node = node.next_sibling
    return heading, nodes


def parse_summary(soup: BeautifulSoup) -> str:
    _, nodes = find_section(soup, "简介")
    paragraphs: list[str] = []
    for node in nodes:
        if node.name == "p":
            value = text(node, "\n")
            if value:
                paragraphs.append(value)
        elif node.name in {"table", "ul", "ol"} and paragraphs:
            break
        if sum(len(value) for value in paragraphs) >= 1800:
            break
    return "\n\n".join(paragraphs)[:2400]


def parse_bind(node: Tag | None) -> str | None:
    if not node:
        return None
    raw = node.get("data-bind")
    if not raw:
        return None
    try:
        value = json.loads(str(raw))
        playlist = value.get("component", {}).get("params", {}).get("playlist", [])
        if playlist:
            return playlist[0].get("audioFileUrl") or playlist[0].get("navigationUrl")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def parse_voice_entries(soup: BeautifulSoup) -> list[dict[str, Any]]:
    _, nodes = find_section(soup, "角色语音")
    if not nodes:
        return []
    voice_soup = BeautifulSoup("".join(str(node) for node in nodes), "lxml")
    tabs: list[Tag] = list(voice_soup.select(".tabbertab"))
    if not tabs:
        tabs = [voice_soup]

    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for tab in tabs:
        costume_label = str(tab.get("title") or "默认服装").strip()
        groups = [
            table
            for table in tab.find_all("table", recursive=False)
            if "mw-collapsible" in (table.get("class") or [])
        ]
        if not groups:
            groups = list(tab.select("table.mw-collapsible"))
        for group_table in groups:
            rows = direct_rows(group_table)
            if len(rows) < 2:
                continue
            group_label = text(rows[0]).strip() or "其他"
            entry_tables = rows[1].select(":scope > td > table")
            for entry_table in entry_tables:
                entry_rows = direct_rows(entry_table)
                if len(entry_rows) < 2:
                    continue
                slot_label = text(entry_rows[0]).strip()
                bind = entry_table.select_one("[data-bind]")
                audio_url = parse_bind(bind)
                voice_id = ""
                chara_id = ""
                costume_id = ""
                slot_id = ""
                if audio_url:
                    match = VOICE_FILE_RE.search(audio_url)
                    if match:
                        chara_id, costume_id, slot_id = match.groups()
                        voice_id = match.group(0)
                    else:
                        voice_id = audio_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]

                translated = ""
                translated_cells = entry_rows[1].find_all(["td", "th"], recursive=False)
                if translated_cells:
                    translated = text(translated_cells[-1], "\n").strip()
                original = ""
                if len(entry_rows) >= 3:
                    original_cells = entry_rows[2].find_all(["td", "th"], recursive=False)
                    if original_cells:
                        original = text(original_cells[-1], "\n").strip()
                        original = re.sub(r"^[【\[]原文[】\]]\s*", "", original).strip()

                dedupe = (voice_id or audio_url or "", costume_label, group_label, slot_label)
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                entries.append(
                    {
                        "voiceId": voice_id or None,
                        "charaId": chara_id or None,
                        "costumeId": costume_id or None,
                        "slot": slot_id or None,
                        "costumeLabel": costume_label,
                        "group": group_label,
                        "slotLabel": slot_label,
                        "text": translated,
                        "original": original,
                        "audioUrl": audio_url,
                        "hasTranslation": bool(translated and translated not in {"待补充", "译文暂缺"}),
                        "hasOriginal": bool(original and original not in {"待补充", "译文暂缺"}),
                    }
                )
    return entries


def base_name(title: str) -> str:
    return VARIANT_RE.sub("", title).strip() or title


def search_text(values: Iterable[Any]) -> str:
    return " ".join(str(value or "") for value in values).strip()


def build(root: Path) -> dict[str, Any]:
    records, archive_index = load_snapshot(root)
    output = root / "data" / "structured"
    if output.exists():
        shutil.rmtree(output)
    (output / "voice").mkdir(parents=True)

    characters: list[dict[str, Any]] = []
    voice_index: list[dict[str, Any]] = []
    total_voice = 0
    total_audio = 0
    total_translated = 0
    chara_ids: set[str] = set()

    for record_id, record in records.items():
        if int(record.get("namespace", -1)) != 0:
            continue
        raw_html = str(record.get("rawHtml") or "")
        if not raw_html:
            continue
        soup = BeautifulSoup(raw_html, "lxml")
        infobox = find_infobox(soup)
        if infobox is None:
            continue
        title = str(record.get("title") or archive_index.get(record_id, {}).get("title") or record_id)
        fields, image_url, image_caption = parse_infobox(infobox)
        meta = archive_index.get(record_id, {})
        categories = [str(value) for value in meta.get("categories", [])]
        organization = ORG_CATEGORY in categories or title in ORG_TITLES
        voices = [] if organization else parse_voice_entries(soup)
        voice_key = hashlib.sha1(record_id.encode("utf-8")).hexdigest()[:16]
        if voices:
            dump_json(output / "voice" / f"{voice_key}.json", voices)
        voice_ids = sorted({str(item["charaId"]) for item in voices if item.get("charaId")})
        chara_ids.update(voice_ids)
        audio_count = sum(bool(item.get("audioUrl")) for item in voices)
        translated_count = sum(bool(item.get("hasTranslation")) for item in voices)
        total_voice += len(voices)
        total_audio += audio_count
        total_translated += translated_count

        item = {
            "id": record_id,
            "title": title,
            "baseName": base_name(title),
            "kind": "organization" if organization else "character",
            "imageUrl": image_url,
            "imageCaption": image_caption,
            "nameJa": fields.get("日文名") or fields.get("日文名称") or "",
            "kana": fields.get("假名") or "",
            "romaji": fields.get("罗马音") or "",
            "aliases": fields.get("别名") or fields.get("其他译名") or "",
            "voiceActor": fields.get("声优") or "",
            "designer": fields.get("人设") or "",
            "summary": parse_summary(soup),
            "fields": fields,
            "categories": categories,
            "sourceUrl": record.get("sourceUrl") or meta.get("sourceUrl"),
            "articleId": record_id,
            "voiceKey": voice_key if voices else None,
            "voiceCount": len(voices),
            "audioCount": audio_count,
            "translatedVoiceCount": translated_count,
            "charaIds": voice_ids,
        }
        item["searchText"] = search_text(
            [
                title,
                item["baseName"],
                item["nameJa"],
                item["kana"],
                item["romaji"],
                item["aliases"],
                item["voiceActor"],
                item["designer"],
                item["summary"],
                *fields.values(),
                *categories,
            ]
        )
        characters.append(item)
        if voices:
            voice_index.append(
                {
                    "id": record_id,
                    "title": title,
                    "baseName": item["baseName"],
                    "imageUrl": image_url,
                    "voiceActor": item["voiceActor"],
                    "voiceKey": voice_key,
                    "lineCount": len(voices),
                    "audioCount": audio_count,
                    "translatedCount": translated_count,
                    "charaIds": voice_ids,
                    "costumes": sorted({str(entry["costumeLabel"]) for entry in voices}),
                    "groups": sorted({str(entry["group"]) for entry in voices}),
                    "searchText": item["searchText"],
                }
            )

    characters.sort(key=lambda item: (item["kind"] != "character", item["baseName"].casefold(), item["title"].casefold()))
    voice_index.sort(key=lambda item: (item["baseName"].casefold(), item["title"].casefold()))
    counts = Counter(item["kind"] for item in characters)
    manifest = {
        "schemaVersion": 1,
        "source": "preserved-rendered-html",
        "characters": len(characters),
        "characterPages": counts["character"],
        "organizations": counts["organization"],
        "voiceCharacters": len(voice_index),
        "voiceLines": total_voice,
        "voiceWithAudio": total_audio,
        "voiceWithTranslation": total_translated,
        "uniqueCharaIds": len(chara_ids),
    }
    dump_json(output / "characters.json", characters)
    dump_json(output / "voice-index.json", voice_index)
    dump_json(output / "manifest.json", manifest, pretty=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    manifest = build(args.snapshot.resolve())
    if manifest["characters"] < 235:
        raise RuntimeError(f"structured character coverage too small: {manifest}")
    if manifest["voiceCharacters"] < 220:
        raise RuntimeError(f"structured voice character coverage too small: {manifest}")
    if manifest["voiceWithAudio"] < 15000:
        raise RuntimeError(f"structured audio coverage too small: {manifest}")


if __name__ == "__main__":
    main()
