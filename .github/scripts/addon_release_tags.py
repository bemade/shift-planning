# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

"""Discover per-addon release tags from Odoo manifest version changes."""

import argparse
import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ADDON_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
ODOO_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+\.\d+$")
ZERO_SHA_RE = re.compile(r"^0{40}$")


@dataclass(frozen=True)
class ReleaseTag:
    addon: str
    version: str
    tag: str


def _git(repo: Path, *args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        input=input_text,
        text=True,
    ).stdout.strip()


def _normalize_before(repo: Path, before: str) -> str:
    if ZERO_SHA_RE.fullmatch(before):
        return _git(repo, "mktree", input_text="")
    return before


def _manifest_at(repo: Path, revision: str, path: str) -> dict | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    manifest = ast.literal_eval(result.stdout)
    if not isinstance(manifest, dict):
        raise TypeError(f"Manifest is not a dictionary: {path}")
    return manifest


def _manifest_version(manifest: dict, path: str) -> str:
    version = manifest.get("version")
    if not isinstance(version, str) or not ODOO_VERSION_RE.fullmatch(version):
        raise ValueError(f"Invalid Odoo version in {path}: {version!r}")
    return version


def discover_release_tags(repo: Path, before: str, after: str) -> list[ReleaseTag]:
    """Return sorted addon/version tags introduced between two revisions."""

    repo = repo.resolve()
    before = _normalize_before(repo, before)
    changed_paths = _git(
        repo,
        "diff",
        "--name-only",
        "--diff-filter=AMR",
        before,
        after,
        "--",
        "*/__manifest__.py",
    ).splitlines()

    releases = []
    for path in changed_paths:
        parts = PurePosixPath(path).parts
        if len(parts) != 2 or parts[1] != "__manifest__.py":
            continue
        addon = parts[0]
        if not ADDON_NAME_RE.fullmatch(addon):
            raise ValueError(f"Invalid addon name for release tag: {addon!r}")

        current_manifest = _manifest_at(repo, after, path)
        if current_manifest is None:
            continue
        current_version = _manifest_version(current_manifest, path)

        previous_manifest = _manifest_at(repo, before, path)
        previous_version = (
            _manifest_version(previous_manifest, path)
            if previous_manifest is not None
            else None
        )
        if current_version == previous_version:
            continue

        releases.append(
            ReleaseTag(
                addon=addon,
                version=current_version,
                tag=f"{addon}/{current_version}",
            )
        )

    return sorted(releases, key=lambda release: release.addon)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List immutable per-addon tags for changed Odoo versions."
    )
    parser.add_argument("before", help="Revision before the push")
    parser.add_argument("after", help="Revision after the push")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()

    for release in discover_release_tags(args.repo, args.before, args.after):
        print(release.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
