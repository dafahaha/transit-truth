"""Token count verification.

Compares token counts reported by a relay service against:
1. Expected token counts from the official API (if key provided)
2. Token counts computed locally using tiktoken (for OpenAI models)
3. Heuristic estimates based on text length

IMPORTANT: When comparing with local tiktoken counts, the reported
prompt tokens will ALWAYS be higher because they include chat template
tokens (system messages, role markers, special tokens like <|im_start|>).
This is why we call it "discrepancy" rather than "inflation" — the
difference may be legitimate chat template overhead, not overcounting.
For definitive proof of overcounting, comparison with the official API
is required.
"""
import re
from typing import Optional

from ..models import TokenComparison
from ..utils.http_client import AsyncAPIClient


# Chat template overhead estimates (tokens added by the API wrapper)
# These are rough estimates for common model families
CHAT_TEMPLATE_OVERHEAD = {
    "gpt-4": 12,      # System + role markers for gpt-4 family
    "gpt-3.5": 12,    # System + role markers for gpt-3.5 family
    "claude": 8,      # Anthropic chat format
    "gemini": 10,     # Google chat format
    "default": 10,    # Default estimate
}


def estimate_chat_template_overhead(model: str) -> int:
    """Estimate chat template token overhead for a model family."""
    model_lower = model.lower()
    for family, overhead in CHAT_TEMPLATE_OVERHEAD.items():
        if family in model_lower:
            return overhead
    return CHAT_TEMPLATE_OVERHEAD["default"]


class TokenVerifier:
    """Verify token counts reported by an API endpoint."""

    def __init__(self, client: AsyncAPIClient, model: str):
        self.client = client
        self.model = model

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate when tiktoken is not available.

        Uses the common heuristic: ~4 chars per token for English,
        adjusted for mixed content.
        """
        if not text:
            return 0
        char_count = len(text)
        # Count CJK characters (they tend to be 1-2 tokens each)
        cjk_count = len(re.findall(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', text))
        # Count non-CJK
        other_count = char_count - cjk_count
        # Heuristic: 4 chars/token for other, 1.5 chars/token for CJK
        estimated = int(other_count / 4 + cjk_count / 1.5)
        return max(estimated, 1)

    def _compute_local_tokens(self, text: str) -> Optional[int]:
        """Compute tokens using tiktoken if available."""
        try:
            import tiktoken
            # Try to get encoding for the model
            try:
                encoding = tiktoken.encoding_for_model(self.model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            return None

    async def verify(
        self,
        test_prompts: list[str] | None = None,
        official_client: Optional[AsyncAPIClient] = None,
    ) -> TokenComparison:
        """Run token count verification.

        Args:
            test_prompts: List of prompts to test with. If None, uses defaults.
            official_client: Client for official API comparison (optional).
        """
        if test_prompts is None:
            test_prompts = [
                "Hello, how are you today?",
                "Explain quantum computing in simple terms.",
                "Write a Python function to sort a list.",
                "What are the main differences between TCP and UDP?",
                "Translate 'hello world' to French, Spanish, and German.",
            ]

        relay_prompt_tokens = []
        relay_completion_tokens = []
        official_prompt_tokens = []
        official_completion_tokens = []
        local_prompt_tokens = []

        for prompt in test_prompts:
            # Get relay response
            relay_result = await self.client.chat_completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=128,
            )

            if "error" in relay_result:
                continue

            relay_usage = relay_result.get("usage", {})
            relay_prompt_tokens.append(relay_usage.get("prompt_tokens", 0))
            relay_completion_tokens.append(relay_usage.get("completion_tokens", 0))

            # Compute local token count
            local = self._compute_local_tokens(prompt)
            if local is not None:
                local_prompt_tokens.append(local)

            # Compare with official API if available
            if official_client:
                official_result = await official_client.chat_completion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=128,
                )
                if "error" not in official_result:
                    official_usage = official_result.get("usage", {})
                    official_prompt_tokens.append(official_usage.get("prompt_tokens", 0))
                    official_completion_tokens.append(official_usage.get("completion_tokens", 0))

        # Aggregate
        total_relay_prompt = sum(relay_prompt_tokens)
        total_relay_completion = sum(relay_completion_tokens)
        total_relay = total_relay_prompt + total_relay_completion

        total_official_prompt = sum(official_prompt_tokens) if official_prompt_tokens else None
        total_official_completion = sum(official_completion_tokens) if official_completion_tokens else None

        # Calculate discrepancy (called "discrepancy" not "inflation" because
        # it may include legitimate chat template overhead)
        prompt_discrepancy = None
        completion_discrepancy = None
        suspicious = False
        discrepancy_note = ""

        # Estimate chat template overhead for this model
        chat_overhead = estimate_chat_template_overhead(self.model)
        num_prompts = len(relay_prompt_tokens)
        total_chat_overhead = chat_overhead * num_prompts if num_prompts > 0 else 0

        if total_official_prompt and total_official_prompt > 0:
            # Official API comparison is definitive (both use same chat template)
            prompt_discrepancy = round(
                (total_relay_prompt - total_official_prompt) / total_official_prompt * 100, 2
            )
            if prompt_discrepancy > 10:  # More than 10% discrepancy is suspicious
                suspicious = True
            discrepancy_note = "Compared with official API (definitive)"

        if total_official_completion and total_official_completion > 0:
            completion_discrepancy = round(
                (total_relay_completion - total_official_completion) / total_official_completion * 100, 2
            )
            if completion_discrepancy > 10:
                suspicious = True

        # If no official API, compare with local tiktoken counts
        # IMPORTANT: Must subtract estimated chat template overhead before judging
        if prompt_discrepancy is None and local_prompt_tokens:
            total_local = sum(local_prompt_tokens)
            if total_local > 0:
                # Raw discrepancy (includes chat template)
                raw_discrepancy = round(
                    (total_relay_prompt - total_local) / total_local * 100, 2
                )
                prompt_discrepancy = raw_discrepancy

                # Adjusted discrepancy (subtract estimated chat template overhead)
                adjusted_relay = total_relay_prompt - total_chat_overhead
                adjusted_discrepancy = round(
                    (adjusted_relay - total_local) / total_local * 100, 2
                ) if total_local > 0 else 0

                # Only flag as suspicious if adjusted discrepancy is still > 20%
                # (wider margin because chat template estimate is rough)
                if adjusted_discrepancy > 20:
                    suspicious = True

                discrepancy_note = (
                    f"Local tiktoken comparison (includes ~{chat_overhead} tokens/prompt "
                    f"chat template overhead, adjusted discrepancy: {adjusted_discrepancy:+.1f}%). "
                    f"For definitive proof, compare with official API."
                )

        return TokenComparison(
            prompt_tokens_reported=total_relay_prompt,
            prompt_tokens_expected=total_official_prompt or (sum(local_prompt_tokens) if local_prompt_tokens else None),
            completion_tokens_reported=total_relay_completion,
            completion_tokens_expected=total_official_completion,
            total_tokens_reported=total_relay,
            prompt_inflation_pct=prompt_discrepancy,
            completion_inflation_pct=completion_discrepancy,
            suspicious=suspicious,
            discrepancy_note=discrepancy_note,
            chat_template_overhead=total_chat_overhead,
        )
