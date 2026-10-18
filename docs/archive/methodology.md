# TransitTruth Detection Methodology

This document describes the technical methodology behind TransitTruth's detection capabilities. It is intended for researchers, contributors, and users who want to understand how the tool works under the hood.

## Table of Contents

1. [Threat Model](#threat-model)
2. [Token Count Verification](#token-count-verification)
3. [Model Fingerprinting](#model-fingerprinting)
4. [Latency & Availability Analysis](#latency--availability-analysis)
5. [Protocol Compliance Checking](#protocol-compliance-checking)
6. [Randomized Probe Strategy](#randomized-probe-strategy)
7. [Scoring & Trust Levels](#scoring--trust-levels)
8. [Limitations & False Positives](#limitations--false-positives)
9. [Academic Foundations](#academic-foundations)

## Threat Model

TransitTruth detects the following types of relay service fraud:

| Threat | Description | Detection Method |
|--------|-------------|-----------------|
| **Token inflation** | Reporting more tokens than actually used | Compare with official API or local tiktoken |
| **Model downgrade** | Serving a lower-tier model while charging for a higher-tier one | Model fingerprinting (tokenizer + behavioral + capability) |
| **Response caching** | Returning cached responses instead of calling the API | Latency analysis, behavioral probe consistency |
| **Protocol manipulation** | Altering response structure, headers, or error formats | Protocol compliance checking |
| **Selective fraud** | Only committing fraud under certain conditions (e.g., high load) | Randomized probes, multi-sample analysis |

## Token Count Verification

### Methodology

1. Send a set of standardized test prompts to the relay service
2. Record the `usage.prompt_tokens` and `usage.completion_tokens` from the response
3. Compare against:
   - **Official API**: If an official API key is provided, send the same prompts to the official endpoint
   - **Local calculation**: If no official key, use `tiktoken` to calculate expected token counts locally
4. Compute inflation percentage: `(reported - expected) / expected * 100`

### Test Prompts

We use 5 diverse prompts covering:
- Simple English text
- Technical explanation
- Code generation
- Protocol/networking concepts
- Multi-language translation

### Thresholds

- **Normal**: <5% difference (accounting for chat template overhead variations)
- **Warning**: 5-10% difference
- **Suspicious**: >10% difference

### Limitations

- Chat template overhead can vary between implementations
- System prompts may differ, affecting prompt token counts
- Local tiktoken calculation doesn't account for chat template tokens

## Model Fingerprinting

Model fingerprinting is the core technical innovation of TransitTruth. It uses three complementary approaches to identify the true model family behind an API endpoint.

### 1. Tokenizer Fingerprinting

**Principle**: Different model families use different tokenizers, which produce different token counts for the same input text.

**Method**:
- Send carefully crafted strings that maximize tokenizer differences:
  - Long digit runs (GPT tokenizes digits in pairs, others differ)
  - CJK character sequences
  - Emoji sequences
  - Multiple whitespace runs
  - Code snippets
  - URLs with query parameters
  - Mixed Unicode (accented + CJK + Korean + Arabic)
  - Repeated single characters
- Record `usage.prompt_tokens` for each
- Compare the signature against known model family benchmarks

**Why it works**: Tokenizer differences are fundamental to the model architecture and cannot be easily faked without reimplementing the exact tokenizer.

### 2. Behavioral Fingerprinting

**Principle**: Different models exhibit measurable distribution biases when asked to generate "random" outputs.

**Method**:
- Ask multiple types of "random" questions:
  - Random number (1-100, 1-10)
  - Random color
  - Coin flip (heads/tails)
  - Random letter (A-Z)
  - Dice roll (1-6)
  - Random animal
  - Random day of week
- Sample each question 3-5 times at temperature=1.0
- Record the distribution of responses
- Compare distribution characteristics against known model benchmarks

**Why it works**: These biases arise from the model's training data and tokenization, and are difficult to eliminate without fundamentally changing the model.

**Research basis**: This approach is inspired by work on LLM behavioral fingerprinting, including studies showing that models have identifiable "randomness" signatures.

### 3. Capability Testing

**Principle**: Different model tiers have measurably different capabilities on simple reasoning and code tasks.

**Method**:
- Send a small set of capability probes:
  - Two-digit multiplication (e.g., 17 * 23)
  - Basic logical reasoning (syllogism evaluation)
  - Python one-liner generation
  - Complex instruction following (count with skip)
- Use temperature=0 for determinism
- Check answers against expected results
- Calculate pass rate

**Why it works**: A GPT-3.5 model will fail more of these tests than a GPT-4o model, providing a tier differentiation signal.

### Fingerprint Analysis

The three signals are combined to produce:
- **Detected family**: Best-guess model family based on tokenizer signature
- **Family match**: Whether detected family matches claimed family
- **Confidence**: How confident the analysis is (0-1)
- **Suspicious**: Whether any significant anomalies were detected

## Latency & Availability Analysis

### Methodology

1. Send 5 lightweight requests ("Say 'pong N'")
2. Measure latency for each request
3. Calculate:
   - Average latency
   - P50 (median) latency
   - P95 latency
   - Minimum/maximum latency
   - Error rate

### Scoring

- **Error penalty**: `error_rate * 50` points
- **Latency penalty**: `min(avg_latency_ms / 100, 30)` points (capped at 30)
- **Score**: `max(0, 100 - error_penalty - latency_penalty)`

### What it detects

- **Caching**: Abnormally low and consistent latency may indicate cached responses
- **Overload**: High latency or error rates may indicate the service is overloaded
- **Instability**: High variance in latency may indicate unreliable infrastructure

## Protocol Compliance Checking

### Methodology

1. **Response structure validation**:
   - Check for required fields: `id`, `object`, `created`, `model`, `choices`, `usage`
   - Validate `choices[0]` structure: `index`, `message`, `finish_reason`
   - Validate `message` structure: `role`, `content`
   - Validate `usage` structure: `prompt_tokens`, `completion_tokens`, `total_tokens`

2. **Model field verification**:
   - Check that `response.model` matches the requested model

3. **Error format validation**:
   - Send a request with an invalid model name
   - Check that the error response follows OpenAI error format

4. **Header inspection**:
   - Check for standard headers (content-type, request-id, rate-limit)

### Scoring

Score = `(passed_checks / total_checks) * 100`

## Randomized Probe Strategy

### Problem

Fixed probe strings can be detected and whitelisted by relay services. A sophisticated relay could:
- Detect known probe patterns
- Return "normal" results for probes while continuing fraud for normal requests

### Solution

TransitTruth randomizes probe content for each audit while preserving the measured characteristic:

| Probe Type | Randomization | Preserved Characteristic |
|-----------|---------------|------------------------|
| Digit run | Random digits | Long sequence of digits |
| CJK | Random Chinese chars | CJK character sequence |
| Emoji | Random emoji selection | Emoji sequence |
| Code | Random variable names/numbers | Code snippet structure |
| URL | Random domain/path/model | URL with query parameters |
| Random number | Random wording | Request for random number in range |
| Math | Random operands | Two-digit multiplication |
| Logic | Random entities/attributes | Syllogism structure |

### Implementation

- `ProbeRandomizer` class with configurable seed
- Each audit generates a unique set of probes
- Seed is recorded for reproducibility
- Original probe IDs are tracked for analysis

### Effectiveness

- Relay services cannot whitelist specific strings (they change every audit)
- Pattern detection requires understanding the *intent* of the probe, not just matching strings
- Multiple probe types make comprehensive defense expensive

## Scoring & Trust Levels

### Overall Score

The overall score is the arithmetic mean of all enabled check scores:

```
overall_score = sum(check_scores) / number_of_checks
```

### Trust Levels

| Level | Score Range | Criteria |
|-------|------------|----------|
| **High** | 80-100 | No critical failures, all checks pass |
| **Medium** | 60-79 | Minor issues, no critical fraud indicators |
| **Low** | 40-59 | Significant issues, possible fraud |
| **Critical** | 0-39 | Critical failure in token or fingerprint check |

**Critical override**: If either token count check or model fingerprint check fails (indicating likely fraud), trust level is automatically set to "critical" regardless of overall score.

## Limitations & False Positives

### Known Limitations

1. **Finite sample size**: Results are based on a limited number of probes; a relay could commit fraud selectively
2. **Model evolution**: Models are updated over time, which can change fingerprint characteristics
3. **Fine-tuned models**: Fine-tuned models may have different behavioral signatures
4. **System prompt effects**: Different system prompts can shift behavioral fingerprints
5. **Regional variations**: API behavior may vary by region or endpoint
6. **New models**: Recently released models may not have benchmark data yet

### False Positive Scenarios

- **Legitimate token count differences**: Different chat templates can cause 5-10% token count variation
- **Model updates**: A model update can temporarily change fingerprint characteristics
- **Load-based routing**: Some services route to different model versions based on load
- **A/B testing**: Services may A/B test model versions, leading to inconsistent results

### Mitigation

- Conservative thresholds (10%+ inflation才 flagged)
- Multi-dimensional verification (no single check is definitive)
- Clear reporting of methodology and limitations
- Recommendation to re-audit if results are borderline

## Academic Foundations

TransitTruth builds on the following areas of research:

### Model Fingerprinting

- **Tokenizer-based identification**: Leveraging differences in subword tokenization algorithms
- **Behavioral fingerprinting**: Distribution analysis of model outputs on "random" generation tasks
- **Capability-based tiering**: Using standardized test sets to differentiate model capabilities

### API Security & Audit

- **Black-box API auditing**: Verifying API behavior without access to internals
- **Supply chain security**: Ensuring third-party API services deliver what they promise
- **Cryptographic attestation**: Approaches like SILENT-BENCH for verifiable API auditing

### Related Work

- **CoIn** (arXiv 2505.13778): Counting invisible reasoning tokens in opaque LLM APIs using Merkle hash trees
- **SILENT-BENCH**: Cryptographically-attested forensic auditing of LLM API gateways
- **AgentProv** (arXiv 2609.00052): Auditing agentic LLM API providers via tool-use policy probes
- **llm-verify**: Open-source Rust tool for black-box LLM API endpoint verification

### Research Opportunities

TransitTruth's methodology opens several research directions:

1. **Large-scale relay audit studies**: Systematic auditing of the relay service ecosystem
2. **Adversarial probe design**: Developing probes that are maximally resistant to relay defense
3. **Model fingerprint databases**: Curated, versioned databases of model fingerprints
4. **Real-time fraud detection**: Streaming audit approaches for ongoing monitoring
5. **Cross-model transfer**: Applying fingerprinting techniques to new model architectures
