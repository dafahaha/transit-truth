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

    responses = await asyncio.gather(*[call(p) for _, p in jobs])
    result.requests_used = len(jobs)

    for (kind, probe), (_, raw) in zip(jobs, responses):
        if "error" in raw:
            result.failures += 1
            continue
        if kind == "tok":
            usage = raw.get("usage", {})
            pt = usage.get("prompt_tokens")
            if pt is not None:
                # Average repeated tokenizer samples if any (here: one each).
                prev = result.observed_tokenizer.get(probe.id)
                result.observed_tokenizer[probe.id] = float(
                    pt if prev is None else (prev + float(pt)) / 2
                )
        else:
            try:
                content = raw["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, TypeError):
                result.failures += 1
                continue
            result.observed_behavioral.setdefault(probe.id, []).append(content)

    return result
