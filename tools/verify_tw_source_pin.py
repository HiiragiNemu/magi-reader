#!/usr/bin/env python3
"""Verify dispatch pins against an already authenticated TW v1 bundle."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from tw_sp_handoff_contract import CONTRACT_FILENAME, verify_contract


class PinError(RuntimeError):
    pass


def normalize_sha(value: str, field: str) -> str:
    result = value.strip()
    if (
        result != result.lower()
        or len(result) != 64
        or any(char not in "0123456789abcdef" for char in result)
    ):
        raise PinError(f"{field} is not a lowercase SHA-256")
    return result


def verify_pins(
    bundle_root: Path,
    *,
    contract_sha256: str,
    sp_revision: str,
    scenario_revision: str,
    manifest_revision: str,
) -> dict[str, str]:
    root = bundle_root.resolve(strict=True)
    raw = (root / CONTRACT_FILENAME).read_bytes()
    actual_contract_sha = hashlib.sha256(raw).hexdigest()
    expected_contract_sha = normalize_sha(contract_sha256, "contract_sha256")
    if actual_contract_sha != expected_contract_sha:
        raise PinError(
            f"contract SHA mismatch: {actual_contract_sha} != {expected_contract_sha}"
        )
    contract = verify_contract(root)
    expected_revisions = {
        "sp": sp_revision.strip(),
        "scenarios": scenario_revision.strip(),
        "manifests": manifest_revision.strip(),
    }
    if contract["sourceRevisions"] != expected_revisions:
        raise PinError(
            f"source revision mismatch: {contract['sourceRevisions']!r} != "
            f"{expected_revisions!r}"
        )
    return {
        "contract_sha256": actual_contract_sha,
        "scenario_tree_sha256": contract["catalogs"]["scenarios"]["treeSha256"],
        "manifest_tree_sha256": contract["catalogs"]["manifests"]["treeSha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--sp-revision", required=True)
    parser.add_argument("--scenario-revision", required=True)
    parser.add_argument("--manifest-revision", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_pins(
            args.bundle_root,
            contract_sha256=args.contract_sha256,
            sp_revision=args.sp_revision,
            scenario_revision=args.scenario_revision,
            manifest_revision=args.manifest_revision,
        )
    except (OSError, RuntimeError, PinError) as exc:
        print(f"TW_SOURCE_PIN_ERROR {exc}")
        return 1
    print(
        "TW_SOURCE_PIN_OK "
        + " ".join(f"{key}={value}" for key, value in result.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
