from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts.fork_build import prepare_build, sync_upstream


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def init_repo(root: Path) -> None:
    root.mkdir()
    git(root, "init", "-b", "variable")
    git(root, "config", "user.name", "Test Owner")
    git(root, "config", "user.email", "owner@example.com")
    git(root, "config", "commit.gpgsign", "false")


def commit_file(root: Path, name: str, content: str) -> str:
    (root / name).write_text(content, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-m", f"Update {name}")
    return git(root, "rev-parse", "HEAD")


class ForkBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "source"
        init_repo(self.root)
        commit_file(
            self.root,
            "config.json",
            json.dumps(
                {
                    "font_version": "8.003",
                    "formats": ["ttf", "otf"],
                    "nerd_font": {"enable": True, "mono": False, "version": "3.5.0"},
                    "feature_freeze": {"cv01": "ignore", "ss01": "ignore"},
                }
            ),
        )
        commit_file(
            self.root,
            "config.overrides.json",
            json.dumps(
                {
                    "formats": ["ttf"],
                    "nerd_font": {"mono": True},
                    "feature_freeze": {"cv01": "enable"},
                }
            ),
        )
        git(self.root, "update-ref", "refs/remotes/fork-upstream/variable", "HEAD")

    def response(self, *, draft: bool = False) -> io.BytesIO:
        return io.BytesIO(json.dumps({"draft": draft}).encode())

    def test_missing_release_builds_nested_overrides_and_records_source(self) -> None:
        source = git(self.root, "rev-parse", "HEAD")
        original_config = git(self.root, "show", "HEAD:config.json")
        missing = HTTPError("https://example.com", 404, "Not Found", Message(), None)
        with patch("scripts.fork_build.urlopen", side_effect=missing):
            result = prepare_build(self.root, "owner/repo")

        self.assertEqual(result["needs_build"], "true")
        effective = json.loads((self.root / "config.json").read_text())
        self.assertEqual(effective["formats"], ["ttf"])
        self.assertEqual(effective["font_version"], "8.003")
        self.assertEqual(
            effective["nerd_font"],
            {"enable": True, "mono": True, "version": "3.5.0"},
        )
        self.assertEqual(
            effective["feature_freeze"], {"cv01": "enable", "ss01": "ignore"}
        )
        self.assertEqual(git(self.root, "show", "HEAD:config.json"), original_config)
        metadata = json.loads((self.root / "fork-build.json").read_text())
        self.assertEqual(metadata["source_sha"], source)
        self.assertEqual(metadata["release_tag"], result["release_tag"])

    def test_failed_or_draft_build_retries_until_published(self) -> None:
        for draft in (True, True, False):
            with self.subTest(draft=draft):
                with patch(
                    "scripts.fork_build.urlopen",
                    return_value=self.response(draft=draft),
                ):
                    result = prepare_build(self.root, "owner/repo")
                self.assertEqual(result["needs_build"], str(draft).lower())

    def test_manual_force_rebuilds_published_revision(self) -> None:
        with patch("scripts.fork_build.urlopen", return_value=self.response()):
            result = prepare_build(self.root, "owner/repo", force=True)
        self.assertEqual(result["needs_build"], "true")

    def test_new_config_commit_gets_a_new_release_identity(self) -> None:
        with patch("scripts.fork_build.urlopen", return_value=self.response()):
            previous = prepare_build(self.root, "owner/repo")
        commit_file(self.root, "config.overrides.json", '{"formats": ["woff2"]}')
        with patch(
            "scripts.fork_build.urlopen", return_value=self.response(draft=True)
        ):
            current = prepare_build(self.root, "owner/repo")
        self.assertNotEqual(previous["release_tag"], current["release_tag"])
        self.assertEqual(current["source_sha"], git(self.root, "rev-parse", "HEAD"))

    def test_api_failure_is_not_treated_as_an_unbuilt_revision(self) -> None:
        for failure in (
            HTTPError("https://example.com", 403, "Forbidden", Message(), None),
            HTTPError("https://example.com", 500, "Server Error", Message(), None),
            URLError("Network unavailable"),
        ):
            with self.subTest(failure=failure):
                with (
                    patch("scripts.fork_build.urlopen", side_effect=failure),
                    self.assertRaises((HTTPError, URLError)),
                ):
                    prepare_build(self.root, "owner/repo")
                self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def test_cli_emits_action_outputs_for_the_configuration_it_prepares(self) -> None:
        output = self.root.parent / "outputs"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.fork_build",
                "prepare",
                "--repository",
                "owner/repo",
                "--force",
            ],
            cwd=self.root,
            env={
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                "GITHUB_OUTPUT": str(output),
            },
            check=True,
            capture_output=True,
            text=True,
        )
        outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
        provenance = json.loads((self.root / "fork-build.json").read_text())
        self.assertEqual(outputs["source_sha"], provenance["source_sha"])
        self.assertEqual(outputs["release_tag"], provenance["release_tag"])
        self.assertEqual(outputs["needs_build"], "true")
        dry_run = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[2] / "build.py"),
                "--archive",
                "--dry",
            ],
            cwd=self.root,
            env={**os.environ, "GITHUB_ACTIONS": "true"},
            check=True,
            capture_output=True,
            text=True,
        )
        resolved = json.loads(dry_run.stdout)
        self.assertEqual(resolved["behavior"]["formats"], ["ttf"])
        self.assertTrue(resolved["behavior"]["archive"])
        self.assertTrue(resolved["nerd_font"]["mono"])
        self.assertEqual(resolved["feature"]["feature_freeze"]["cv01"], "enable")

    def test_invalid_override_does_not_overwrite_upstream_config(self) -> None:
        original = (self.root / "config.json").read_bytes()
        for invalid in ("{", "[]", "null"):
            with self.subTest(invalid=invalid):
                (self.root / "config.overrides.json").write_text(invalid)
                with self.assertRaises(ValueError):
                    prepare_build(self.root, "owner/repo")
                self.assertEqual((self.root / "config.json").read_bytes(), original)


class ForkSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.upstream = root / "upstream"
        init_repo(self.upstream)
        commit_file(self.upstream, "config.json", '{"font_version": "8.003"}')
        self.origin = root / "origin.git"
        git(root, "clone", "--bare", str(self.upstream), str(self.origin))
        self.fork = root / "fork"
        git(root, "clone", str(self.origin), str(self.fork))
        git(self.fork, "config", "user.name", "Test Owner")
        git(self.fork, "config", "user.email", "owner@example.com")
        git(self.fork, "config", "commit.gpgsign", "false")
        commit_file(self.fork, "config.overrides.json", '{"width": "narrow"}')
        git(self.fork, "push", "origin", "variable")

    def test_sync_preserves_overrides_and_pushes_all_upstream_commits(self) -> None:
        upstream_sha = commit_file(
            self.upstream,
            "config.json",
            '{"font_version": "8.004", "new_option": true}',
        )
        source = sync_upstream(self.fork, str(self.upstream), "variable")
        self.assertEqual(git(self.origin, "rev-parse", "variable"), source)
        git(self.fork, "merge-base", "--is-ancestor", upstream_sha, source)
        self.assertEqual(
            json.loads((self.fork / "config.overrides.json").read_text()),
            {"width": "narrow"},
        )
        self.assertTrue(
            json.loads((self.fork / "config.json").read_text())["new_option"]
        )
        self.assertEqual(
            sync_upstream(self.fork, str(self.upstream), "variable"), source
        )

    def test_conflict_stops_without_changing_remote_branch(self) -> None:
        original = git(self.origin, "rev-parse", "variable")
        commit_file(self.fork, "config.json", '{"font_version": "custom"}')
        commit_file(self.upstream, "config.json", '{"font_version": "8.004"}')
        with self.assertRaises(subprocess.CalledProcessError):
            sync_upstream(self.fork, str(self.upstream), "variable")
        self.assertEqual(git(self.origin, "rev-parse", "variable"), original)

    def test_concurrent_remote_commit_is_never_force_overwritten(self) -> None:
        other = self.fork.parent / "other"
        git(self.fork.parent, "clone", str(self.origin), str(other))
        git(other, "config", "user.name", "Another Owner")
        git(other, "config", "user.email", "another@example.com")
        git(other, "config", "commit.gpgsign", "false")
        other_sha = commit_file(other, "notes.txt", "Keep this remote change")
        git(other, "push", "origin", "variable")
        commit_file(self.upstream, "config.json", '{"font_version": "8.004"}')
        with self.assertRaises(subprocess.CalledProcessError):
            sync_upstream(self.fork, str(self.upstream), "variable")
        self.assertEqual(git(self.origin, "rev-parse", "variable"), other_sha)

    def test_dirty_checkout_is_not_synchronized(self) -> None:
        (self.fork / "config.overrides.json").write_text('{"width": "slim"}')
        original = git(self.origin, "rev-parse", "variable")
        with self.assertRaises(ValueError):
            sync_upstream(self.fork, str(self.upstream), "variable")
        self.assertEqual(git(self.origin, "rev-parse", "variable"), original)
