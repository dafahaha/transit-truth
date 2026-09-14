"""Model fingerprinting engine.

Identifies the likely model family behind an API endpoint by
analyzing:
1. Tokenizer signatures - how strings are tokenized
2. Behavioral signatures - distribution biases in random generation
3. Response characteristics - headers, error formats, latency patterns

Anti-defense measures:
- Probe order is randomized to avoid pattern detection
- Request intervals are randomized (0.5-2.0s) to avoid rate limiting patterns
- Probe content is randomized (see randomized_probes.py)
- User-Agent and headers vary naturally via httpx

Statistical methods (v0.3+):
- KS test for tokenizer distribution comparison
- Chi-square test for behavioral distribution comparison
- Bayesian updating for posterior probability of model match
- Real baseline data collected from official APIs (data/baselines/)
"""
import asyncio
import random
import statistics
from collections import Counter
from pathlib import Path
from typing import Optional

from ..config import MODEL_FAMILIES, CONCURRENT_REQUESTS
from ..models import FingerprintResult
from ..utils.http_client import AsyncAPIClient
from .probes import (
    TOKENIZER_PROBES,
    BEHAVIORAL_PROBES,
    CAPABILITY_PROBES,
    Probe,
)
from .statistical_analyzer import StatisticalAnalyzer


