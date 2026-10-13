# Third-party notices

TransitTruth is MIT-licensed. It reuses *methods and data* from the following
open-source projects. No source code is copied verbatim; attributions are below.
Licenses were verified against each project's canonical source.

## Statistical forensics / fingerprinting methods

- **knowlyr ModelAudit** (`knowlyr-modelaudit`) — *MIT License*.
  Statistical model-forensics concepts (distillation detection, behavioral +
  tokenizer fingerprinting) informed the probe/statistics design. We
  re-implemented the statistics in this repo rather than vendoring code.
  https://pypi.org/project/knowlyr-modelaudit/

- **LLMmap** (USENIX Security 2025) — the black-box behavioral-fingerprinting /
  relay-mapping study that the knowlyr ModelAudit built-in method derives from.
  Our same lineage of open-ended, cheap behavioral probes (rather than a curated
  benchmark) follows LLMmap; the statistics here are re-implemented from scratch.

- **Zenodo: "Single-token output distributions as behavioral fingerprints of
  large language models"** (Bruckner, Tomáš et al.) — *Creative Commons
  Attribution 4.0 International (CC-BY-4.0)*.
  The open-source behavioral reference distributions that the operator may load
  into `data/fingerprints/` are conceptually drawn from this dataset. It is NOT
  shipped in the repo; collect it and attribute the authors when used.
  https://zenodo.org/records/21278557

## Observability / integration libraries (optional, not required)

- **OpenTelemetry** — *Apache License 2.0*.
  https://opentelemetry.io/
- **OpenInference (GenAI semantic conventions)** — *Apache License 2.0*.
  https://github.com/Arize-ai/openinference
  `app/verify/otel.py` emits OpenInference-style attributes but does not vendor it.
- **DeepEval** — *Apache License 2.0*. Example only in `examples/deepeval_metric.py`.
  https://github.com/confident-ai/deepeval
- **Langfuse** — *MIT License*. Example only in `examples/langfuse_score.py`.
  https://github.com/langfuse/langfuse

## Model tokenizers used to build reference fingerprints

- **Qwen / Qwen2.5 tokenizer** (Alibaba) — used to measure real prompt-token
  counts in `data/fingerprints/`. Subject to the Qwen model license (Apache-2.0
  for Qwen2.5). Counts are facts, not copyrighted expression; attribution here.

## Baseline third-party runtime dependencies

- FastAPI (MIT), httpx (BSD-3-Clause), SciPy (BSD-3-Clause), NumPy (BSD-3),
  tiktoken (MIT), uvicorn (BSD-3-Clause). See `backend/requirements.txt`.
