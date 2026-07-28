#!/usr/bin/env python3
"""Extract the complete Doppel catalog from preserved character page HTML."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

BASE = "https://magireco.moe"


def dump_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")) + "\n",
        encoding="utf-8",
    )


def node_text(node: Tag | None, separator: str = "\n") -> str:
    if node is None:
        return ""
    value = node.get_text(separator, strip=True)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def direct_rows(table: Tag) -> list[Tag]:
    body = table.find("tbody", recursive=False)
    return list(body.find_all("tr", recursive=False)) if body else []


def section_nodes(soup: BeautifulSoup, heading_text: str) -> list[Tag]:
    heading = next((node for node in soup.select("h2,h3,h4") if heading_text in node_text(node, " ")), None)
    if heading is None:
        return []
    level = int(heading.name[1])
    result: list[Tag] = []
    node = heading.next_sibling
    while node:
        name = getattr(node, "name", None)
        if name and re.fullmatch(r"h[1-6]", name) and int(name[1]) <= level:
            break
        if isinstance(node, Tag):
            result.append(node)
        node = node.next_sibling
    return result


def split_epithet(value: str) -> tuple[str, str]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    epithet = lines[0] if lines else ""
    form = ""
    for line in lines[1:]:
        match = re.search(r"(?:其姿态为|その姿は[、，]?)[：:]?\s*(.+)", line)
        if match:
            form = match.group(1).strip()
            break
    return epithet, form


def build(snapshot: Path) -> dict[str, Any]:
    archive_index = {
        item["id"]: item
        for item in json.loads((snapshot / "data/archive-index.json").read_text(encoding="utf-8-sig"))
    }
    records: dict[str, dict[str, Any]] = {}
    for path in sorted((snapshot / "data/archive").glob("*.json")):
        records.update(json.loads(path.read_text(encoding="utf-8-sig")))
    character_path = snapshot / "data/structured/characters.json"
    characters = json.loads(character_path.read_text(encoding="utf-8-sig")) if character_path.exists() else []
    character_by_id = {item["id"]: item for item in characters}

    catalog: list[dict[str, Any]] = []
    for record_id, record in records.items():
        if int(record.get("namespace", -1)) != 0:
            continue
        raw_html = str(record.get("rawHtml") or "")
        if not raw_html:
            continue
        soup = BeautifulSoup(raw_html, "lxml")
        nodes = section_nodes(soup, "魔女化身")
        if not nodes:
            continue
        section = BeautifulSoup("".join(str(node) for node in nodes), "lxml")
        table = next(
            (
                item
                for item in section.select("table")
                if item.find("caption") and "Doppel" in node_text(item.find("caption"), " ")
            ),
            None,
        )
        if table is None:
            continue
        rows = direct_rows(table)
        if len(rows) < 3:
            continue
        first = rows[0].find_all(["th", "td"], recursive=False)
        second = rows[1].find_all(["th", "td"], recursive=False)
        third = rows[2].find_all(["th", "td"], recursive=False)
        if len(first) < 3 or len(second) < 2 or len(third) < 2:
            continue

        image = first[0].select_one("img")
        image_url = urljoin(BASE, str(image.get("src"))) if image and image.get("src") else None
        credit_node = first[0].select_one("small")
        credit = node_text(credit_node, " ")
        name = node_text(first[1], " ")
        runes = node_text(first[2], " ")
        epithet_zh, form_zh = split_epithet(node_text(second[0]))
        epithet_ja, form_ja = split_epithet(node_text(second[1]))
        description_zh = node_text(third[0])
        description_ja = node_text(third[1])
        note = ""
        for row in rows[3:]:
            value = node_text(row)
            if "注" in value:
                note = value
                break
        character = character_by_id.get(record_id, {})
        meta = archive_index.get(record_id, {})
        item = {
            "id": record_id,
            "characterId": record_id,
            "character": str(record.get("title") or meta.get("title") or record_id),
            "characterImageUrl": character.get("imageUrl"),
            "doppelImageUrl": image_url,
            "credit": credit,
            "name": name,
            "runes": runes,
            "epithetZh": epithet_zh,
            "formZh": form_zh,
            "epithetJa": epithet_ja,
            "formJa": form_ja,
            "descriptionZh": description_zh,
            "descriptionJa": description_ja,
            "note": note,
            "articleId": record_id,
            "sourceUrl": record.get("sourceUrl") or meta.get("sourceUrl"),
            "categories": meta.get("categories", []),
        }
        item["searchText"] = " ".join(
            str(value or "")
            for value in (
                item["character"], item["name"], item["runes"], item["credit"],
                item["epithetZh"], item["formZh"], item["epithetJa"], item["formJa"],
                item["descriptionZh"], item["descriptionJa"], *item["categories"],
            )
        )
        catalog.append(item)

    catalog.sort(key=lambda item: (item["character"].casefold(), item["name"].casefold()))
    if len(catalog) != 174:
        raise RuntimeError(f"Doppel coverage mismatch: expected 174, got {len(catalog)}")
    output = snapshot / "data/structured"
    dump_json(output / "doppel.json", catalog)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    manifest["doppel"] = len(catalog)
    manifest["doppelWithImage"] = sum(bool(item.get("doppelImageUrl")) for item in catalog)
    manifest["doppelWithChineseDescription"] = sum(bool(item.get("descriptionZh")) for item in catalog)
    dump_json(manifest_path, manifest, pretty=True)
    print(json.dumps({"doppel": len(catalog), "sample": catalog[:2]}, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    build(args.snapshot.resolve())


if __name__ == "__main__":
    main()
