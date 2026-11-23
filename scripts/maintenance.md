# Maple Mono Maintenance Guide

This is the operational source of truth for maintainers. The other files under `scripts/` document implementation details; use this guide for source changes, generated files, CJK base refreshes, validation, and releases.

## Start safely

Work from a branch and inspect the worktree before changing anything:

```sh
git status --short
uv sync
```

The FontLab `.vfc` files, CJK preset JSON files, and feature source modules are inputs. Designspace/UFO sources, `.fea` files, release archives, and files under `fonts/` are generated outputs. Regenerate them with the task that owns them instead of editing them by hand. Exported root `sources/*.glyphs` files are local intermediates and are ignored.

Do not run a release, publish, or push command until the generated diff has been reviewed. `uv run task.py release ...` commits and pushes a version tag.

## Update the Maple Mono source

1. Edit the tracked regular or italic `.vfc` source in FontLab, then export the matching `sources/MapleMono[wght].glyphs` or `sources/MapleMono-Italic[wght].glyphs` file for each changed style. The exports are temporary inputs for conversion and must not be committed.
2. Regenerate the committed Designspace and UFO sources:

   ```sh
   uv run task.py designspace
   ```

   `tag_*` ligature glyphs and `.bg` variants are normalized to integer coordinates
   during conversion. Their 400-weight master is derived from the Thin and ExtraBold
   endpoints, so edit those endpoint masters rather than the middle layer. Review the
   complete diff under `sources/*.designspace` and `sources/*.ufo/`. If conversion
   reports compatibility errors, inspect `fonts/source-issues.json` before continuing.

3. If feature definitions or feature configuration changed in scripts/feature, regenerate all derived feature data:

   ```sh
   uv run task.py fea
   ```

   Review every generated file listed below. Do not keep unrelated churn.

4. Run a focused build before committing source changes:

   ```sh
   uv run build.py --format ttf --debug
   ```

   Add `--cjk cn` only when the change needs a CJK merge. Use `--dry` first when checking resolved inputs, and omit `--cache` after changing generator code, dependency versions, UFO contents, or another input that is not part of the stage cache identity.

Feature generation updates these tracked outputs:

- `sources/features/regular.fea`
- `sources/features/italic.fea`
- `sources/features/cn.fea`
- `sources/features/regular_cn.fea`
- `sources/features/italic_cn.fea`
- `documentation/opentype-features.md`
- `sources/schema.json` and the feature-freeze section in `config.json`
- The moving-rule list in `scripts/in_browser.py`

When deliberately adopting a new Nerd Font upstream release, build a base TTF first and run `uv run task.py nf`. The task checks the upstream release, updates `nerd_font.version` in `config.json`, downloads the matching patcher, and writes the three tracked NF base fonts under `sources/`. Use `uv run task.py nf --no-update` when the configured version is already correct and only the local NF outputs need rebuilding.

## Update CJK base fonts

The four source URLs are maintained manually. Update the `source.download.url` value in the relevant preset before starting a build:

| Locale | Preset                         |
| ------ | ------------------------------ |
| CN     | `sources/cjk/cn/config-cn.json` |
| TC     | `sources/cjk/tc/config-tc.json` |
| JP     | `sources/cjk/jp/config-jp.json` |
| KR     | `sources/cjk/kr/config-kr.json` |

Keep the source URL pinned to the intended upstream release or ref. Each built-in locale uses a cache key derived from its preset, shared feature font, generator, and locked runtime dependency list. Base font naming uses a separate version from the final release fonts.

### Published update (recommended)

1. Update the relevant preset or shared inputs. For a local check, run `uv run --locked --no-dev task.py cjk --preset <locale>` and review the generated fonts.
2. Push the input changes to `variable`. **Update CJK Base Fonts** builds locales whose cache keys lack a published release. It validates the ZIP structure, variable `fvar` tables, and generated content digests.
3. The workflow publishes each locale's two ZIPs and two digest files under `cjk-base-<locale>-<key>`. To populate a missing cache manually, dispatch the workflow for the desired locale or select `all`.

Both local and release builds can reuse the verified cache for their checkout's key. A missing or invalid archive falls back to building from the pinned source.

### Local check or rebuild

Use the standalone task for a focused local build or when debugging a preset:

```sh
uv run task.py cjk --help
uv run --locked --no-dev task.py cjk --preset cn
```

The task rebuilds the regular and italic variable bases, then writes the static instances unless `--vf-only` is selected. Unmodified presets write their ZIPs, fonts, and digests at `sources/cjk/<locale>/.cache/<key>/`. Use `uv run task.py cjk cache-key <locale>` to print the key. These outputs are generated and ignored by Git.

## Create a Maple Mono release

### Prepare and tag locally

1. Finish source, feature, and CJK updates, then run the validation baseline below. Check the CJK base workflow if the release includes changes to CJK inputs.
2. Preview the next version without changing files. The release task uses the development-only `questionary` menu with arrow-key navigation; each option includes its target tag and embedded font version, and `minor` is selected by default:

   ```sh
   uv run task.py release --dry
   ```

3. When the preview is correct, run the release task and confirm the prompt:

   ```sh
   uv run task.py release
   ```

   Choose `minor`, `major`, `pre-minor`, or `pre-major`. The task updates the PEP 440 project version in `pyproject.toml`, updates the three-digit embedded version in `config.json`, builds the release inputs, regenerates Fontsource and default, Narrow, and Slim variable WOFF2 assets under `woff2/variable/`, exports `requirements.txt`, copies CN assets, commits the intended release files, pushes the commit, and pushes the new tag.

   Pre-releases use tags such as `v8.0-beta.1` and embedded versions such as `Version 8.001`. Repeating `pre-major` creates `v8.0-beta.2` and `Version 8.002`; choosing `major` while on that release line finalizes `v8.0` with the next embedded version, `Version 8.003`.

### Build and publish GitHub release assets

The `Build All Formats and Release` workflow starts from a `v*` tag. It builds 8 profile/width bundles in parallel; each bundle builds the base outputs once and then all four CJK locales on the same runner, producing 22 archives. The final manifest still contains 176 archives, and the workflow creates a draft GitHub release with `uv run task.py publish release`.

For a manual rerun, use **Run workflow** and enter the existing release tag in the required `release_tag` field (for example, `v8.1`). The workflow checks out that tag; it does not create a new tag or infer one from the default branch. Do not pass a branch name or an unpushed tag.

Before handing off a release, verify the draft contains the generated release manifest and all base, Nerd Font, and locale archives. If an asset is missing, fix the matrix/build input and rerun the workflow rather than uploading an ad-hoc archive.

## Validation baseline

Run the smallest checks that cover the change, and run the full baseline before a release:

```sh
uv run build.py --dry
uv run ruff format --check .
uv run ruff check .
uv run pyrefly check
uv run python -m unittest discover -s scripts/tests
```

For CJK-only changes, add the focused suite before downloading large sources:

```sh
uv run python -m unittest \
  scripts.tests.test_cjk_config \
  scripts.tests.test_cjk_cache \
  scripts.tests.test_cjk_executor
```

After any task, inspect `git diff --check`, `git diff --stat`, and `git status --short`. Generated outputs are part of the change only when the task intentionally updates their source of truth.
