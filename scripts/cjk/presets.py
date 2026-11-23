from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from scripts.cjk.config import config_from_json
from scripts.utils.hashing import hash_bytes, hash_file, hash_json

if TYPE_CHECKING:
    from scripts.cjk.config import CJKBuildConfig

CJKPresetId = Literal["cn", "jp", "tc", "kr"]
DEFAULT_PRESET_ROOT = Path("sources/cjk")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CJKPresetSpec:
    preset_id: CJKPresetId
    label: str
    config_path: Path
    meta_languages: str
    code_page_range1: int


_PRESETS: dict[CJKPresetId, CJKPresetSpec] = {
    "cn": CJKPresetSpec(
        "cn",
        "Simplified Chinese",
        DEFAULT_PRESET_ROOT / "cn" / "config-cn.json",
        "Latn, Hans",
        1 << 0 | 1 << 18,
    ),
    "jp": CJKPresetSpec(
        "jp",
        "Japanese",
        DEFAULT_PRESET_ROOT / "jp" / "config-jp.json",
        "Latn, Jpan",
        1 << 0 | 1 << 17,
    ),
    "tc": CJKPresetSpec(
        "tc",
        "Traditional Chinese",
        DEFAULT_PRESET_ROOT / "tc" / "config-tc.json",
        "Latn, Hant",
        1 << 0 | 1 << 20,
    ),
    "kr": CJKPresetSpec(
        "kr",
        "Korean",
        DEFAULT_PRESET_ROOT / "kr" / "config-kr.json",
        "Latn, Hang",
        1 << 0 | 1 << 19,
    ),
}


def list_presets() -> tuple[CJKPresetId, ...]:
    return tuple(_PRESETS.keys())


def get_preset(preset_id: CJKPresetId) -> CJKPresetSpec:
    return _PRESETS[preset_id]


def build_preset_config(
    preset_id: CJKPresetId, root: str | None = None
) -> CJKBuildConfig:
    preset = get_preset(preset_id)
    config_path = (
        Path(root) / preset.config_path.relative_to(DEFAULT_PRESET_ROOT)
        if root
        else preset.config_path
    )
    return config_from_json(config_path)


def cache_preset(preset_id: CJKPresetId, config: CJKBuildConfig) -> CJKBuildConfig:
    """Key reusable bases by the inputs to the canonical preset build."""
    preset_path = PROJECT_ROOT / get_preset(preset_id).config_path
    inputs = [
        preset_path,
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / ".github/workflows/cjk-base-build.yml",
        PROJECT_ROOT / "scripts/task/cjk.py",
    ]
    for module in ("cjk", "font_ops", "utils"):
        inputs.extend((PROJECT_ROOT / "scripts" / module).glob("*.py"))
    input_hashes = {
        path.relative_to(PROJECT_ROOT).as_posix(): hash_bytes(
            path.read_text(encoding="utf-8").encode("utf-8")
        )
        for path in inputs
    }
    input_hashes["feature_font"] = hash_file(config.feature_font_path)
    source = config.source
    if source.download is None:
        input_hashes["source_font"] = hash_file(source.path)
    else:
        download_key = hash_json([source.download.url, source.download.path_in_archive])
        source = replace(
            source, path=source.path.parent / ".cache" / download_key / source.path.name
        )
    cache_key = hash_json(input_hashes)
    directory = config.output.dir / ".cache" / cache_key
    return replace(
        config,
        source=source,
        output=replace(config.output, dir=directory),
        temp_dir=directory / "temp",
        cache_key=cache_key,
    )
