"""Synchronize the fork and prepare reproducible custom builds for Actions."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def sync_upstream(root: Path, upstream: str, branch: str) -> str:
    """Merge and push normally; conflicts and concurrent pushes must fail."""
    if _git(root, "status", "--porcelain"):
        raise ValueError("Synchronization requires a clean checkout")
    if _git(root, "symbolic-ref", "--short", "HEAD") != branch:
        raise ValueError(f"Synchronization requires the {branch} branch")
    upstream_ref = f"refs/remotes/fork-upstream/{branch}"
    _git(root, "fetch", "--no-tags", upstream, f"+refs/heads/{branch}:{upstream_ref}")
    _git(root, "merge", "--no-edit", upstream_ref)
    _git(root, "push", "origin", f"HEAD:refs/heads/{branch}")
    return _git(root, "rev-parse", "HEAD")


def _read_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def _merge_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _published_release_exists(repository: str, tag: str) -> bool:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        f"https://api.github.com/repos/{repository}/releases/tags/{tag}",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=30) as response:
            release = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return False
        raise
    return not release["draft"]


def prepare_build(
    root: Path, repository: str, *, force: bool = False
) -> dict[str, str]:
    """Apply overrides only for a build that has not already been published."""
    config = _merge_config(
        _read_object(root / "config.json"),
        _read_object(root / "config.overrides.json"),
    )
    source_sha = _git(root, "rev-parse", "HEAD")
    release_tag = f"custom-{source_sha}"
    needs_build = force or not _published_release_exists(repository, release_tag)
    outputs = {
        "source_sha": source_sha,
        "release_tag": release_tag,
        "needs_build": str(needs_build).lower(),
    }
    if needs_build:
        metadata = {
            **outputs,
            "repository": repository,
            "upstream_sha": _git(
                root, "rev-parse", "refs/remotes/fork-upstream/variable"
            ),
        }
        (root / "fork-build.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        (root / "config.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync")
    sync.add_argument(
        "--upstream", default="https://github.com/subframe7536/maple-font.git"
    )
    sync.add_argument("--branch", default="variable")
    prepare = commands.add_parser("prepare")
    prepare.add_argument(
        "--repository", default=os.environ.get("GITHUB_REPOSITORY"), required=False
    )
    prepare.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    if args.command == "sync":
        sync_upstream(root, args.upstream, args.branch)
        return
    if not args.repository:
        parser.error("prepare requires --repository or GITHUB_REPOSITORY")
    outputs = prepare_build(root, args.repository, force=args.force)
    if output_path := os.environ.get("GITHUB_OUTPUT"):
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.writelines(f"{key}={value}\n" for key, value in outputs.items())


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr or error.stdout or str(error)) from error
