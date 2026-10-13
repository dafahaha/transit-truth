# `transit-truth verify` — model-identity verification

`verify` is a stateless, pipelinable check: given an OpenAI-compatible endpoint
and the model it *claims* to serve, it runs a bounded battery of black-box
probes and emits a single machine-readable JSON report.

```
transit-truth verify --base-url https://relay.example/v1 --model gpt-4o-mini
```

The API key is read from the environment (`TRANSIT_TRUTH_API_KEY` by default, or
`--api-key-env`). It is **never** written to disk, logged, or included in the
report.

## Verdict (three states)

| verdict | meaning |
|---|---|
| `pass` | observed fingerprint is statistically consistent with the reference. |
| `suspicious` | observed fingerprint differs significantly (e.g. wrong model family). |
| `insufficient_evidence` | no reference, sample too small, or an error — we do **not** guess. |

A black-box result is **probabilistic auxiliary evidence, not a cryptographic
proof** and not a verdict on authenticity.

## Report shape

```json
{
  "schema": "transit-truth/verify-report/v1",
  "claimed_model": "gpt-4o-mini",
  "endpoint_base_url": "https://relay.example",
  "timestamp": "2026-10-14T...",
  "verdict": "pass",
  "confidence": "medium",
  "statistics": {
    "matched_reference_model": "gpt-4o-mini",
    "posterior": 0.87,
    "chi2_pvalue": 0.9,
    "tokenizer_consistency": {"score": 1.0, "verdict": "match"}
  },
  "observations": {"tokenizer": {...}, "behavioral": {...}},
  "disclaimer": "..."
}
```

Exit codes: `0` pass, `3` suspicious, `2` error.

## Reference fingerprints

- `data/baselines/` — real collected baselines (`gpt-4o-mini`, `gpt-4o`).
- `data/fingerprints/` — open-source catalog (Qwen real tokenizer; see its
  README for honest coverage status).
- Closed-model (GPT/Claude/Gemini) fingerprints require the operator's own keys.

## Self-hosted reference backend

Generate/compare reference fingerprints without a paid key:

```
transit-truth reference-server --model qwen2.5-0.5b-instruct --port 8765
transit-truth verify --base-url http://127.0.0.1:8765/v1 \
    --model qwen2.5-0.5b-instruct --allow-local
```

`--allow-local` is required for loopback targets; the default enforces the
public-URL SSRF guard.

> **Honesty: tokenizer-only is NOT a certification.** The open-source catalog
> currently ships tokenizer counts only (no behavioral distribution). Tokenizer
> counts are *self-reported* by the endpoint in `usage.prompt_tokens`, and the
> probe prompts + reference numbers are public — a fake relay can report them
> without running the real model. Therefore, when the reference has no behavioral
> distribution, `verify` deliberately caps the verdict at `insufficient_evidence`
> even when `tokenizer_consistency.verdict == "match"`. A `pass` requires
> behavioral evidence that overlaps a real reference distribution. Tokenizer counts
> are measured on the **system_prompt + user_prompt** caliber (the full request
> the battery sends), so a self-hosted reference server's reported counts line up
> with the on-disk reference.

## Deterministic-replay honesty (v0.4.2)

The shipped behavioral baselines are collected at **temperature=0**, which makes
them *point masses*: e.g. `beh-number-1-10` for gpt-4o-mini answers `"7"` every
single time. The probe prompts and the baselines ship in this public repo, so an
adversary does not need luck — they can hard-code ~4 public modal strings
(`"7"` / `"Heads"` / `"Cerulean"` / `"4"`) and reproduce a behavioral "match"
**deterministically**.

`verify` therefore measures each probe's empirical entropy / mode fraction:

- when overlapping behavioral responses are point-mass (zero entropy, mode
  fraction ≈ 1.0), the report sets
  `statistics.deterministic_replay_risk.flag = true` with the degenerate probes
  listed;
- such a behavioral "match" can no longer carry an unreserved high-confidence
  `pass`: the verdict may still be `pass`, but `confidence` is capped to `low`.

**Bottom line:** tokenizer counts are a weak, self-reported signal; behavioral
probes at temperature=0 are replayable; and neither is a proof. Official
cryptographic attestation (provider-signed responses) remains the only endgame —
this tool is probabilistic auxiliary evidence, nothing more.

## SDK

```python
from app.verify import verify_endpoint, verify_endpoint_sync

report = verify_endpoint_sync(
    base_url="https://relay.example/v1", claimed_model="gpt-4o-mini"
)
```

## Observability (optional)

```python
from app.verify.otel import to_openinference_attributes, emit_otel_span

attrs = to_openinference_attributes(report)   # plain dict, no dependency
emit_otel_span(report)                         # real OTel span if installed
```

See `examples/` for DeepEval-style metric and Langfuse score integrations.

## ε-dilution (budgeted sequential test)

A relay may route only a fraction ε of traffic to a fake model. Estimate what a
request budget can detect:

```python
from app.verify.sequential import budgeted_sequential_analysis
print(budgeted_sequential_analysis(epsilon=0.1, budget=100))
```
