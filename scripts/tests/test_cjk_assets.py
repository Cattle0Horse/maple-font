from __future__ import annotations

import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from scripts.cjk.assets import CJKBaseArchiveStore
from scripts.cjk.cache import write_static_hash
from scripts.cjk.config import CJKBuildConfig, CJKOutputConfig, CJKSourceConfig
from scripts.config.base import CJKCommonBuildOptions, ResolvedCJKBuildEntry
from scripts.tests.cjk_font_fixtures import build_test_font


class CJKBaseArchiveStoreTest(unittest.TestCase):
    def make_config(self, root: Path) -> CJKBuildConfig:
        return CJKBuildConfig(
            source=CJKSourceConfig(
                path=root / "source.ttf",
                masters={
                    100: {"wght": 100},
                    400: {"wght": 400},
                    800: {"wght": 800},
                },
            ),
            locale_name="CN",
            output=CJKOutputConfig(
                dir=root / "sources" / "cjk" / "cn",
                static_hash="static-cn.sha256",
                archive_name="cn-base-static.zip",
                variable_hash="variable-cn.sha256",
                variable_archive_name="cn-base-variable.zip",
            ),
        )

    def test_static_base_reuses_archive_from_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            archive = root / config.output.archive_name
            archive.write_bytes(b"local archive")
            store = CJKBaseArchiveStore("github.com")

            with (
                patch("scripts.cjk.assets.Path.cwd", return_value=root),
                patch.object(
                    store, "_install_local_archive", return_value=True
                ) as local,
                patch.object(store, "_install_static_archive") as remote,
            ):
                self.assertTrue(store.install_static_base("cn", config))

            self.assertEqual(local.call_args.args[0], archive)
            remote.assert_not_called()

    def test_variable_base_reuses_archive_from_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            config.output.dir.mkdir(parents=True)
            config.output.dir.joinpath(config.output.variable_hash).write_text(
                "0" * 64, encoding="utf-8"
            )
            archive = root / config.output.variable_archive_name
            archive.write_bytes(b"local archive")
            entry = ResolvedCJKBuildEntry(
                entry_id="cn",
                locale_name="CN",
                build_config=config,
                common_options=CJKCommonBuildOptions(),
                is_builtin=True,
                preset_id="cn",
            )
            store = CJKBaseArchiveStore("github.com")

            with (
                patch("scripts.cjk.assets.Path.cwd", return_value=root),
                patch.object(
                    store, "_install_local_archive", return_value=True
                ) as local,
                patch.object(store, "_install_variable_archive") as remote,
            ):
                self.assertTrue(store.ensure_variable_base(entry))

            self.assertEqual(local.call_args.args[0], archive)
            remote.assert_not_called()

    def test_remote_static_base_uses_digest_from_matching_release(self) -> None:
        for matching in (True, False):
            with self.subTest(matching=matching), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture = self.make_config(root / "fixture")
                filename = "MapleMonoCN-Regular.ttf"
                font_path = fixture.output.dir / fixture.output.static_dir / filename
                build_test_font(font_path).close()
                write_static_hash(fixture, font_path.parent)
                archive_path = fixture.output.dir / fixture.output.archive_name
                with ZipFile(archive_path, "w") as archive:
                    archive.write(font_path, filename)
                if not matching:
                    with ZipFile(archive_path, "w") as archive:
                        archive.writestr(filename, b"mismatched bytes")

                config = replace(
                    self.make_config(root / "consumer"), cache_key="a" * 64
                )
                store = CJKBaseArchiveStore("github.com")
                tag = f"cjk-base-cn-{config.cache_key}"

                def download(
                    url: str,
                    path: Path,
                    mirror: str,
                    *,
                    tag: str = tag,
                    assets: Path = fixture.output.dir,
                ) -> None:
                    self.assertIn(f"/releases/download/{tag}/", url)
                    self.assertEqual(mirror, "github.com")
                    shutil.copyfile(assets / url.rsplit("/", 1)[1], path)

                with (
                    patch("scripts.cjk.assets.download_file", side_effect=download),
                    patch(
                        "scripts.utils.downloads.download_file", side_effect=download
                    ),
                ):
                    self.assertEqual(store.install_static_base("cn", config), matching)

                self.assertEqual(
                    (config.output.dir / config.output.static_dir / filename).is_file(),
                    matching,
                )
                self.assertEqual(
                    (config.output.dir / config.output.static_hash).is_file(),
                    matching,
                )


if __name__ == "__main__":
    unittest.main()
