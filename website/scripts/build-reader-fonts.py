"""Build complete WOFF2 reader font assets from an explicit game-font folder.

This intentionally performs no subsetting. Source hashes are pinned so a file
with the same display name but different bytes cannot be paired by mistake.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont


FONT_SPECS = (
    {
        "id": "magi-cn-body",
        "source": "TTDaYuanGB3.ttf",
        "sha256": "01bbb65b3b21f8d445fe15412fc3b5864425033f534464be26de0aa7ed8150c0",
    },
    {
        "id": "magi-cn-title",
        "source": "TTZhiHeiGB3-W4.ttf",
        "sha256": "01a4be2e5fca489c30219b3bec5edac0b7c98128c5fa629c34a0208ed5b0ba34",
    },
    {
        "id": "magi-jp-body",
        "source": "mbm_20160902.ttf",
        "sha256": "37f266883643ca3e3168049a130396a4993b981747f73c4f5068afec2412f5c5",
    },
    {
        "id": "magi-jp-title",
        "source": "MTF4a5kp.ttf",
        "sha256": "36dbe7b91d30d9d95713ba4b46bfa9b70f5d16bf759e45d3a043eae97da948a1",
    },
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unicode_cmap(font: TTFont) -> set[int]:
    code_points: set[int] = set()
    for table in font["cmap"].tables:
        if table.isUnicode():
            code_points.update(table.cmap)
    return code_points


def build(source_dir: Path, output_dir: Path) -> dict[str, object]:
    records: list[dict[str, object]] = []
    staged: list[tuple[Path, str]] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="magi-reader-fonts-") as temporary:
        temporary_dir = Path(temporary)
        for spec in FONT_SPECS:
            source = source_dir / spec["source"]
            source_data = source.read_bytes()
            source_digest = sha256(source_data)
            if source_digest != spec["sha256"]:
                raise RuntimeError(
                    f"{source} SHA256 mismatch: {source_digest}"
                )

            font = TTFont(source, recalcTimestamp=False)
            glyphs = font["maxp"].numGlyphs
            cmap = unicode_cmap(font)
            fs_type = int(font["OS/2"].fsType)
            temporary_woff2 = temporary_dir / f"{spec['id']}.woff2"
            font.flavor = "woff2"
            font.save(temporary_woff2, reorderTables=False)
            font.close()

            converted = TTFont(temporary_woff2, lazy=True)
            if converted["maxp"].numGlyphs != glyphs:
                raise RuntimeError(f"{source.name}: glyph count changed")
            if unicode_cmap(converted) != cmap:
                raise RuntimeError(f"{source.name}: Unicode cmap changed")
            if int(converted["OS/2"].fsType) != fs_type:
                raise RuntimeError(f"{source.name}: OS/2 fsType changed")
            converted.close()

            woff2_data = temporary_woff2.read_bytes()
            woff2_digest = sha256(woff2_data)
            filename = f"{spec['id']}.{woff2_digest[:12]}.full.woff2"
            staged.append((temporary_woff2, filename))
            records.append(
                {
                    "id": spec["id"],
                    "sourceFile": source.name,
                    "sourceBytes": len(source_data),
                    "sourceSha256": source_digest,
                    "woff2File": filename,
                    "woff2Url": f"/fonts/{filename}",
                    "woff2Bytes": len(woff2_data),
                    "woff2Sha256": woff2_digest,
                    "glyphs": glyphs,
                    "unicodeCodePoints": len(cmap),
                    "fsType": f"0x{fs_type:04x}",
                    "fullConversion": True,
                }
            )

        expected_files = {filename for _, filename in staged}
        for existing in output_dir.glob("magi-*.full.woff2"):
            if existing.name not in expected_files:
                existing.unlink()
        for temporary_woff2, filename in staged:
            (output_dir / filename).write_bytes(temporary_woff2.read_bytes())

    manifest: dict[str, object] = {
        "version": 1,
        "conversion": (
            "fontTools TTFont flavor=woff2; full glyph set, no subsetting"
        ),
        "fonts": records,
    }
    (output_dir / "reader-font-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "public" / "fonts",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.source_dir.resolve(), args.output_dir.resolve()),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
