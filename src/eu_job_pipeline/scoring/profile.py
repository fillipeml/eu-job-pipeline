"""The candidate profile: a Markdown file read by both scorers.

The LLM receives the whole file verbatim inside its system prompt. The heuristic scorer
only needs the bullet lists under a few headings, parsed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Profile:
    markdown: str
    skills: list[str] = field(default_factory=list)
    target_roles: list[str] = field(default_factory=list)
    languages: dict[str, str] = field(default_factory=dict)  # "german" -> "beginner"
    needs_visa: bool = True
    max_years: int = 3

    def speaks(
        self, language: str, at_least: tuple[str, ...] = ("fluent", "native", "c1", "c2")
    ) -> bool:
        level = self.languages.get(language.lower(), "")
        return any(marker in level for marker in at_least)


_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*?)\s*$")


def parse_profile(markdown: str) -> Profile:
    profile = Profile(markdown=markdown)
    section = ""
    for line in markdown.splitlines():
        if m := _HEADING_RE.match(line):
            section = m.group(1).lower()
            continue
        if not (m := _BULLET_RE.match(line)):
            continue
        item = m.group(1).strip()
        if "skill" in section:
            profile.skills.append(item.lower())
        elif "role" in section:
            profile.target_roles.append(item.lower())
        elif "language" in section:
            name, _, level = item.partition(":")
            profile.languages[name.strip().lower()] = level.strip().lower()
        elif "constraint" in section:
            lowered = item.lower()
            if "visa" in lowered:
                profile.needs_visa = "not required" not in lowered and "no visa" not in lowered
            if years := re.search(r"up to (\d+) years", lowered):
                profile.max_years = int(years.group(1))
    return profile


def load_profile(path: Path, fallback: Path | None = None) -> Profile:
    for candidate in (path, fallback):
        if candidate and candidate.exists():
            return parse_profile(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"No profile found at {path}" + (f" or {fallback}" if fallback else ""))
