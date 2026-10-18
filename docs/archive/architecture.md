# TransitTruth Architecture

## Overview

TransitTruth is an open-source AI API relay audit tool. It verifies whether AI API relay services (中转站) are engaging in fraudulent practices such as token count inflation, model downgrading, and response caching.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │   Web UI     │  │   CLI Tool   │  │   REST API       │ │
│  │  (React/JS)  │  │  (argparse)  │  │  (FastAPI)       │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
└─────────┼───────────────────┼─────────────────────┼───────────┘
          │                   │                     │
          ▼                   ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      Application Layer                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Audit Engine                           │ │
│  │  (orchestrates all checks, generates scores & reports)  │ │
│  └──────────────┬──────────────────────────────────────────┘ │
│                 │                                              │
│  ┌──────────────▼───────┐  ┌──────────────────────────────┐ │
│  │   Detection Modules    │  │      Utility Modules         │ │
│  │  ┌──────────────────┐  │  │  ┌────────────────────────┐│ │
│  │  │ Token Verifier   │  │  │  │  Async HTTP Client     ││ │
│  │  ├──────────────────┤  │  │  ├────────────────────────┤│ │
│  │  │ Model Fingerprint│  │  │  │  Report Generator      ││ │
│  │  ├──────────────────┤  │  │  ├────────────────────────┤│ │
│  │  │ Latency Checker  │  │  │  │  Probe Randomizer      ││ │
│  │  ├──────────────────┤  │  │  └────────────────────────┘│ │
│  │  │ Protocol Checker │  │  │                              │ │
│  │  └──────────────────┘  │  │                              │ │
│  └─────────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                       Data Layer                              │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │   SQLite DB      │  │  Benchmark Data  │                 │
│  │  (audit history, │  │  (model          │                 │
│  │   rankings)      │  │   fingerprints)  │                 │
│  └──────────────────┘  └──────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                    External Services                          │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │  Relay API       │  │  Official API     │                 │
│  │  (under audit)   │  │  (for comparison) │                 │
│  └──────────────────┘  └──────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Audit Engine (`app/core/auditor.py`)

The central orchestrator that:
- Validates API availability
- Runs all enabled detection modules
- Aggregates results into an overall score (0-100)
- Determines trust level (high/medium/low/critical)
- Generates recommendations
- Saves results to the database

### 2. Detection Modules

#### Token Verifier (`app/core/token_check.py`)
- Sends test prompts to the relay and official API
- Compares `usage.prompt_tokens` and `usage.completion_tokens`
- Falls back to local `tiktoken` calculation if no official key
- Flags inflation >10% as suspicious

#### Model Fingerprinter (`app/core/fingerprint.py`)
Runs three categories of probes:
- **Tokenizer probes**: Crafted strings that tokenize differently across model families
- **Behavioral probes**: Random number/color/coin-flip questions with model-specific distribution biases
- **Capability probes**: Simple reasoning/code tests to differentiate model tiers

Analyzes results to detect:
- Family mismatch (e.g., claimed GPT-4o but detected as GPT-3.5 family)
- Tokenizer signature anomalies
- Capability failure rate

#### Latency Checker (`app/core/latency_protocol.py`)
- Sends 5 sample requests
- Measures P50/P95 latency, error rate
- Flags high latency (>10s) or high error rate (>20%)

#### Protocol Checker (`app/core/latency_protocol.py`)
- Validates OpenAI API response structure (id, object, created, model, choices, usage)
- Checks error format for invalid requests
- Verifies response headers
- Checks model field matches requested model

### 3. Probe System (`app/core/probes.py` + `app/core/randomized_probes.py`)

- **Fixed probes**: Base definitions with expected characteristics
- **Randomized probes**: Each audit generates unique probe content while preserving the measured characteristic
- Prevents relay services from whitelisting specific probe strings

### 4. Report Generator (`app/utils/report_generator.py`)
- Generates standalone HTML reports
- Includes overall score, check details, evidence, recommendations
- Self-contained (inline CSS, no external dependencies)

### 5. CLI Tool (`app/cli.py`)
- `audit`: Run an audit from command line
- `list`: View audit history
- `export`: Export audit report to HTML
- `benchmark`: Collect model fingerprint benchmark data

## Data Flow

### Audit Flow

```
User Input (API key, base URL, model)
    │
    ▼
Availability Check ──► Failed ──► Return error
    │
    ▼ Success
Generate Randomized Probes
    │
    ├──► Token Count Check (relay vs official/tiktoken)
    ├──► Model Fingerprint (tokenizer + behavioral + capability probes)
    ├──► Latency Check (5 samples, P50/P95)
    └──► Protocol Check (response structure, errors, headers)
    │
    ▼
Aggregate Scores → Overall Score (0-100)
    │
    ▼
Determine Trust Level → Generate Recommendations
    │
    ▼
Save to Database → Return Result / Generate Report
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI, asyncio |
| HTTP Client | httpx (async) |
| Token Calculation | tiktoken |
| Database | SQLite (via stdlib sqlite3) |
| Frontend | Vanilla HTML/CSS/JS (no build step) |
| Testing | pytest |
| CI/CD | GitHub Actions |
| Deployment | Docker / docker-compose |

## Design Principles

1. **Open by default**: All detection logic is transparent and auditable
2. **Privacy-first**: API keys are never stored; all processing is local
3. **Randomized probes**: Prevents relay services from detecting and defending against fixed probes
4. **Multi-dimensional verification**: No single check is definitive; cross-validation reduces false positives
5. **Conservative claims**: Results are based on finite samples; we never claim absolute certainty
6. **Extensible probe system**: New probes can be added without changing core architecture

## Future Architecture Considerations

- **Pluggable detection modules**: Allow third-party detection modules via entry points
- **Distributed auditing**: Support for running audits from multiple geographic locations
- **Streaming audit**: Real-time monitoring of relay services
- **Benchmark database**: Curated, versioned fingerprint database for known models
- **Plugin system**: For custom probe types and analysis methods
