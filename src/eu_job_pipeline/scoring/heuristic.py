"""Deterministic keyword scorer.

Used in demo mode (no network, no key) and as the fallback when the LLM answer is missing or
malformed. It is intentionally simple and explainable: every point comes from a named rule that
ends up in `reasons`, so the two scorers can be compared job by job.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from time import perf_counter

from ..models import Job, JobScore, ScoreRecord
from .profile import Profile

_VISA_YES = re.compile(
    r"visa sponsorship|sponsor(?:ship|ed)? (?:a |your )?visa|relocation (?:support|package|assistance|bonus)"
    r"|we (?:support|help with) (?:your )?(?:visa|relocation)|blue card"
)
_VISA_NO = re.compile(
    r"no (?:visa )?sponsorship|must (?:already )?(?:hold|have) (?:a |an )?(?:valid |existing )?"
    r"(?:(?:eu|german|dutch|irish|work|residence)\s+)*(?:permit|authori[sz]ation)"
    r"|eu citizens only|right to work in|without sponsorship|cannot sponsor|need an existing"
)
_OTHER_LANGUAGE_REQUIRED = re.compile(
    r"(?:fluent|fluency in|native|professional|business[- ]level)[^.\n]{0,40}"
    r"(?:french|dutch|spanish|italian|swedish|danish|norwegian|finnish|polish|czech)"
    r"|(?:french|dutch|spanish|italian|swedish|danish|norwegian|finnish|polish|czech)"
    r"[^.\n]{0,25}\b(?:required|mandatory|is a must)"
)
_GERMAN_REQUIRED = re.compile(
    r"(?:fluent|fluency in|business[- ]fluent|native|professional|verhandlungssicher|muttersprach|flie[sß]end)"
    r"[^.\n]{0,40}(?:german|deutsch)|(?:german|deutsch)[^.\n]{0,25}\b(?:c1|c2|native|fluent|required|mandatory)"
    r"|deutschkenntnisse (?:auf )?(?:c1|c2|verhandlungssicher)"
)
_GERMAN_PLUS = re.compile(
    r"(?:german|deutsch)[^.\n]{0,30}(?:plus|advantage|bonus|nice to have|beneficial|not required)"
)
_SENIOR = re.compile(
    r"\b(?:senior|staff|principal|lead|head of|architect)\b"
    r"|(?<![\d\-–])(?:[5-9]|1\d)\+?\s?(?:years|yrs|jahre)"
)
_JUNIOR = re.compile(
    r"\b(?:junior|graduate|entry[- ]level|working student|werkstudent|intern(?:ship)?|trainee)\b"
)
_REMOTE = re.compile(r"\bremote\b|home ?office|work from anywhere")
_HYBRID = re.compile(r"\bhybrid\b")
_ONSITE = re.compile(r"\bon[- ]?site\b|in[- ]office|vor ort")


class HeuristicScorer:
    name = "heuristic"

    def __init__(self, profile: Profile, target_countries: list[str]) -> None:
        self.profile = profile
        self.targets = {c.upper() for c in target_countries}

    def score(self, job: Job) -> ScoreRecord | None:
        started = perf_counter()
        text = job.text()
        title = job.title.lower()
        reasons: list[str] = []
        points = 0

        # Skills overlap: up to 50 points.
        hits = [s for s in self.profile.skills if s and s in text]
        if self.profile.skills:
            share = len(hits) / len(self.profile.skills)
            points += round(50 * min(1.0, share * 2.5))  # 40 % of the list already earns full marks
            reasons.append(
                f"Skills mentioned: {', '.join(hits[:6]) or 'none'} ({len(hits)}/{len(self.profile.skills)})."
            )

        # Target role in the title: 25 points; elsewhere in the text: 10.
        if any(r in title for r in self.profile.target_roles):
            points += 25
            reasons.append("Title matches a target role.")
        elif any(r in text for r in self.profile.target_roles):
            points += 10
            reasons.append("A target role appears in the description, not the title.")

        # Visa.
        if _VISA_NO.search(text):
            visa = "no"
            points -= 30 if self.profile.needs_visa else 0
            reasons.append("Posting requires an existing work permit or excludes sponsorship.")
        elif _VISA_YES.search(text):
            visa = "yes"
            points += 10
            reasons.append("Posting offers visa sponsorship or relocation support.")
        else:
            visa = "unknown"

        # Language.
        if _GERMAN_REQUIRED.search(text) and not _GERMAN_PLUS.search(text):
            language = "german"
            if not self.profile.speaks("german"):
                points -= 25
                reasons.append("Fluent German required; candidate does not meet it.")
        elif _OTHER_LANGUAGE_REQUIRED.search(text):
            language = "other"
            points -= 20
            reasons.append("A language other than English is required.")
        elif "english" in text or job.country in {"IE", "GB", "NL", "EU", None}:
            language = "english"
        else:
            language = "unknown"

        # Seniority.
        if _SENIOR.search(title) or _SENIOR.search(text[:1500]):
            seniority = "senior"
            points -= 15
            reasons.append("Senior-level role; candidate is junior to mid.")
        elif _JUNIOR.search(title):
            seniority = "junior"
        else:
            seniority = "mid"

        # Workplace.
        if job.remote or _REMOTE.search(text):
            workplace = "remote"
        elif _HYBRID.search(text):
            workplace = "hybrid"
        elif _ONSITE.search(text):
            workplace = "onsite"
        else:
            workplace = "unknown"

        # Geography.
        if job.country and job.country.upper() in self.targets:
            points += 5
        elif job.country:
            points -= 10
            reasons.append(f"Location {job.country} is outside the target countries.")

        fit = max(0, min(100, points))
        verdict = "strong" if fit >= 70 else "possible" if fit >= 45 else "weak"
        score = JobScore(
            fit=fit,
            verdict=verdict,
            reasons=reasons[:5] or ["No rule fired; neutral score."],
            visa_sponsorship=visa,
            language_requirement=language,
            seniority=seniority,
            workplace=workplace,
        )
        return ScoreRecord(
            job_key=job.key,
            score=score,
            scorer=self.name,
            scored_at=datetime.now(UTC),
            latency_ms=int((perf_counter() - started) * 1000),
        )
