# Automatic custom builds for this fork

The `Fork Sync and Custom Build` workflow checks `subframe7536/maple-font:variable` once a day and merges its changes into this fork's `variable` branch. It then builds your configuration and publishes custom font archives in this fork's Releases. A few fork-specific commits remain on the branch.

## Set your preferences

Edit [`config.overrides.json`](../config.overrides.json), keeping only the settings you want to change. For example:

```json
{
  "formats": ["ttf"],
  "width": "narrow",
  "nerd_font": {
    "enable": true,
    "mono": true
  },
  "feature_freeze": {
    "cv01": "enable"
  }
}
```

The example above demonstrates possible changes.

Objects merge recursively; scalar values and arrays replace the corresponding upstream value. Other upstream settings, including newly added defaults, remain available. Avoid copying the entire upstream configuration or pinning `font_version` unless that is intentional. Removing an override restores the upstream default on the next build. `null` is a literal replacement, not a deletion instruction.

Keep the committed `config.json` unchanged. The workflow writes the effective configuration into that file only after synchronization, in the temporary Actions checkout. No change to the upstream builder is required.

## Create the synchronization secret

Create a **repository secret** named `FORK_SYNC_TOKEN`. The workflow reads it as `${{ secrets.FORK_SYNC_TOKEN }}` and does not declare an `environment`, so use **New repository secret** on the Actions secrets page.

1. [Create a fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token). Set **Resource owner** to `Cattle0Horse`, choose **Only select repositories**, and select `maple-font`.
2. Under **Repository permissions**, grant these permissions:

   | Permission | Access |
   | ---------- | ------ |
   | Contents | Read and write |
   | Workflows | Read and write |

3. Generate the token and copy its value.
4. Open this repository's [Settings → Secrets and variables → Actions](https://github.com/Cattle0Horse/maple-font/settings/secrets/actions). Under **Repository secrets**, click **New repository secret**.
5. Fill in the fields, then click **Add secret**:

   | Field | Value |
   | ----- | ----- |
   | Name | `FORK_SYNC_TOKEN` |
   | Secret | The fine-grained personal access token value from step 3 |

Environment secrets are available to jobs that reference their environment; this workflow uses a repository secret. See [GitHub's secrets documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

`FORK_SYNC_TOKEN` allows unattended synchronization when upstream changes workflow files. Without this secret, checkout uses `GITHUB_TOKEN`, which can reject pushes that update workflow files. See the [workflow synchronization discussion](https://github.com/orgs/community/discussions/35410). When the personal access token expires, replace the repository secret's value with a renewed token.

## Activate and download

1. Commit these files and push them to this fork's default branch, `variable`.
2. Create the `FORK_SYNC_TOKEN` repository secret using the [instructions above](#create-the-synchronization-secret).
3. Open **Actions → Fork Sync and Custom Build**. Enable Actions for the fork if GitHub asks.
4. Run the workflow manually for an initial build, or let the configuration push trigger it.
5. Download your font ZIP files from **Releases**, under **Custom fonts**. Custom releases are marked as prereleases and use `custom-<commit>` tags, separate from upstream `v*` tags.

Changing `config.overrides.json` also starts a build after you push it to `variable`. The schedule runs once a day at 00:23 UTC (08:23 in China). GitHub may delay scheduled runs; public repositories can have schedules disabled after 60 days without activity. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The workflow requests `contents: write` through the built-in `GITHUB_TOKEN` for release publication. `FORK_SYNC_TOKEN`, when present, is used by checkout for Git synchronization. Repository or organization restrictions can still prevent a push or release. Resolve any permission failure shown in the Actions log before retrying.

## Build records and recovery

- Synchronization and building happen in one workflow: pushes made with `GITHUB_TOKEN` do not trigger another push workflow. See [GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token).
- Each release targets the exact synchronized commit used for the build. It includes the effective `config.json`, resolved `build-config.json`, and source provenance in `fork-build.json`.
- A published release marks that revision as successful. Scheduled runs skip it until the source or override configuration changes. A failed build or incomplete draft release is retried on the next check. Select **force_build** in a manual run to rebuild an already published revision.
- Merge conflicts stop synchronization without force-pushing. Resolve the conflict locally, push the result to `variable`, and rerun the workflow. If another owner pushes while synchronization is running, its normal push fails safely; rerun against the latest branch.
- Failed builds retain configuration and available feature diagnostics as an Actions artifact for 14 days. Full logs remain in the workflow run.
- The workflow uses the checked-in uv lockfile with Python 3.12. FontForge is installed only when the selected Nerd Font configuration requires Font Patcher.

New upstream configuration incompatibilities can require updating your overrides; automatic synchronization cannot repair semantic changes to your chosen settings.
