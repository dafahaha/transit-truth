# Changelog

All notable changes to TransitTruth will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Statistical analyzer** (`app/core/statistical_analyzer.py`): Rigorous statistical methods for model verification
  - Kolmogorov-Smirnov test for tokenizer distribution comparison
  - Chi-square test for behavioral distribution comparison
  - Bayesian updating with credible intervals
  - False positive/negative rate estimation
  - Default baseline distributions for GPT-4, GPT-3.5, Claude families
- **Continuous monitoring** (`app/core/monitor.py`): Monitor relays at regular intervals
  - 4 alert detection rules (absolute score, score drop, token discrepancy, high latency)
  - 4 alert channels (console, email, Telegram, webhook)
  - History persistence to JSON files
  - Example config at `examples/monitor-config.example.json`
- **One-click contribution** (`app/utils/contributor.py`): Automatically create GitHub Issues
  - Server-side GitHub API integration
  - Token verification
  - Auto-formatted issue body from audit template
  - Anonymous or attributed contribution
- **Standalone frontend** (`standalone/index.html`): Pure frontend version, no backend required
  - All API requests directly from browser
  - Auto-detect base URL from 12 known relays
  - Auto-load model list via `/models` endpoint
  - Quick/deep mode toggle
  - js-tiktoken for client-side token counting
  - Export JSON, copy result, contribute to ranking
- **Initial ranking data** (`data/initial_ranking.json`): 12 audit results for cold start
  - 4 verified entries (official APIs)
  - 2 wolfai.top real audit results
  - 6 community-estimated entries
  - Covers 10 relays and 5 models
- **pyproject.toml**: Full Python package configuration
  - `pip install transit-truth` support
  - `transit-truth` CLI entry point
  - Dependencies: fastapi, uvicorn, httpx, tiktoken, numpy, scipy, rich, click
  - Dev dependencies: pytest, flake8, mypy, ruff
  - Ruff and mypy configuration

### Changed
- **Token "inflation" → "discrepancy"**: Renamed all references to avoid implying fraud
  - Added `chat_template_overhead` field to estimate legitimate token overhead
  - Adjusted suspicious threshold from 15% to 20% (after chat template deduction)
  - Added `discrepancy_note` field with plain-language explanation
  - Updated HTML report, frontend, and CLI displays
- **Capability probes**: Expanded from 4 to 10 probes
  - Added: knowledge cutoff, reasoning chain (bat-and-ball), code bug fix, multilingual, context length, math word problem
  - Added difficulty tiers (easy/medium/hard) and model tier estimation
  - Increased default capability probe count from 4 to 6
- **Probe randomization**: Enhanced anti-detection measures
  - Random probe execution order
  - Random startup delay (0.3-1.5s per probe)
  - Already had randomized probe content

### Improved
- **Anomaly detection**: Expanded from 2 to 5 rules
  - Score deviation >30 from median
  - Token inflation >200% or <0%
  - Latency >30s or <50ms (cached response detection)
  - Duplicate scores appearing 3+ times
  - Exact scores of 0 or 100
- **Contributor reputation system**: Weighted aggregation by contributor trust
  - Reputation score (0-100): audit count 40% + verified count 20% + unique relays 20% - anomaly penalty 20%
  - Reputation levels: Trusted/Established/Regular/New/Unknown
  - Weighted median aggregation (0.5x-1.5x weight based on reputation)
- **Disclaimer**: Expanded from 1 paragraph to 7 detailed points
  - Token discrepancy ≠ fraud
  - Fingerprint confidence <80% is not evidence
  - Ranking data is community-contributed, not independently verified
  - API key never leaves browser (standalone version)
  - Appeal channel via GitHub Issues

## [0.2.0] - 2026-09-12

### Added
- CLI tool with audit/list/export/benchmark commands
- 44 unit tests (now 46)
- Randomized probes for anti-defense
- HTML report generator
- Benchmark data collector
- CI/CD with GitHub Actions
- CONTRIBUTING, CODE_OF_CONDUCT, architecture docs, methodology docs
- 4 issue templates + PR template

### Changed
- Web UI: step-by-step form, auto-detect base URL, model dropdown, quick/deep modes
- Real-time progress bar
- Local audit history (localStorage)
- GitHub Issues as ranking database (0-cost)
- Ranking static page (GitHub Pages compatible)
- Contributor badges (SVG)

## [0.1.0] - 2026-09-10

### Added
- Initial release
- Core audit engine (token verification, model fingerprint, latency/protocol)
- 20 probes (8 tokenizer, 8 behavioral, 4 capability)
- Async HTTP client
- SQLite database
- FastAPI REST API
- Single-page frontend (4 tabs)
- Docker support
- README, LICENSE, .gitignore

[Unreleased]: https://github.com/dafahaha/transit-truth/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/dafahaha/transit-truth/releases/tag/v0.2.0
[0.1.0]: https://github.com/dafahaha/transit-truth/releases/tag/v0.1.0
