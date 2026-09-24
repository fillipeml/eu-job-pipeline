"""A small labelled golden set and the accuracy report any scorer must pass.

`evals/golden.jsonl` holds synthetic postings with the expected verdict, visa, language and
seniority. `eu-jobs eval` runs a scorer over it and prints per-field accuracy plus every miss,
so a prompt or rule change is measured, not felt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import Job

FIELDS = ("verdict", "visa_sponsorship", "language_requirement", "seniority")
GOLDEN_PATH = Path("evals/golden.jsonl")


@dataclass
class EvalReport:
    total: int
    correct: dict[str, int] = field(default_factory=dict)
    misses: list[tuple[str, str, str, str]] = field(
        default_factory=list
    )  # (title, field, expected, got)
    unscored: list[str] = field(default_factory=list)

    def accuracy(self, name: str) -> float:
        return self.correct.get(name, 0) / self.total if self.total else 0.0


def load_golden(path: Path = GOLDEN_PATH) -> list[tuple[Job, dict]]:
    cases: list[tuple[Job, dict]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = json.loads(line)
        cases.append((Job(**item["job"]), item["expected"]))
    return cases


def run_eval(scorer, cases: list[tuple[Job, dict]]) -> EvalReport:
    report = EvalReport(total=len(cases), correct=dict.fromkeys(FIELDS, 0))
    for job, expected in cases:
        record = scorer.score(job)
        if record is None:
            report.unscored.append(job.title)
            continue
        got = record.score.model_dump()
        for name in FIELDS:
            if got[name] == expected[name]:
                report.correct[name] += 1
            else:
                report.misses.append((job.title, name, expected[name], got[name]))
    return report


def render_eval(report: EvalReport, scorer_name: str) -> str:
    out = [
        f"golden set: {report.total} postings - scorer: {scorer_name}",
        "",
        "| Field | Accuracy |",
        "|---|---|",
    ]
    out += [
        f"| {name} | {report.accuracy(name):.0%} ({report.correct.get(name, 0)}/{report.total}) |"
        for name in FIELDS
    ]
    if report.unscored:
        out += ["", f"unscored: {', '.join(report.unscored)}"]
    if report.misses:
        out += ["", "| Posting | Field | Expected | Got |", "|---|---|---|---|"]
        out += [f"| {t} | {f} | {e} | {g} |" for t, f, e, g in report.misses]
    return "\n".join(out) + "\n"
