#!/usr/bin/env python3
"""Compile critical Python tools and run repository regression tests."""
from __future__ import annotations

import argparse
import py_compile
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRITICAL_FILES = (
    ROOT / "generate_story_index.py",
    ROOT / "tools/github_api_checkout.py",
    ROOT / "tools/import_magireco_general_voice.py",
    ROOT / "tools/import_exedra_official_tw.py",
    ROOT / "tools/import_exedra_cache_export.py",
    ROOT / "tools/import_exedra_human_text.py",
    ROOT / "tools/import_exedra_wiki_voice.py",
    ROOT / "tools/generate_exedra_voice_catalog.py",
    ROOT / "tools/fetch_tw_sp_source_bundle.py",
    ROOT / "tools/tw_sp_handoff_contract.py",
    ROOT / "tools/tw_official_import_core.py",
    ROOT / "tools/materialize_tw_official_cn.py",
    ROOT / "tools/apply_tw_official_metadata.py",
    ROOT / "tools/generate_exedra_localization_audit.py",
    ROOT / "tools/build_split_search_indexes.py",
    ROOT / "tools/search_chunk_delivery.py",
    ROOT / "tools/patch_search_chunk_runtime.py",
    ROOT / "tools/patch_tw_deploy_workflow.py",
    ROOT / "tools/build_story_release_archive.py",
    ROOT / "scripts/materialize_proofreading_assets.py",
)
TEST_ROOT = ROOT / "tests"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    missing = [path for path in CRITICAL_FILES if not path.is_file()]
    if missing:
        for path in missing:
            print(f"missing critical Python file: {path}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="magi-reader-pycompile-") as temporary:
        compile_root = Path(temporary)
        for index, path in enumerate(CRITICAL_FILES):
            output = compile_root / f"{index:02d}-{path.stem}.pyc"
            try:
                py_compile.compile(str(path), cfile=str(output), doraise=True)
            except py_compile.PyCompileError as error:
                print(error.msg, file=sys.stderr)
                return 2
            print(f"compiled: {path.relative_to(ROOT).as_posix()}")

    if not TEST_ROOT.is_dir():
        print(f"missing test directory: {TEST_ROOT}", file=sys.stderr)
        return 2
    sys.dont_write_bytecode = True
    suite = unittest.defaultTestLoader.discover(
        str(TEST_ROOT), pattern="test_*.py", top_level_dir=str(ROOT)
    )
    result = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1,
        failfast=False,
    ).run(suite)
    if not result.wasSuccessful():
        return 2
    print(
        f"python checks passed: tests={result.testsRun} "
        f"errors={len(result.errors)} failures={len(result.failures)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