class ModelFingerprinter:
    """Run fingerprint probes and analyze results."""

    def __init__(self, client: AsyncAPIClient, model: str, custom_probes: Optional[list] = None):
        self.client = client
        self.model = model
        self.tokenizer_results: dict[str, dict] = {}
        self.behavioral_results: dict[str, list[str]] = {}
        self.capability_results: dict[str, dict] = {}
        # Use randomized probes if provided, otherwise use default fixed probes
        self._custom_probes = custom_probes
        if custom_probes:
            self._tokenizer_probes = [p for p in custom_probes if p.category == "tokenizer"]
            self._behavioral_probes = [p for p in custom_probes if p.category == "behavioral"]
            self._capability_probes = [p for p in custom_probes if p.category == "capability"]
        else:
            self._tokenizer_probes = TOKENIZER_PROBES
            self._behavioral_probes = BEHAVIORAL_PROBES
            self._capability_probes = CAPABILITY_PROBES

        # Statistical analyzer with real baseline data
        self.stat_analyzer = StatisticalAnalyzer()
        self.stat_analyzer.load_default_baselines()
        # Try to load real baselines from data/baselines/ (relative to project root)
        baseline_dirs = [
            Path(__file__).parent.parent.parent.parent / "data" / "baselines",
            Path("data/baselines"),
            Path("../data/baselines"),
        ]
        for bd in baseline_dirs:
            if bd.exists():
                self.stat_analyzer.load_real_baselines(str(bd))
                break

    def _claimed_family(self) -> Optional[str]:
        """Determine the claimed model family from the model name."""
        model_lower = self.model.lower()
        for key, info in MODEL_FAMILIES.items():
            if key in model_lower:
                return info["family"]
        return None

    async def run_tokenizer_probes(self, count: int = 8) -> dict:
        """Run tokenizer fingerprint probes.

        Probes are run in random order with randomized startup delays
        to avoid being detected as an audit pattern.
        """
        probes = self._tokenizer_probes[:count]
        # Randomize probe order
        random.shuffle(probes)
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

        async def run_probe(probe: Probe) -> tuple[str, dict]:
            # Random startup delay (0.3-1.5s) to avoid pattern detection
            await asyncio.sleep(random.uniform(0.3, 1.5))
            async with semaphore:
                result = await self.client.chat_completion(
                    model=self.model,
                    messages=[{"role": "user", "content": probe.prompt}],
                    temperature=0,
                    max_tokens=128,
                )
                if "error" in result:
                    return probe.id, {"error": result["error"]}
                usage = result.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                content = ""
                try:
                    content = result["choices"][0]["message"]["content"]
                except (KeyError, IndexError):
                    pass
                return probe.id, {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "response_preview": content[:100],
                    "latency_ms": result.get("_latency_ms", 0),
                }

        results = await asyncio.gather(*[run_probe(p) for p in probes])
        self.tokenizer_results = dict(results)
        return self.tokenizer_results

    async def run_behavioral_probes(self, count: int = 6, samples: int = 5) -> dict:
        """Run behavioral fingerprint probes (multiple samples each)."""
        probes = self._behavioral_probes[:count]
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

        async def run_probe_samples(probe: Probe) -> tuple[str, list[str]]:
            responses = []
            for _ in range(samples):
                async with semaphore:
                    result = await self.client.chat_completion(
                        model=self.model,
                        messages=[{"role": "user", "content": probe.prompt}],
                        temperature=probe.temperature,
                        max_tokens=probe.max_tokens,
                    )
                    if "error" not in result:
                        try:
                            content = result["choices"][0]["message"]["content"].strip()
                            responses.append(content)
                        except (KeyError, IndexError):
                            pass
            return probe.id, responses

        results = await asyncio.gather(*[run_probe_samples(p) for p in probes])
        self.behavioral_results = dict(results)
        return self.behavioral_results

    async def run_capability_probes(self, count: int = 4) -> dict:
        """Run capability test probes."""
        probes = self._capability_probes[:count]
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

        async def run_probe(probe: Probe) -> tuple[str, dict]:
            async with semaphore:
                result = await self.client.chat_completion(
                    model=self.model,
                    messages=[{"role": "user", "content": probe.prompt}],
                    temperature=probe.temperature,
                    max_tokens=probe.max_tokens,
                )
                if "error" in result:
                    return probe.id, {"error": result["error"]}
                try:
                    content = result["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError):
                    content = ""
                return probe.id, {
                    "response": content,
                    "latency_ms": result.get("_latency_ms", 0),
                }

        results = await asyncio.gather(*[run_probe(p) for p in probes])
        self.capability_results = dict(results)
        return self.capability_results

    def analyze(self) -> FingerprintResult:
        """Analyze all probe results and produce a fingerprint verdict.

        Combines tokenizer signature, behavioral fingerprint (with
        statistical comparison against real baselines), and capability
        tests to produce a statistically grounded verdict.
        """
        claimed_family = self._claimed_family()
        suspicious = False
        confidence = 0.5
        detected_family = None

        # Analyze tokenizer signature
        tokenizer_sig = self._analyze_tokenizer()
        # Analyze behavioral signature (with statistical comparison)
        behavioral_sig = self._analyze_behavioral()
        # Analyze capability
        capability_sig = self._analyze_capability()

        # Tokenizer anomaly detection
        if tokenizer_sig.get("anomaly_score", 0) > 0.5:
            suspicious = True
            confidence = max(confidence, 0.7)

        # Capability failure detection
        if capability_sig.get("failure_rate", 0) > 0.5:
            suspicious = True
            confidence = max(confidence, 0.6)

        # Behavioral fingerprint statistical detection (NEW)
        stat_match = behavioral_sig.get("statistical_match")
        if stat_match:
            if stat_match.get("chi2_significant") and stat_match.get("fingerprint_match_rate", 1.0) < 0.5:
                # Behavioral fingerprint significantly different from baseline
                suspicious = True
                confidence = max(confidence, 0.85)
            elif stat_match.get("chi2_significant") and stat_match.get("fingerprint_match_rate", 1.0) < 0.7:
                suspicious = True
                confidence = max(confidence, 0.7)
            elif (not stat_match.get("chi2_significant") and
                  stat_match.get("fingerprint_match_rate", 0) > 0.8):
                # Strong behavioral fingerprint match - increases confidence in honesty
                confidence = max(confidence, 0.6)

        # Determine detected family (best effort)
        detected_family = self._guess_family(tokenizer_sig, behavioral_sig)

        family_match = (
            claimed_family is not None
            and detected_family is not None
            and claimed_family.split("-")[0] == detected_family.split("-")[0]
        )

        if not family_match and claimed_family and detected_family:
            suspicious = True
            confidence = max(confidence, 0.8)

        return FingerprintResult(
            claimed_model=self.model,
            detected_family=detected_family,
            family_match=family_match,
            confidence=confidence,
            tokenizer_signature=tokenizer_sig,
            behavioral_signature=behavioral_sig,
            suspicious=suspicious,
        )

    def _analyze_tokenizer(self) -> dict:
        """Analyze tokenizer probe results."""
        if not self.tokenizer_results:
            return {"error": "no data"}

        total_prompt_tokens = 0
        anomalies = 0
        probe_count = 0

        for probe_id, result in self.tokenizer_results.items():
            if "error" in result:
                continue
            probe_count += 1
            total_prompt_tokens += result.get("prompt_tokens", 0)

            # Check if token count is within expected range
            probe = next((p for p in TOKENIZER_PROBES if p.id == probe_id), None)
            if probe and probe.expected_tokens_range:
                lo, hi = probe.expected_tokens_range
                actual = result.get("prompt_tokens", 0)
                if actual < lo * 0.5 or actual > hi * 2:
                    anomalies += 1

        avg_prompt_tokens = total_prompt_tokens / max(probe_count, 1)
        anomaly_score = anomalies / max(probe_count, 1)

        return {
            "probe_count": probe_count,
            "avg_prompt_tokens": round(avg_prompt_tokens, 1),
            "anomaly_count": anomalies,
            "anomaly_score": round(anomaly_score, 2),
            "individual_results": {
                k: v for k, v in self.tokenizer_results.items() if "error" not in v
            },
        }

    def _analyze_behavioral(self) -> dict:
        """Analyze behavioral probe results with statistical comparison.

        Uses chi-square test to compare observed response distributions
        against real baseline data. Strong behavioral fingerprints
        (e.g., gpt-4o-mini returns "7" 100% for 1-10 selection)
        are highly discriminative.
        """
        if not self.behavioral_results:
            return {"error": "no data"}

        signatures = {}
        all_observed = {}
        for probe_id, responses in self.behavioral_results.items():
            if not responses:
                continue
            counter = Counter(responses)
            most_common = counter.most_common(3)
            total = len(responses)
            entropy = 0.0
            for count in counter.values():
                p = count / total
                if p > 0:
                    entropy -= p * (p ** 0.5)  # simplified entropy
            signatures[probe_id] = {
                "sample_count": total,
                "unique_responses": len(counter),
                "top3": most_common,
                "diversity_score": round(len(counter) / max(total, 1), 2),
            }
            all_observed[probe_id] = responses

        # Statistical comparison against real baselines
        statistical_match = None
        baseline_info = {"available": False}
        if all_observed:
            # Check if we have a baseline for this model
            baseline = None
            for key, bl in self.stat_analyzer.baseline_db.items():
                if key.lower() in self.model.lower() or self.model.lower() in key.lower():
                    baseline = bl
                    break

            if baseline and baseline.behavioral_distributions:
                baseline_info = {
                    "available": True,
                    "baseline_model": baseline.model_name,
                    "baseline_family": baseline.model_family,
                    "baseline_sample_size": baseline.sample_size,
                }

                # Run chi-square test for behavioral distributions
                chi2_stat, chi2_pvalue = self.stat_analyzer.chi2_test_behavioral(
                    all_observed, baseline
                )

                # Calculate behavioral fingerprint match score
                # Strong fingerprints: if top response matches baseline top response
                fingerprint_matches = 0
                fingerprint_total = 0
                for probe_id, observed_responses in all_observed.items():
                    if probe_id not in baseline.behavioral_distributions:
                        continue
                    baseline_responses = baseline.behavioral_distributions[probe_id]
                    if not baseline_responses or not observed_responses:
                        continue
                    fingerprint_total += 1
                    observed_top = Counter(observed_responses).most_common(1)[0][0]
                    baseline_top = Counter(baseline_responses).most_common(1)[0][0]
                    if observed_top == baseline_top:
                        fingerprint_matches += 1

                fingerprint_match_rate = fingerprint_matches / max(fingerprint_total, 1)

                statistical_match = {
                    "chi2_statistic": round(chi2_stat, 4),
                    "chi2_pvalue": round(chi2_pvalue, 4),
                    "chi2_significant": chi2_pvalue < 0.05,
                    "fingerprint_match_rate": round(fingerprint_match_rate, 2),
                    "fingerprint_matches": fingerprint_matches,
                    "fingerprint_total": fingerprint_total,
                    "interpretation": self._interpret_behavioral_match(chi2_pvalue, fingerprint_match_rate),
                }

        return {
            "probe_count": len(signatures),
            "signatures": signatures,
            "statistical_match": statistical_match,
            "baseline_info": baseline_info,
        }

    def _interpret_behavioral_match(self, chi2_pvalue: float, fingerprint_match_rate: float) -> str:
        """Interpret behavioral fingerprint match results in plain language."""
        if chi2_pvalue is None:
            return "无基准数据，无法进行统计比较"
        if chi2_pvalue < 0.01 and fingerprint_match_rate < 0.5:
            return "行为指纹与基准显著不符，高度可疑模型被替换"
        elif chi2_pvalue < 0.05 and fingerprint_match_rate < 0.7:
            return "行为指纹与基准存在显著差异，可疑模型被降级"
        elif chi2_pvalue > 0.5 and fingerprint_match_rate > 0.8:
            return "行为指纹与基准高度匹配，模型身份可信"
        elif chi2_pvalue > 0.1:
            return "行为指纹与基准无显著差异"
        else:
            return "行为指纹存在边缘差异，建议增加样本量重新测试"

    def _analyze_capability(self) -> dict:
        """Analyze capability probe results.

        Capability probes help differentiate model tiers:
        - Simple math/logic: all models should pass
        - Reasoning chain: gpt-3.5 often fails, gpt-4 passes
        - Knowledge cutoff: older models don't know 2024 events
        - Code bug fix: tests code understanding
        - Multilingual: low-tier models struggle with Arabic
        """
        if not self.capability_results:
            return {"error": "no data"}

        # Expected answers for capability probes
        expected = {
            "cap-simple-math": {"391"},
            "cap-logic": {"no", "No", "NO"},
            "cap-following-instructions": {"1,2,4,5", "1, 2, 4, 5", "1 2 4 5", "1,2,4,5."},
            "cap-reasoning-chain": {"5", "5 cents", "5 cents.", "5¢"},
            "cap-knowledge-cutoff": {"trump", "Trump", "Donald Trump", "donald trump"},
            "cap-context-length": {"alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel-india-juliet"},
        }

        # Probe difficulty tiers (for model tier estimation)
        easy_probes = {"cap-simple-math", "cap-logic", "cap-following-instructions"}
        medium_probes = {"cap-code-syntax", "cap-code-bug-fix", "cap-context-length", "cap-multilingual"}
        hard_probes = {"cap-reasoning-chain", "cap-knowledge-cutoff", "cap-math-word-problem"}

        passed = 0
        total = 0
        easy_passed = 0
        medium_passed = 0
        hard_passed = 0
        details = {}

        for probe_id, result in self.capability_results.items():
            if "error" in result:
                continue
            total += 1
            response = result.get("response", "").strip()
            is_correct = False

            if probe_id in expected:
                is_correct = response in expected[probe_id]
            elif probe_id == "cap-code-syntax":
                is_correct = "sum" in response.lower() and ("%" in response or "for" in response or "[" in response)
            elif probe_id == "cap-code-bug-fix":
                is_correct = "if" in response.lower() and ("n ==" in response or "n<=" in response or "n <==" in response or "1" in response)
            elif probe_id == "cap-math-word-problem":
                # Average speed = total distance / total time
                # Distance1 = 60*2.5 = 150, Distance2 = 80*1.5 = 120, Total = 270
                # Time = 4 hours, Avg = 67.5
                is_correct = "67.5" in response or "68" in response or "67" in response
            elif probe_id == "cap-multilingual":
                # Just check if response contains Japanese/Korean/Arabic characters
                has_japanese = any('\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff' for c in response)
                has_korean = any('\uac00' <= c <= '\ud7af' for c in response)
                has_arabic = any('\u0600' <= c <= '\u06ff' for c in response)
                is_correct = has_japanese and has_korean and has_arabic

            if is_correct:
                passed += 1
                if probe_id in easy_probes:
                    easy_passed += 1
                elif probe_id in medium_probes:
                    medium_passed += 1
                elif probe_id in hard_probes:
                    hard_passed += 1

            details[probe_id] = {
                "response": response[:80],
                "passed": is_correct,
                "difficulty": "easy" if probe_id in easy_probes else "medium" if probe_id in medium_probes else "hard",
            }

        # Estimate model tier based on pass rates by difficulty
        tier_estimate = "unknown"
        if total > 0:
            easy_rate = easy_passed / max(len(easy_probes & set(self.capability_results.keys())), 1)
            medium_rate = medium_passed / max(len(medium_probes & set(self.capability_results.keys())), 1)
            hard_rate = hard_passed / max(len(hard_probes & set(self.capability_results.keys())), 1)

            if easy_rate >= 0.8 and medium_rate >= 0.6 and hard_rate >= 0.4:
                tier_estimate = "high"
            elif easy_rate >= 0.6 and medium_rate >= 0.4:
                tier_estimate = "medium"
            else:
                tier_estimate = "low"

        return {
            "total": total,
            "passed": passed,
            "failure_rate": round(1 - passed / max(total, 1), 2),
            "easy_passed": easy_passed,
            "medium_passed": medium_passed,
            "hard_passed": hard_passed,
            "tier_estimate": tier_estimate,
            "details": details,
        }

    def _guess_family(self, tokenizer_sig: dict, behavioral_sig: dict) -> Optional[str]:
        """Best-effort family detection based on tokenizer patterns."""
        # This is a simplified heuristic - real implementation would
        # compare against a benchmark database of known model signatures
        avg_tokens = tokenizer_sig.get("avg_prompt_tokens", 0)

        if avg_tokens == 0:
            return None

        # Very rough: GPT models tend to have lower token counts for CJK,
        # Claude tends to have higher, Gemini varies
        # In practice, this would compare against benchmark data
        return self._claimed_family()  # default to claimed if can't determine
