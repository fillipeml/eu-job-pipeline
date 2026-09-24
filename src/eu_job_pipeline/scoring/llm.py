"""LLM scorer: Claude with structured outputs, behind a small client interface.

Three clients implement `LLMClient`:

- `AnthropicLLMClient`: the real thing (Messages API, JSON-schema output, prompt caching on the
  shared system prompt). Also submits Message Batches for large runs at half the price.
- `FixtureLLMClient`: replays recorded responses from `fixtures/llm/<sha256>.json`; raises
  `FixtureMissError` for unseen requests so the scorer can fall back to the heuristic.
- `RecordingLLMClient`: wraps a real client and writes fixtures for later offline runs.

The scorer validates every answer against `JobScore` before it is stored. A malformed answer,
a refusal or an API error never crashes a run; it is logged and the job stays unscored or gets
the heuristic score, with the scorer name recorded so the two are never confused.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Protocol

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import ValidationError

from ..models import Job, JobScore, ScoreRecord, llm_output_schema
from .heuristic import HeuristicScorer
from .profile import Profile
from .prompt import build_system, build_user

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    text: str | None
    stop_reason: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


class FixtureMissError(LookupError):
    """No recorded response for this request."""


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, schema: dict) -> LLMResult: ...


def request_hash(model: str, system: str, user: str) -> str:
    digest = hashlib.sha256()
    for part in (model, system, user):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


# --------------------------------------------------------------------------- real client
class AnthropicLLMClient:
    def __init__(
        self,
        model: str = "claude-opus-5",
        effort: str = "medium",
        max_tokens: int = 1024,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def _params(self, system: str, user: str, schema: dict) -> MessageCreateParamsNonStreaming:
        return MessageCreateParamsNonStreaming(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={
                "format": {"type": "json_schema", "schema": schema},
                "effort": self.effort,
            },
        )

    def complete(self, system: str, user: str, schema: dict) -> LLMResult:
        response = self._client.messages.create(**self._params(system, user, schema))
        return _result_from_message(response)

    # ---- Message Batches: same request shape, asynchronous, half the price
    def submit_batch(self, items: Iterable[tuple[str, str, str]], schema: dict) -> str:
        """`items` are (custom_id, system, user). Returns the batch id."""
        requests = [
            Request(custom_id=custom_id, params=self._params(system, user, schema))
            for custom_id, system, user in items
        ]
        return self._client.messages.batches.create(requests=requests).id

    def wait_batch(
        self,
        batch_id: str,
        poll_seconds: int = 30,
        on_poll: Callable[[str, int], None] | None = None,
    ) -> None:
        while True:
            batch = self._client.messages.batches.retrieve(batch_id)
            if on_poll:
                on_poll(batch.processing_status, batch.request_counts.processing)
            if batch.processing_status == "ended":
                return
            time.sleep(poll_seconds)

    def iter_batch_results(self, batch_id: str) -> Iterator[tuple[str, LLMResult | str]]:
        """Yields (custom_id, LLMResult) or (custom_id, error_kind) in arrival order."""
        for item in self._client.messages.batches.results(batch_id):
            if item.result.type == "succeeded":
                yield item.custom_id, _result_from_message(item.result.message)
            elif item.result.type == "errored":
                yield item.custom_id, f"errored:{item.result.error.type}"
            else:
                yield item.custom_id, item.result.type  # canceled | expired


def _result_from_message(message) -> LLMResult:
    text = next((b.text for b in message.content if b.type == "text"), None)
    usage = message.usage
    return LLMResult(
        text=None if message.stop_reason == "refusal" else text,
        stop_reason=message.stop_reason or "unknown",
        model=message.model,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )


# --------------------------------------------------------------------------- fixtures
class FixtureLLMClient:
    def __init__(self, directory: Path, model: str = "claude-opus-5") -> None:
        self.directory = Path(directory)
        self.model = model

    def complete(self, system: str, user: str, schema: dict) -> LLMResult:
        path = self.directory / f"{request_hash(self.model, system, user)}.json"
        if not path.exists():
            raise FixtureMissError(path.name)
        data = json.loads(path.read_text(encoding="utf-8"))
        return LLMResult(**data)


class RecordingLLMClient:
    def __init__(self, inner: LLMClient, directory: Path) -> None:
        self.inner = inner
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def model(self) -> str:
        return self.inner.model

    def complete(self, system: str, user: str, schema: dict) -> LLMResult:
        result = self.inner.complete(system, user, schema)
        path = self.directory / f"{request_hash(self.model, system, user)}.json"
        path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")
        return result


# --------------------------------------------------------------------------- scorer
class LLMScorer:
    def __init__(
        self, client: LLMClient, profile: Profile, fallback: HeuristicScorer | None = None
    ) -> None:
        self.client = client
        self.fallback = fallback
        self.system = build_system(profile)
        self.schema = llm_output_schema()
        self.name = f"llm:{client.model}"

    def score(self, job: Job) -> ScoreRecord | None:
        started = perf_counter()
        try:
            result = self.client.complete(self.system, build_user(job), self.schema)
        except FixtureMissError:
            log.info("no fixture for %s; using heuristic", job.key)
            return self._fallback(job)
        except anthropic.RateLimitError as exc:
            log.warning("rate limited on %s: %s", job.key, exc.message)
            return None
        except anthropic.APIStatusError as exc:
            log.warning("API error %s on %s: %s", exc.status_code, job.key, exc.message)
            return None
        except anthropic.APIConnectionError as exc:
            log.warning("connection error on %s: %s", job.key, exc)
            return None
        return self._record(job, result, started)

    def score_batch(
        self,
        jobs: list[Job],
        poll_seconds: int = 30,
        on_poll: Callable[[str, int], None] | None = None,
    ) -> tuple[list[ScoreRecord], list[str]]:
        """Score many jobs through the Message Batches API. Returns (records, failed_keys)."""
        if not isinstance(self.client, AnthropicLLMClient):
            raise TypeError("batch scoring needs the real Anthropic client")
        by_id = {job.key: job for job in jobs}
        batch_id = self.client.submit_batch(
            ((job.key, self.system, build_user(job)) for job in jobs), self.schema
        )
        log.info("submitted batch %s with %d requests", batch_id, len(jobs))
        self.client.wait_batch(batch_id, poll_seconds, on_poll)
        records: list[ScoreRecord] = []
        failed: list[str] = []
        for custom_id, outcome in self.client.iter_batch_results(batch_id):
            job = by_id.get(custom_id)
            if job is None:
                continue
            if isinstance(outcome, str):
                log.warning("batch item %s %s", custom_id, outcome)
                failed.append(custom_id)
                continue
            record = self._record(job, outcome, None)
            (records.append(record) if record else failed.append(custom_id))
        return records, failed

    # ---- helpers
    def _record(self, job: Job, result: LLMResult, started: float | None) -> ScoreRecord | None:
        if result.stop_reason == "refusal" or not result.text:
            log.warning("no answer for %s (stop_reason=%s)", job.key, result.stop_reason)
            return None
        try:
            score = JobScore.model_validate_json(result.text).clamped()
        except ValidationError as exc:
            log.warning("schema rejected answer for %s: %s", job.key, exc.errors()[0].get("msg"))
            return self._fallback(job)
        return ScoreRecord(
            job_key=job.key,
            score=score,
            scorer=f"llm:{result.model}",
            scored_at=datetime.now(UTC),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            latency_ms=int((perf_counter() - started) * 1000) if started is not None else 0,
        )

    def _fallback(self, job: Job) -> ScoreRecord | None:
        return self.fallback.score(job) if self.fallback else None
