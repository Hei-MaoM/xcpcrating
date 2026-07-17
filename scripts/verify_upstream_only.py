#!/usr/bin/env python3
"""Fail when the repository can still overlay locally-curated SRK boards."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SRK_ROOT = REPO_ROOT / "srk-extra"
DATA_SOURCE_CONFIGS = (
    REPO_ROOT / ".github" / "workflows" / "pages.yml",
    REPO_ROOT / "scripts" / "update_data.sh",
    REPO_ROOT / "README.md",
)


def find_local_overlay_violations() -> list[str]:
    """Return every local-SRK artifact or active documentation reference."""
    violations: list[str] = []

    if LOCAL_SRK_ROOT.exists():
        files = sorted(path for path in LOCAL_SRK_ROOT.rglob("*") if path.is_file())
        violations.extend(str(path.relative_to(REPO_ROOT)) for path in files)

    for path in DATA_SOURCE_CONFIGS:
        if path.exists() and "srk-extra" in path.read_text(encoding="utf-8"):
            violations.append(f"{path.relative_to(REPO_ROOT)} references srk-extra")

    return violations


def main() -> int:
    violations = find_local_overlay_violations()
    if not violations:
        print("Upstream-only SRK source invariant satisfied.")
        return 0

    print("Local SRK overlay is still enabled:")
    for violation in violations:
        print(f"- {violation}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
