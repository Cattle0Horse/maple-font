# CJK Base Cache Implementation Plan

> **For agentic workers:** implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal** Remove checked-in output digests from the CJK base build contract while preserving archive validation.

**Architecture** Use one input fingerprint per built-in locale for the local cache and its release tag. Generate the two archives and their content digests together. Consumers validate the pair from the matching release before installing assets.

**Tech stack** Python, uv, GitHub Actions, and GitHub CLI.

**Spec** Use a stable identity for reusable CJK fonts, key the cache by inputs, and publish generated digests alongside archives.

- [x] Implement fingerprinted preset configuration and stable CJK base naming. Verify that only the affected locale changes when its preset changes and that release version edits do not change the cache key.
- [x] Resolve versioned links and verify downloaded archives against their release sidecars. Exercise successful installation and rejection of mismatched bytes.
- [x] Implement publishing of missing locale releases using locked runtime dependencies. Validate the generated archive pairs before publishing.
- [x] Update maintainer guidance, run the unit suite, and check a real locale build.
