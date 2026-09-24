"""Prompt construction for the LLM scorer.

The system prompt (rubric + candidate profile) is identical for every job, so it is marked
cacheable; only the user message changes per posting.
"""

from __future__ import annotations

from ..models import Job
from .profile import Profile

MAX_DESCRIPTION_CHARS = 6000

SYSTEM_TEMPLATE = """You screen job postings for one specific candidate who is relocating to Europe.
For each posting you return a JSON object that follows the provided schema exactly.

How to score `fit` (0 to 100):
- 80-100: the role matches the candidate's target roles and most listed skills, the seniority is
  reachable, and nothing in the posting excludes them (language, work permit).
- 55-79: a real match with one significant gap (a missing core skill, seniority one step above,
  a language "preferred" but not required).
- 30-54: partial overlap; two or more significant gaps, or a hard requirement the candidate does
  not meet but that some employers waive.
- 0-29: a different profession, or an explicit exclusion the candidate cannot satisfy
  (must already hold an EU work permit and the posting refuses sponsorship; native-level German
  required; 8+ years required).

`verdict`: "strong" for fit >= 70, "possible" for 45-69, "weak" below 45.

`visa_sponsorship`: "yes" only if the posting states sponsorship, relocation support or
"we help with visas"; "no" if it requires an existing permit or excludes non-EU applicants;
otherwise "unknown".

`language_requirement`: the working language the posting requires. "german" only when German is
required (not merely "a plus"). "english" when English is stated or the posting is in English with
no other requirement. "other" for any other required language. "unknown" if not inferable.

`seniority`: what the posting asks for, not the title alone: "junior" (0-2 years, graduate,
entry), "mid" (2-5 years or unspecified professional), "senior" (5+ years, lead, staff, principal).

`workplace`: "remote", "hybrid", "onsite" or "unknown" from the posting.

`reasons`: up to five short sentences, most important first, each pointing at concrete evidence
in the posting. Never invent requirements that are not written. When the posting does not say,
answer "unknown" rather than guessing.

# Candidate profile

{profile}
"""


def build_system(profile: Profile) -> str:
    return SYSTEM_TEMPLATE.format(profile=profile.markdown.strip())


def build_user(job: Job) -> str:
    description = job.description.strip()
    if len(description) > MAX_DESCRIPTION_CHARS:
        description = description[:MAX_DESCRIPTION_CHARS].rstrip() + "\n[... truncated]"
    lines = [
        f"Title: {job.title}",
        f"Company: {job.company}",
        f"Location: {job.location or 'not stated'}" + (f" ({job.country})" if job.country else ""),
        f"Remote flag from source: {job.remote if job.remote is not None else 'not stated'}",
        f"Posted: {job.posted_at.isoformat() if job.posted_at else 'not stated'}",
        f"Tags: {', '.join(job.tags) if job.tags else 'none'}",
        f"Source: {job.source}",
        "",
        "Description:",
        description or "(no description available; judge from the title and tags only)",
    ]
    return "\n".join(lines)
