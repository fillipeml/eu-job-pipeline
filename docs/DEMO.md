# Three-minute demo

Before the call, in the repository root with `DEMO_MODE=true` (the default in `.env.example`):

```bash
uv run eu-jobs seed && uv run eu-jobs fetch && uv run eu-jobs score
```

Keep a terminal open and the editor on `src/eu_job_pipeline/factory.py`.

| Time | Do | Say |
|---|---|---|
| 0:00 | `uv run eu-jobs report --top 8` | "Four public job APIs into one SQLite store, every posting scored for one candidate: fit, visa, language, seniority. Everything on screen is fictional demo data." |
| 0:30 | `uv run eu-jobs stats` | "Counts per source and country, and the cost table: token usage is stored per row, so cost is computed from what was actually spent, not estimated." |
| 1:00 | `uv run eu-jobs eval` | "A 20-posting golden set with hand labels. The heuristic gets visa, language and seniority right on all of them and the verdict on 17. The three misses are adjacent roles: exactly what the LLM should read better. Same command with `--mode llm` fills the other column." |
| 1:30 | Open `factory.py`, then `scoring/llm.py` | "One factory reads DEMO_MODE. Two scorers behind one interface. The LLM client sends a strict JSON schema; Pydantic clamps what a schema cannot express; a malformed answer falls back to the heuristic and the scorer name is stored, so the two are never confused." |
| 2:15 | Scroll to `submit_batch` / `score_batch` | "Bulk scoring goes through the Message Batches API: half the price, restartable, keyed by custom_id. Same request shape as the synchronous call." |
| 2:40 | `uv run pytest -q` | "45 tests in demo mode, in CI on every push, plus gitleaks. The fixture files are what the tests and the demo share." |

## Questions to expect

- "Why not just ask the LLM everything?" The heuristic is free, instant and explainable, and it is the fallback. Having it lets me measure what the LLM adds instead of assuming it.
- "What did the assistant get wrong?" The generated JSON schema carried `title` and bounds the API rejects; substring matching that made "AI" match inside "maintain"; a year-range regex that read "2-5 years" as senior. All caught by tests or the golden set.
- "What would break at 10x volume?" Arbeitnow paging and Bundesagentur details. The fix is in "What I'd do next".
