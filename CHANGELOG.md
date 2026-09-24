# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [0.1.0] - 2026-09-24

### Added

- Sources: Arbeitnow, Bundesagentur für Arbeit Jobsuche, Greenhouse boards and Lever postings, normalised into one SQLite store with idempotent upserts.
- Scorers behind one interface: deterministic heuristic (offline) and Claude with a strict JSON schema, including Message Batches mode and fixture replay.
- Golden-set evaluation (`eu-jobs eval`) with per-field accuracy and a list of misses; runs in CI.
- Markdown and CSV reports, token usage and cost per scorer (`eu-jobs stats`).
- Demo mode: recorded API fixtures, synthetic postings, no key and no network required.
- 45 tests, SHA-pinned CI with gitleaks, Dockerfile and compose file.
