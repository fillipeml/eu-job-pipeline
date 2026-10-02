# CLAUDE.md

Working rules for AI-assisted changes in this repository. They mirror the README; the README
wins on conflict.

## Non-negotiable rules

1. **The heuristic scorer is a real scorer, not a mock.** It runs in demo mode, it is the
   fallback when the model's answer is missing or malformed, and it is scored against the same
   golden set. Deleting it would remove the only baseline that says what the model is worth.
2. **Every stored rate carries what produced it.** `scorer` is written on every score row, so a
   number from the heuristic and a number from a model can never be averaged together by
   accident.
3. **The three input token counts do not overlap.** `input_tokens` is already the uncached
   remainder; the whole prompt is `input_tokens + cache_write_tokens + cache_read_tokens`.
   Subtracting one from another discounts the same tokens twice, which is a mistake this
   repository has already made once and now has a test against.
4. **A batch `custom_id` is derived, never a job key.** The Message Batches API requires
   `^[a-zA-Z0-9_-]{1,64}$` and every job key is `source:id`. `batch_custom_id` hashes rather
   than strips, because two postings can strip to the same string and one would be lost.
5. **Demo mode makes no network call.** `--demo` runs the whole pipeline on generated postings
   and recorded readings, with no key. Any new source or scorer gets a fixture adapter in the
   same change.
6. **Invented data only.** The companies, postings and people in the demo store do not exist.
   No real job board response is committed.

## Conventions

- Python 3.12, `uv`, `ruff`, `pytest`. A CLI over a SQLite file; no server.
- `DEMO_MODE` and the API key are read in `config.py` and nowhere else.
- One SQLite file is the whole state. Upserts are keyed by `source:external_id`, so re-running
  a fetch is free and idempotent.
- A column added to a stored row goes in `SCHEMA` **and** in `_LATER_COLUMNS`, so a database
  written by an earlier version still opens.
- Tests run offline. Expected values are computed independently, not by running the code and
  pasting the result.
- Commits: English, Conventional Commits, one logical change each, no AI attribution trailers.
