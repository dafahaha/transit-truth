"""Bounded probe battery for the stateless verifier.

Runs a *bounded* number of probes against an OpenAI-compatible endpoint and
collects the minimal observations needed by :class:`StatisticalAnalyzer`:

- ``{probe_id: prompt_tokens}`` for tokenizer probes (from ``usage``).
- ``{probe_id: [response, ...]}`` for behavioral probes (from content).

Hard guardrails:
- concurrency is capped at 2 (operators asked for low, polite probing);
- total requests are capped by ``max_requests``;
- every request goes through the existing retry/timeout machinery.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..core.probes import (
    BEHAVIORAL_PROBES,
    TOKENIZER_PROBES,
    Probe,
)
from ..utils.http_client import AsyncAPIClient

# Default bounded battery: a handful of tokenizer probes (run once) plus a
# few behavioral probes (run a few times each). Chosen to overlap the shipped
# real baseline (gpt-4o-mini) so the offline e2e path has something to compare.
DEFAULT_TOKENIZER_IDS = [
    "tok-whitespace",
    "tok-code",
    "tok-url",
    "tok-mixed-unicode",
    "tok-repeated-chars",
]
DEFAULT_BEHAVIORAL_IDS = [
    "beh-number-1-10",
    "beh-coin-flip",
    "beh-random-color",
    "beh-dice-roll",
]


@dataclass
class BatteryResult:
    observed_tokenizer: dict[str, float] = field(default_factory=dict)
    observed_behavioral: dict[str, list[str]] = field(default_factory=dict)
    requests_used: int = 0
    failures: int = 0
    # The CLIENT-SENT behavioral probe universe (the denominator the coverage
    # gate uses). A backend cannot shrink the evaluated set by selective
    # non-response: we record exactly which behavioral probes we attempted, so a
    # probe that 504s every repeat is still counted as n=0 -- not invisible.
    planned_behavioral_ids: list[str] = field(default_factory=list)


def _by_id(probes: list[Probe], wanted: list[str]) -> list[Probe]:
    index = {p.id: p for p in probes}
    return [index[pid] for pid in wanted if pid in index]


async def run_battery(
    client: AsyncAPIClient,
    claimed_model: str,
    *,
    max_requests: int = 20,
    behavioral_samples: int = 3,
    concurrency: int = 2,
    tokenizer_ids: list[str] | None = None,
    behavioral_ids: list[str] | None = None,
) -> BatteryResult:
    """Run the bounded battery and return raw observations.

    Failures on individual probes are counted but do not abort the run; the
    caller decides whether the remaining evidence suffices.
    """
    tok_probes = _by_id(TOKENIZER_PROBES, tokenizer_ids or DEFAULT_TOKENIZER_IDS)
    beh_probes = _by_id(BEHAVIORAL_PROBES, behavioral_ids or DEFAULT_BEHAVIORAL_IDS)

    result = BatteryResult()
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 2)))

    async def call(probe: Probe) -> tuple[Probe, dict]:
        async with semaphore:
            return probe, await client.chat_completion(
                model=claimed_model,
                messages=[
                    {"role": "system", "content": probe.system_prompt},
                    {"role": "user", "content": probe.prompt},
                ],
                temperature=probe.temperature,
                max_tokens=probe.max_tokens,
            )

    # Build the work list and trim to the request budget.
    jobs: list[tuple[str, Probe]] = []  # (kind, probe)
    for p in tok_probes:
        jobs.append(("tok", p))
    for p in beh_probes:
        for _ in range(behavioral_samples):
            jobs.append(("beh", p))
    jobs = jobs[:max_requests]

    # Record the actually-sent behavioral probe universe (post-budget-trim). A
    # probe we sent but got zero usable responses for IS evaluated as n=0.
    planned_beh: list[str] = []
    for kind, probe in jobs:
        if kind == "beh" and probe.id not in planned_beh:
            planned_beh.append(probe.id)

    # return_exceptions=True is the second half of the v0.4.7 P2 guard: even
    # if a per-request future raises (e.g. an httpx-level bug, an unexpected
    # stdlib exception we forgot to catch in chat_completion), it must only
    # degrade that one probe, never abort the whole battery and discard the
    # ~16 good evidence rows with it.
    responses = await asyncio.gather(
        *[call(p) for _, p in jobs], return_exceptions=True
    )
    result.requests_used = len(jobs)
    result.planned_behavioral_ids = planned_beh

    for (kind, probe), resp in zip(jobs, responses):
        # If this individual request raised (any exception), count it as one
        # failed observation and move on -- never re-raise.
        if isinstance(resp, BaseException):
            result.failures += 1
            continue
        _, raw = resp
        if "error" in raw:
            result.failures += 1
            continue
        try:
            if kind == "tok":
                # A backend may send ``usage: null`` (or omit it). Treat a
                # malformed usage block as ONE failed observation -- never let
                # ``None.get(...)`` raise AttributeError and abort the whole
                # battery, discarding the ~16 good evidence rows with it.
                usage = raw.get("usage")
                if not isinstance(usage, dict):
                    raise ValueError("usage block is missing/not an object")
                pt = usage.get("prompt_tokens")
                if pt is None:
                    continue
                pt = float(pt)
                # Average repeated tokenizer samples if any (here: one each).
                prev = result.observed_tokenizer.get(probe.id)
                result.observed_tokenizer[probe.id] = (
                    pt if prev is None else (prev + pt) / 2
                )
            else:
                # ``content`` may legitimately be JSON null (refusal / stub).
                # A single such repeat only counts as one failed/missing
                # observation (the coverage / thin-evidence gate then handles
                # it); it must never crash extraction and nuke the battery.
                message = raw["choices"][0].get("message")
                if not isinstance(message, dict):
                    raise ValueError("message is missing/not an object")
                content = message.get("content")
                if not isinstance(content, str):
                    raise ValueError("content is null/not a string")
                result.observed_behavioral.setdefault(probe.id, []).append(
                    content.strip()
                )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            result.failures += 1
            continue

    return result
