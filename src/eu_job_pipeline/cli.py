"""Command-line interface: fetch -> score -> report, plus seed and stats for demo mode."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import factory
from .config import Settings
from .demo import generate_jobs
from .evals import GOLDEN_PATH, load_golden, render_eval, run_eval
from .report import render_csv, render_markdown, render_stats
from .scoring import LLMScorer

app = typer.Typer(
    help="Multi-source job ingestion and LLM fit-scoring for a Europe relocation search.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def _setup(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show source and scorer logs.")
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


@app.command()
def fetch(
    source: Annotated[
        list[str] | None, typer.Option("--source", "-s", help="Only these sources.")
    ] = None,
    query: Annotated[
        list[str] | None, typer.Option("--query", "-q", help="Override search terms.")
    ] = None,
) -> None:
    """Pull postings from every configured source and upsert them into the store."""
    settings = Settings()
    store = factory.build_store(settings)
    queries = query or settings.query_list
    total_new = total_updated = 0
    with factory.build_http_client(settings) as client:
        for src in factory.build_sources(settings, client, source):
            try:
                jobs = src.fetch(queries)
            except Exception as exc:  # one broken source must not stop the others
                console.print(f"[red]{src.name}: {exc}[/red]")
                continue
            new, updated = store.upsert_jobs(jobs)
            total_new += new
            total_updated += updated
            console.print(f"{src.name:14} fetched {len(jobs):4}  new {new:4}  updated {updated:4}")
    console.print(
        f"[bold]total new {total_new}, updated {total_updated}[/bold] -> {settings.resolved_db_path}"
    )


@app.command()
def score(
    limit: Annotated[int, typer.Option(help="Score at most N jobs (0 = all).")] = 0,
    rescore: Annotated[bool, typer.Option(help="Re-score jobs that already have a score.")] = False,
    batch: Annotated[
        bool,
        typer.Option(help="Use the Message Batches API (live mode, half price, minutes to hours)."),
    ] = False,
    mode: Annotated[
        str | None, typer.Option(help="Force a scorer: heuristic | llm | fixture | record.")
    ] = None,
) -> None:
    """Score unscored jobs against the candidate profile."""
    settings = Settings()
    store = factory.build_store(settings)
    profile = factory.build_profile(settings)
    scorer = factory.build_scorer(settings, profile, mode)
    jobs = store.jobs(unscored_only=not rescore, limit=limit)
    if not jobs:
        console.print("nothing to score")
        raise typer.Exit()
    console.print(f"scoring {len(jobs)} jobs with [bold]{scorer.name}[/bold]")

    if batch:
        if not isinstance(scorer, LLMScorer):
            console.print("[red]--batch needs the LLM scorer (live mode)[/red]")
            raise typer.Exit(code=2)
        records, failed = scorer.score_batch(
            jobs, on_poll=lambda status, n: console.print(f"  batch {status}, {n} still processing")
        )
        for record in records:
            store.save_score(record)
        console.print(f"[bold]scored {len(records)}[/bold], failed {len(failed)}")
        raise typer.Exit(code=0 if not failed else 1)

    done = skipped = 0
    with console.status("scoring...") as status:
        for i, job in enumerate(jobs, 1):
            status.update(f"scoring {i}/{len(jobs)}: {job.title[:50]}")
            record = scorer.score(job)
            if record is None:
                skipped += 1
                continue
            store.save_score(record)
            done += 1
    console.print(f"[bold]scored {done}[/bold], skipped {skipped}")


@app.command()
def report(
    top: Annotated[int, typer.Option(help="How many postings to include (0 = all).")] = 20,
    fmt: Annotated[str, typer.Option("--format", "-f", help="md or csv")] = "md",
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Write to this file instead of stdout.")
    ] = None,
    min_fit: Annotated[int, typer.Option(help="Hide postings below this fit.")] = 0,
) -> None:
    """Render the best matches as Markdown or CSV."""
    settings = Settings()
    rows = factory.build_store(settings).ranked(top=top, min_fit=min_fit)
    text = render_csv(rows) if fmt == "csv" else render_markdown(rows)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        console.print(f"wrote {len(rows)} rows -> {out}")
    else:
        print(text, end="")


@app.command()
def seed(
    count: Annotated[int, typer.Option(help="How many synthetic postings.")] = 120,
    seed: Annotated[int, typer.Option(help="Random seed; same seed, same data.")] = 20260101,
    keep: Annotated[
        bool, typer.Option(help="Keep existing rows instead of clearing the store.")
    ] = False,
) -> None:
    """Fill the store with fictional postings (demo mode only)."""
    settings = Settings()
    if not settings.demo_mode:
        console.print(
            "[red]seed only runs with DEMO_MODE=true; it would pollute a real store[/red]"
        )
        raise typer.Exit(code=2)
    store = factory.build_store(settings)
    if not keep:
        store.clear()
    new, updated = store.upsert_jobs(generate_jobs(count, seed))
    console.print(f"seeded {new} new, {updated} updated -> {settings.resolved_db_path}")


@app.command()
def stats() -> None:
    """Counts per source, country and verdict, plus token usage and cost per scorer."""
    settings = Settings()
    data = factory.build_store(settings).stats()
    print(render_stats(data), end="")
    if data["usage"]:
        table = Table(title="Verdicts")
        table.add_column("verdict")
        table.add_column("jobs", justify="right")
        for k, v in sorted(data["by_verdict"].items()):
            table.add_row(k, str(v))
        console.print(table)


@app.command(name="eval")
def eval_(
    mode: Annotated[
        str | None,
        typer.Option(
            help="Scorer to evaluate: heuristic | llm | fixture (default follows DEMO_MODE)."
        ),
    ] = None,
    golden: Annotated[Path, typer.Option(help="Golden set (JSONL).")] = GOLDEN_PATH,
) -> None:
    """Score the labelled golden set and print per-field accuracy and every miss."""
    settings = Settings()
    profile = factory.build_profile(settings)
    scorer = factory.build_scorer(settings, profile, mode)
    report_ = run_eval(scorer, load_golden(golden))
    print(render_eval(report_, scorer.name), end="")
    if report_.unscored:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
